"""CSV/JSON ingestion with per-row atomicity and a durable error report."""
import csv
import hashlib
import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from services.database import now
from services.normalization import clean, normalized_name, parse_quantity, positive

SOURCES = {'IMPORTED', 'MANUAL', 'DEMO', 'COLLECTED'}


def url(value):
    if not value:
        return None
    parsed = urlparse(str(value))
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('URLs must be absolute HTTP(S) URLs without credentials')
    return str(value)


def stamp(value):
    if not value:
        return now()
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is None or dt > datetime.now(timezone.utc):
            raise ValueError()
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        raise ValueError('observed_at must be a timezone-aware timestamp, not in the future') from None


def prepare(raw, kind, source):
    if not isinstance(raw, dict):
        raise ValueError('Each row must be an object')
    row = {k: v.strip() if isinstance(v, str) else v for k, v in raw.items()}
    for field in ('company', 'brand', 'category', 'product_name'):
        if not isinstance(row.get(field), str) or not clean(row[field]):
            raise ValueError(f'{field} is required')
    for field in ('country', 'unit', 'retailer', 'retailer_sku', 'availability', 'currency'):
        if row.get(field) is not None and not isinstance(row[field], str):
            raise ValueError(f'{field} must be text')
    is_pg = clean(row['company']) in {'p g', 'procter gamble', 'procter and gamble'}
    if (kind == 'pg') != is_pg:
        raise ValueError('Company does not agree with the P&G/competitor import type')
    if is_pg:
        row['company'] = 'P&G'
    if (row.get('country') or 'QA').upper() not in {'QA', 'QATAR'}:
        raise ValueError('This catalogue is scoped to Qatar (QA)')
    row['quantity'] = parse_quantity(row.get('size', ''), row.get('unit'), row.get('pack_count'))
    for field in ('product_url', 'image_url', 'source_reference', 'retailer_website'):
        row[field] = url(row.get(field))
    for field in ('barcode', 'sku', 'variant_name', 'subcategory', 'purpose', 'product_family', 'description'):
        if row.get(field) is not None and not isinstance(row[field], str):
            raise ValueError(f'{field} must be text')
    row['attributes'] = row.get('attributes') or {}
    if isinstance(row['attributes'], str):
        try:
            row['attributes'] = json.loads(row['attributes'])
        except ValueError:
            raise ValueError('attributes must be a JSON object') from None
    if not isinstance(row['attributes'], dict) or any(not isinstance(v, str) for v in row['attributes'].values()):
        raise ValueError('attributes must map attribute names to strings')
    row['source_state'] = source
    if source not in SOURCES:
        raise ValueError('Unsupported provenance')
    row['price'] = float(positive(row['price'], 'price', 1000000)) if row.get('price') not in (None, '') else None
    if row.get('currency') and row['currency'] != 'QAR':
        raise ValueError('Qatar observations require QAR')
    if row['price'] is not None and not row.get('retailer'):
        raise ValueError('A price requires a retailer listing')
    if row.get('retailer') and not (row.get('retailer_sku') or row['product_url']):
        raise ValueError('A retailer listing needs a stable retailer_sku or product_url')
    row['availability'] = row.get('availability') or 'unknown'
    if row['availability'] not in {'available', 'out_of_stock', 'unknown'}:
        raise ValueError('Invalid availability')
    row['observed_at'] = stamp(row.get('observed_at'))
    row['kind'] = kind
    return row


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_row(db, row, event_key, import_id=None, collection_id=None, forced_id=None):
    timestamp = now()
    company_id = clean(row['company']).replace(' ', '-')
    brand_id = company_id + ':' + clean(row['brand']).replace(' ', '-')
    category_id = clean(row['category']).replace(' ', '-')
    db.execute('INSERT OR IGNORE INTO companies VALUES (?,?,?,?)', (company_id, row['company'], row['kind'], timestamp))
    db.execute('INSERT OR IGNORE INTO brands(id,company_id,name,slug,created_at) VALUES (?,?,?,?,?)',
               (brand_id, company_id, row['brand'], clean(row['brand']).replace(' ', '-'), timestamp))
    db.execute('INSERT OR IGNORE INTO categories(id,name,slug) VALUES (?,?,?)', (category_id, row['category'], category_id))
    name = row.get('product_family') or row['product_name']
    normalized = normalized_name(name, row['brand'])
    demo_scope = row['source_state'] == 'DEMO'
    db.execute('INSERT OR IGNORE INTO products(brand_id,category_id,name,normalized_name,product_family,description,image_url,demo_scope,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
               (brand_id, category_id, name, normalized, row.get('product_family'), row.get('description'), row.get('image_url'), demo_scope, timestamp, timestamp))
    family_id = db.execute('SELECT id FROM products WHERE brand_id=? AND category_id=? AND normalized_name=? AND demo_scope=?', (brand_id, category_id, normalized, demo_scope)).fetchone()[0]
    q = row['quantity'] or (None, None, None, None, None)
    # Per-item size and pack count are part of SKU identity: 2 x 500ml is not 1 x 1L.
    per_item = q[3] / q[2] if q[3] is not None else None
    source_demo = demo_scope
    identity = digest([source_demo, brand_id, category_id, normalized,
                       clean(row.get('variant_name')), per_item, q[4], q[2], clean(row.get('size')) if not row['quantity'] else None])
    barcode = row.get('barcode') or None
    existing = db.execute('SELECT * FROM product_variants WHERE identity_key=?', (identity,)).fetchone()
    if barcode:
        by_code = db.execute("SELECT * FROM product_variants WHERE barcode=? AND (source_state='DEMO')=?", (barcode, source_demo)).fetchone()
        if by_code and (not existing or existing['id'] != by_code['id']):
            # Refuse ambiguous identity changes; operator must reconcile explicitly.
            raise ValueError('Barcode already belongs to a different variant identity')
    if existing and existing['barcode'] and barcode and existing['barcode'] != barcode:
        raise ValueError('Variant identity already has a different barcode')
    if row.get('sku'):
        by_sku = db.execute("SELECT v.id FROM product_variants v JOIN products p ON p.id=v.product_id WHERE p.brand_id=? AND v.sku=? AND (v.source_state='DEMO')=?", (brand_id, row['sku'], source_demo)).fetchone()
        if by_sku and (not existing or existing['id'] != by_sku['id']):
            raise ValueError('Manufacturer SKU already belongs to a different variant identity')
    if existing:
        old_attributes = json.loads(existing['attributes'])
        if any(old_attributes.get(key) and row['attributes'].get(key) and clean(old_attributes[key]) != clean(row['attributes'][key])
               for key in ('form', 'concentration', 'diaper_size', 'razor_type', 'target_customer', 'product_type')):
            raise ValueError('Conflicting essential attributes; use a distinct variant_name or reconcile the identity')
    values = dict(product_id=family_id, identity_key=identity, display_name=row['product_name'], sku=row.get('sku'), barcode=barcode,
                  variant_name=row.get('variant_name'), size_value=q[0], size_unit=q[1], pack_count=q[2],
                  normalized_quantity=q[3], normalized_unit=q[4], original_size=str(row.get('size') or ''),
                  subcategory=row.get('subcategory'), purpose=row.get('purpose'), attributes=json.dumps(row['attributes'], sort_keys=True),
                  country='QA', source_state=row['source_state'], source_reference=row.get('source_reference'))
    if existing:
        merged_attributes = json.loads(existing['attributes']) | row['attributes']
        values['attributes'] = json.dumps(merged_attributes, sort_keys=True)
        # Reimporting an identity does not reclassify its provenance or clear verification.
        values['source_state'] = existing['source_state']
        changes = {k: v for k, v in values.items() if v not in (None, '') and v != existing[k]}
        if changes:
            changes['updated_at'] = timestamp
            db.execute('UPDATE product_variants SET ' + ','.join(k + '=?' for k in changes) + ' WHERE id=?', (*changes.values(), existing['id']))
        variant_id, outcome = existing['id'], 'updated' if changes else 'skipped'
    else:
        values.update(created_at=timestamp, updated_at=timestamp)
        if forced_id is not None:
            values['id'] = forced_id
        result = db.execute('INSERT INTO product_variants(' + ','.join(values) + ') VALUES (' + ','.join('?' for _ in values) + ')', tuple(values.values()))
        variant_id, outcome = result.lastrowid, 'imported'
    for field in ('image_url', 'description'):
        if row.get(field):
            db.execute(f'UPDATE products SET {field}=?,updated_at=? WHERE id=? AND ({field} IS NULL OR {field}=\'\')', (row[field], timestamp, family_id))
    if row.get('retailer'):
        retailer_id = clean(row['retailer']).replace(' ', '_')
        db.execute('INSERT OR IGNORE INTO retailers(id,name,website,created_at) VALUES (?,?,?,?)', (retailer_id, row['retailer'], row.get('retailer_website'), timestamp))
        sku = row.get('retailer_sku') or row['product_url']
        old = db.execute("SELECT * FROM retailer_products WHERE retailer_id=? AND retailer_sku=? AND (source_state='DEMO')=?", (retailer_id, sku, source_demo)).fetchone()
        if old and old['product_variant_id'] != variant_id:
            raise ValueError('Retailer SKU is already linked to a different variant')
        if old and db.execute('SELECT 1 FROM price_observations WHERE retailer_product_id=? AND event_key=?', (old['id'], event_key)).fetchone():
            return variant_id, outcome
        if old:
            listing_id = old['id']
            if row['observed_at'] >= old['last_seen_at']:
                db.execute('UPDATE retailer_products SET retailer_product_name=?,retailer_product_url=COALESCE(?,retailer_product_url),image_url=COALESCE(?,image_url),availability=?,last_seen_at=?,source_state=?,collection_error=NULL WHERE id=?',
                           (row['product_name'], row['product_url'], row['image_url'], row['availability'], row['observed_at'], row['source_state'], listing_id))
        else:
            listing_id = db.execute('INSERT INTO retailer_products(retailer_id,product_variant_id,retailer_product_name,retailer_product_url,retailer_sku,image_url,availability,source_state,last_seen_at) VALUES (?,?,?,?,?,?,?,?,?)',
                (retailer_id, variant_id, row['product_name'], row['product_url'], sku, row['image_url'], row['availability'], row['source_state'], row['observed_at'])).lastrowid
        result = db.execute('INSERT OR IGNORE INTO price_observations(retailer_product_id,price,currency,observed_at,source_state,availability,source_reference,collection_run_id,import_run_id,event_key) VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (listing_id, row['price'], 'QAR', row['observed_at'], row['source_state'], row['availability'], row['source_reference'] or row['product_url'], collection_id, import_id, event_key))
        if result.rowcount and outcome == 'skipped':
            outcome = 'updated'
    return variant_id, outcome


class Importer:
    def __init__(self, database):
        self.database = database

    def run(self, rows, kind='pg', source='IMPORTED', dry_run=False):
        run_id = str(uuid.uuid4())
        summary = dict(id=run_id, total=0, imported=0, updated=0, skipped=0, errors=[], dry_run=dry_run)
        with self.database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO import_runs VALUES (?,?,?,?,?)', (run_id, source, int(dry_run), '{}', now()))
            evidence = []
            for number, raw in enumerate(rows, 1):
                summary['total'] += 1
                serialized = json.dumps(raw, ensure_ascii=False)
                if dry_run:
                    evidence.append((run_id, number, serialized))
                db.execute('INSERT INTO import_rows(import_run_id,row_number,raw_data) VALUES (?,?,?)', (run_id, number, serialized))
                db.execute('SAVEPOINT import_row')
                try:
                    row = prepare(raw, kind, source)
                    _, outcome = save_row(db, row, 'import:' + digest([source, raw]), import_id=run_id)
                    summary[outcome] += 1
                    db.execute('RELEASE import_row')
                except (ValueError, TypeError, sqlite3.IntegrityError) as error:
                    db.execute('ROLLBACK TO import_row')
                    db.execute('RELEASE import_row')
                    summary['errors'].append({'row': number, 'message': str(error)})
            if dry_run:
                db.rollback()
                db.execute('INSERT INTO import_runs VALUES (?,?,?,?,?)', (run_id, source, int(dry_run), json.dumps(summary), now()))
                db.executemany('INSERT INTO import_rows(import_run_id,row_number,raw_data) VALUES (?,?,?)', evidence)
            else:
                db.execute('UPDATE import_runs SET summary=? WHERE id=?', (json.dumps(summary), run_id))
            db.executemany('INSERT INTO import_errors(import_run_id,row_number,error_message) VALUES (?,?,?)',
                           [(run_id, e['row'], e['message']) for e in summary['errors']])
        return summary


def read_rows(content, format):
    if format == 'csv':
        return csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    rows = json.loads(content)
    if not isinstance(rows, list):
        raise ValueError('JSON import must be an array')
    return rows

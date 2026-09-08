"""Durable single-worker queue using the existing, policy-aware retailer adapters."""
import asyncio
import json
import uuid

from services.database import now
from services.imports import prepare, save_row
from services.normalization import clean


class CollectionJobs:
    def __init__(self, repository, connectors, matches):
        self.repository, self.database = repository, repository.database
        self.connectors, self.matches = connectors, matches
        with self.database.connect() as db:
            for slug, connector in connectors.items():
                # Use canonical platform identity across imports and connectors.
                db.execute('INSERT OR IGNORE INTO retailers(id,name,created_at) VALUES (?,?,?)',
                           (clean(connector.platform).replace(' ', '_'), connector.platform, now()))

    def enqueue(self, retailers, query, context=None):
        if any(slug not in self.connectors for slug in retailers):
            raise ValueError('Unknown retailer')
        ids = []
        with self.database.connect() as db:
            for slug in dict.fromkeys(retailers):
                id = str(uuid.uuid4())
                retailer_id = clean(self.connectors[slug].platform).replace(' ', '_')
                db.execute('INSERT INTO data_collection_runs(id,retailer_id,query,context,status) VALUES (?,?,?,?,?)',
                           (id, retailer_id, query, json.dumps((context or {}) | {'connector': slug}), 'QUEUED'))
                ids.append(id)
        return ids

    def recover(self):
        # Only one worker process may own this local queue. Never manufacture a success after a crash.
        with self.database.connect() as db:
            db.execute("UPDATE data_collection_runs SET status='ERROR',completed_at=?,errors='Worker interrupted; retry is available' WHERE status='RUNNING'", (now(),))

    def claim(self):
        with self.database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM data_collection_runs WHERE status='QUEUED' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE data_collection_runs SET status='RUNNING',started_at=?,attempts=attempts+1 WHERE id=?", (now(), row['id']))
            return dict(row)

    def record_search(self, slug, query, result):
        id = str(uuid.uuid4())
        retailer_id = clean(self.connectors[slug].platform).replace(' ', '_')
        run = dict(id=id, retailer_id=retailer_id, query=query, context=json.dumps({'connector': slug}))
        with self.database.connect() as db:
            db.execute('INSERT INTO data_collection_runs(id,retailer_id,query,context,status,started_at,attempts) VALUES (?,?,?,?,?,?,1)',
                       (id, retailer_id, query, run['context'], 'RUNNING', now()))
        self.process(run, result)
        return id

    def process(self, run, result=None):
        context = json.loads(run['context'])
        try:
            if result is None:
                result = self.connectors[context['connector']].search(run['query'])
            if result.data_status == 'UNAVAILABLE':
                self.finish(run, 'UNAVAILABLE', 0, 0, [('RETAILER_UNAVAILABLE', result.reason)])
                return
        except Exception:
            self.finish(run, 'ERROR', 0, 0, [('COLLECTION_ERROR', 'Retailer connector failed; previous observations retained.')])
            return
        errors, saved = [], 0
        for observation in result.products:
            raw = observation.model_dump(mode='json')
            try:
                # Retailer source must identify the brand/company itself. Query context is not identity evidence.
                if not observation.brand or not observation.company:
                    raise ValueError('Brand/company missing; retained for identity review')
                known = self.database.rows('''SELECT v.id,c.type FROM retailer_products rp
                  JOIN product_variants v ON v.id=rp.product_variant_id JOIN products p ON p.id=v.product_id
                  JOIN brands b ON b.id=p.brand_id JOIN companies c ON c.id=b.company_id
                  WHERE rp.retailer_id=? AND rp.retailer_product_url=? AND v.source_state<>'DEMO' ''', (run['retailer_id'], str(observation.product_url)))
                if known:
                    product = self.repository.get(known[0]['id'])
                    if clean(product.brand) != clean(observation.brand) or clean(product.company) != clean(observation.company):
                        raise ValueError('Known retailer URL has contradictory brand/company')
                    row = dict(company=product.company, brand=product.brand, category=product.category,
                        product_name=product.product_name, product_family=product.product_family, variant_name=product.variant,
                        size=product.size_value or '', unit=product.unit, pack_count=product.pack_quantity,
                        barcode=product.barcode, subcategory=product.subcategory, purpose=product.purpose, attributes=product.attributes)
                    kind = known[0]['type']
                else:
                    if not observation.category and not context.get('category'):
                        raise ValueError('Category missing; retained for identity review')
                    row = dict(company=observation.company, brand=observation.brand, category=observation.category or context['category'],
                               product_name=observation.product_name, size=observation.product_size or '',
                               barcode=observation.barcode, subcategory=observation.subcategory, purpose=observation.purpose,
                               variant_name=observation.variant_name, attributes=observation.attributes)
                    kind = 'pg' if clean(observation.company) in {'p g', 'procter gamble', 'procter and gamble'} else 'competitor'
                row.update(retailer=observation.platform, retailer_sku=observation.retailer_sku, product_url=str(observation.product_url),
                           image_url=str(observation.product_image) if observation.product_image else None,
                           price=observation.current_price, currency=observation.currency, availability=observation.availability,
                           observed_at=observation.collected_at.isoformat())
                prepared = prepare(row, kind, 'COLLECTED')
                with self.database.connect() as db:
                    save_row(db, prepared, 'collection:' + run['id'], collection_id=run['id'])
                saved += 1
                state, reason = 'SAVED', None
            except (ValueError, KeyError, TypeError) as error:
                state, reason = 'REQUIRES_REVIEW', str(error)
                errors.append(('IDENTITY_REVIEW', reason))
            except Exception:
                state, reason = 'ERROR', 'Could not persist observation; raw discovery retained.'
                errors.append(('COLLECTION_ERROR', reason))
            with self.database.connect() as db:
                db.execute('INSERT INTO discoveries(collection_run_id,product_url,raw_product,state,reason,created_at) VALUES (?,?,?,?,?,?)',
                           (run['id'], str(observation.product_url), json.dumps(raw), state, reason, now()))
        self.finish(run, 'PARTIAL' if errors else 'COMPLETED', len(result.products), saved, errors)
        if saved:
            self.matches.recalculate()

    def finish(self, run, status, found, saved, errors):
        with self.database.connect() as db:
            db.execute('UPDATE data_collection_runs SET status=?,records_found=?,records_saved=?,completed_at=?,errors=? WHERE id=?',
                       (status, found, saved, now(), json.dumps(errors), run['id']))
            for kind, message in errors:
                db.execute('INSERT INTO data_collection_errors(collection_run_id,error_type,product_query,error_message,created_at) VALUES (?,?,?,?,?)',
                           (run['id'], kind, run['query'], message, now()))
            if status in {'ERROR', 'UNAVAILABLE'}:
                db.execute("UPDATE retailer_products SET collection_error=? WHERE retailer_id=? AND source_state='COLLECTED'", ('Latest retailer collection failed; previous observation retained.', run['retailer_id']))

    async def run(self):
        self.recover()
        while True:
            run = await asyncio.to_thread(self.claim)
            if run:
                try:
                    await asyncio.to_thread(self.process, run)
                except Exception:
                    await asyncio.to_thread(self.finish, run, 'ERROR', 0, 0, [('COLLECTION_ERROR', 'Collection worker failed; retry is available.')])
            else:
                await asyncio.sleep(1)

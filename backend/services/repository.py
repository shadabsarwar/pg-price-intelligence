import json
from collections.abc import Mapping
from datetime import datetime, timezone

from models.product import Product, PlatformListing
from models.company import Company
from models.brand import Brand
from services.database import now

SELECT_VARIANTS = '''SELECT v.*,p.name AS product_name,p.image_url,p.product_family,
 b.id AS brand_id,b.name AS brand,c.id AS company_id,c.name AS company,c.type,
 cat.name AS category FROM product_variants v JOIN products p ON p.id=v.product_id
 JOIN brands b ON b.id=p.brand_id JOIN companies c ON c.id=b.company_id
 JOIN categories cat ON cat.id=p.category_id'''


class Repository:
    def __init__(self, database, include_demo=False):
        self.database, self.include_demo = database, include_demo

    def products(self, kind=None, limit=None, offset=0, category=None, query=None):
        where, args = ['v.archived=0'], []
        if not self.include_demo:
            where.append("v.source_state<>'DEMO'")
        if kind:
            where.append('c.type=?')
            args.append(kind)
        if category:
            where.append('cat.name=?')
            args.append(category)
        if query:
            where.append('(p.name LIKE ? OR b.name LIKE ?)')
            args.extend(['%' + query + '%'] * 2)
        sql = SELECT_VARIANTS + ' WHERE ' + ' AND '.join(where) + ' ORDER BY v.id'
        if limit is not None:
            sql += ' LIMIT ? OFFSET ?'
            args.extend([limit, offset])
        return self.hydrate(self.database.rows(sql, args))

    def get(self, id):
        rows = self.database.rows(SELECT_VARIANTS + ' WHERE v.id=? AND v.archived=0', (id,))
        if not rows or (not self.include_demo and rows[0]['source_state'] == 'DEMO'):
            raise KeyError(id)
        return self.hydrate(rows)[0]

    def hydrate(self, rows):
        result = []
        # Batch listing reads to avoid a query per product; stay below SQLite parameter limits.
        listing_map = {}
        ids = [row['id'] for row in rows]
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            sql = '''SELECT rp.*,r.name AS platform,o.price,o.observed_at,o.source_state AS observation_source
              FROM retailer_products rp JOIN retailers r ON r.id=rp.retailer_id
              LEFT JOIN price_observations o ON o.id=(SELECT id FROM price_observations
              WHERE retailer_product_id=rp.id ORDER BY observed_at DESC,id DESC LIMIT 1)
              WHERE rp.product_variant_id IN (''' + ','.join('?' for _ in chunk) + ')'
            for item in self.database.rows(sql, chunk):
                listing_map.setdefault(item['product_variant_id'], []).append(item)
        for row in rows:
            listings, flags = [], set()
            observations = listing_map.get(row['id'], [])
            for item in observations:
                if not item['retailer_product_url']:
                    flags.add('MISSING_PRODUCT_URL')
                if item['collection_error']:
                    flags.add('COLLECTION_ERROR')
                if item['price'] is None:
                    flags.add('MISSING_PRICE')
                    continue  # Raw listing remains in /prices, even without an observation price.
                listings.append(PlatformListing(platform=item['platform'], platform_product_id=item['retailer_sku'],
                    product_name=item['retailer_product_name'], price=item['price'], product_url=item['retailer_product_url'],
                    image_url=item['image_url'], availability=item['availability'], last_updated=item['observed_at'],
                    data_source='demo' if item['observation_source'] == 'DEMO' else 'verified',
                    source_name=item['observation_source'], provenance=None if item['observation_source'] == 'DEMO' else 'LIVE' if item['observation_source'] == 'COLLECTED' else item['observation_source'],
                    collection_method='demo' if item['observation_source'] == 'DEMO' else 'live' if item['observation_source'] == 'COLLECTED' else 'feed', collection_error=item['collection_error']))
            if not observations:
                flags.update(['MISSING_PRICE', 'RETAILER_UNAVAILABLE', 'MISSING_PRODUCT_URL'])
            if not row['image_url'] and not any(item['image_url'] for item in observations):
                flags.add('MISSING_IMAGE')
            if row['normalized_quantity'] is None:
                flags.add('MISSING_QUANTITY')
            if any(item.data_status == 'STALE' for item in listings):
                flags.add('STALE_DATA')
            result.append(Product(id=row['id'], company=row['company'], company_id=row['company_id'], brand=row['brand'],
                brand_id=row['brand_id'], product_name=row['display_name'] or row['product_name'], category=row['category'], size=row['original_size'] or 'Unknown',
                barcode=row['barcode'] or '', currency='QAR', price=None, image_url=row['image_url'], subcategory=row['subcategory'],
                purpose=row['purpose'], variant=row['variant_name'], size_value=row['size_value'], unit=row['size_unit'],
                pack_quantity=row['pack_count'], attributes=json.loads(row['attributes']), listings=listings,
                source_state='VERIFIED' if row['verified'] else row['source_state'], quality_flags=sorted(flags),
                verified=bool(row['verified']), product_family=row['product_family'], updated_at=row['updated_at']))
        return result

    def companies(self):
        return {r['id']: Company(id=r['id'], name=r['name']) for r in self.database.rows('SELECT * FROM companies')}

    def brands(self):
        return {r['id']: Brand(id=r['id'], name=r['name'], company_id=r['company_id'], market_note='Catalogue ownership supplied by import; verification is tracked per variant.') for r in self.database.rows('SELECT * FROM brands')}

    def history(self, variant_id, limit=200, offset=0):
        self.get(variant_id)
        listings = self.database.rows('''SELECT rp.*,r.name AS retailer FROM retailer_products rp
            JOIN retailers r ON r.id=rp.retailer_id WHERE product_variant_id=?''', (variant_id,))
        for listing in listings:
            history = self.database.rows('SELECT * FROM price_observations WHERE retailer_product_id=? ORDER BY observed_at DESC,id DESC LIMIT ? OFFSET ?', (listing['id'], limit, offset))
            recent = self.database.rows('SELECT * FROM price_observations WHERE retailer_product_id=? ORDER BY observed_at DESC,id DESC LIMIT 2', (listing['id'],))
            bounds = self.database.rows('SELECT min(price) AS lowest,max(price) AS highest,count(*) AS count FROM price_observations WHERE retailer_product_id=?', (listing['id'],))[0]
            current = recent[0]['price'] if recent else None
            previous = recent[1]['price'] if len(recent) > 1 else None
            listing.update(history=history, latest_price=current, previous_price=previous, **bounds,
                           change_percent=(current - previous) / previous * 100 if current is not None and previous else None)
            listing['data_status'] = listing['source_state']
            if listing['collection_error']:
                listing['data_status'] = 'ERROR'
            elif listing['source_state'] != 'DEMO' and (datetime.now(timezone.utc) - datetime.fromisoformat(listing['last_seen_at'])).total_seconds() > (900 if listing['source_state'] == 'COLLECTED' else 86400):
                listing['data_status'] = 'STALE'
        return listings

    def archive(self, id):
        self.get(id)
        with self.database.connect() as db:
            db.execute('UPDATE product_variants SET archived=1,updated_at=? WHERE id=?', (now(), id))


class CatalogueView(Mapping):
    """Compatibility with existing services; all reads come from durable storage."""
    def __init__(self, repository, kind):
        self.repository, self.kind = repository, kind

    def __getitem__(self, id):
        product = self.repository.get(id)
        is_pg = product.company == 'P&G'
        if is_pg != (self.kind == 'pg'):
            raise KeyError(id)
        return product

    def __iter__(self):
        return iter(p.id for p in self.values())

    def __len__(self):
        return len(self.values())

    def values(self):
        return self.repository.products(kind=self.kind)

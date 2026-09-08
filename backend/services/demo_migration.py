"""Explicit development-only migration. Never run automatically against a populated database."""
import json
from services.database import ROOT
from services.catalogue import load_competitor_catalogue
from collectors.mock_data import DemoCollector
from models.product import Product
from services.imports import prepare, save_row


def migrate_demo(database):
    with database.connect() as db:
        if db.execute('SELECT 1 FROM product_variants LIMIT 1').fetchone():
            return {'skipped': True, 'reason': 'Database is already populated'}
        masters = {r['id']: Product(**r) for r in json.loads((ROOT / 'data' / 'demo_products.json').read_text())}
        for product in masters.values():
            product.listings = DemoCollector().collect(product)
        _, _, competitors = load_competitor_catalogue(masters)
        for product in [*masters.values(), *competitors.values()]:
            for listing in product.listings:
                raw = dict(company=product.company, brand=product.brand, category=product.category,
                           product_name=product.product_name, size=product.size_value, unit=product.unit,
                           pack_count=product.pack_quantity, barcode=product.barcode, subcategory=product.subcategory,
                           purpose=product.purpose, variant_name=product.variant, attributes=product.attributes,
                           retailer=listing.platform, retailer_sku=listing.platform_product_id, price=listing.price,
                           availability=listing.availability, observed_at=listing.last_updated.isoformat())
                row = prepare(raw, 'pg' if product.company == 'P&G' else 'competitor', 'DEMO')
                row['size'] = product.size
                save_row(db, row, 'demo-migration-v1', forced_id=product.id)
    return {'imported': 9, 'source_state': 'DEMO'}

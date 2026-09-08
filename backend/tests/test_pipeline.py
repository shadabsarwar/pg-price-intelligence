import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from collectors.retailers.base_retailer import RetailerProduct, RetailerSearchResult
from pipeline_api import make_router
from services.collection_jobs import CollectionJobs
from services.database import Database
from services.imports import Importer, read_rows
from services.matches import MatchService, candidate_score
from services.normalization import clean, normalized_name, parse_quantity
from services.price_normalization import normalize_price
from services.repository import Repository


def row(**changes):
    return dict(company='P&G', brand='Test Brand', category='Laundry', product_name='Test Brand Liquid',
                product_family='Liquid', size='2 L', variant_name='Original', subcategory='Liquid detergent',
                purpose='Machine laundry', attributes={'form': 'liquid', 'concentration': 'standard'}) | changes


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Database(Path(self.tmp.name) / 'catalogue.db')
        self.repo = Repository(self.db)
        self.importer = Importer(self.db)
        self.matches = MatchService(self.repo)

    def test_empty_production_and_restart(self):
        self.assertEqual(self.repo.products(), [])
        self.assertEqual(self.importer.run([row()])['imported'], 1)
        reopened = Repository(Database(self.db.path))
        self.assertEqual(len(reopened.products()), 1)
        self.assertIsNone(reopened.products()[0].price)
        self.assertEqual(reopened.products()[0].source_state, 'IMPORTED')

    def test_normalization(self):
        self.assertEqual(clean('  LIQUID—Soap!  '), 'liquid soap')
        self.assertEqual(normalized_name('TEST Brand: Soap', 'Test Brand'), 'soap')
        self.assertEqual(parse_quantity('2000 ml')[3:], parse_quantity('2 litres')[3:])
        self.assertEqual(parse_quantity('1000 g')[3:], parse_quantity('1 kg')[3:])
        self.assertEqual(parse_quantity('2 × 500 ml'), (500, 'ml', 2, 1, 'L'))
        self.assertEqual(parse_quantity('48 diapers')[3:], (48, 'diaper'))
        for size in ('Size 4', '0 ml', '-1 L', 'NaN kg', '100000 x 20 L'):
            with self.subTest(size=size), self.assertRaises(ValueError):
                parse_quantity(size)
        with self.assertRaises(ValueError):
            parse_quantity('2 x 500 ml', pack_count=3)
        self.assertIsNone(parse_quantity(''))

    def test_equivalent_units_deduplicate_but_multipacks_do_not(self):
        summary = self.importer.run([row(), row(size='2000 ml'), row(size='2 x 1000 ml')])
        self.assertEqual(summary['imported'], 2)
        self.assertEqual(len(self.db.rows('SELECT * FROM products')), 1)
        self.assertEqual(len(self.repo.products()), 2)
        self.assertEqual(len(self.db.rows('SELECT * FROM product_variants')), 2)

    def test_row_errors_dry_run_and_no_empty_overwrite(self):
        bad = row(brand='')
        dry = self.importer.run([row(), bad], dry_run=True)
        self.assertEqual((dry['imported'], len(dry['errors'])), (1, 1))
        self.assertEqual(self.repo.products(), [])
        self.assertEqual(len(self.db.rows('SELECT * FROM import_errors')), 1)
        self.importer.run([row(image_url='https://example.com/image.jpg', barcode='TEST-1')])
        result = self.importer.run([row(image_url='', barcode=''), bad])
        self.assertEqual(result['skipped'], 1)
        product = self.repo.products()[0]
        self.assertEqual(product.barcode, 'TEST-1')
        self.assertEqual(product.image_url, 'https://example.com/image.jpg')
        self.assertEqual(len(self.db.rows('SELECT * FROM companies')), 1)

    def test_validation_and_partial_import(self):
        invalids = [row(price=value, retailer='Test Qatar', retailer_sku='x') for value in [0, -1, 'nan', 'inf']]
        invalids += [row(currency='USD'), row(product_url='javascript:alert(1)'), row(company='Other'),
                     row(country='US'), row(country=123), row(unit=123), row(size='5 nonsense'), row(price=10), row(retailer='No SKU'), row(attributes='[]')]
        result = self.importer.run([*invalids, row()])
        self.assertEqual(len(result['errors']), len(invalids))
        self.assertEqual(result['imported'], 1)

    def test_duplicate_barcode_and_retailer_collision_rollback(self):
        self.importer.run([row(barcode='TEST-1', retailer='Test Qatar', retailer_sku='sku-1', price=20)])
        result = self.importer.run([row(size='1L', barcode='TEST-1'), row(size='3L', retailer='Test Qatar', retailer_sku='sku-1', price=30)])
        self.assertEqual(len(result['errors']), 2)
        self.assertEqual(len(self.repo.products()), 1)
        self.assertEqual(len(self.db.rows('SELECT * FROM price_observations')), 1)

    def test_manufacturer_sku_and_attribute_conflicts(self):
        self.importer.run([row(sku='SKU-1')])
        result = self.importer.run([row(sku='SKU-1', size='1L'), row(attributes={'form': 'powder'})])
        self.assertEqual(len(result['errors']), 2)
        self.assertEqual(len(self.repo.products()), 1)

    def test_demo_metadata_does_not_leak_into_real_product(self):
        self.importer.run([row(image_url='https://example.com/demo.jpg')], source='DEMO')
        self.importer.run([row()])
        product = self.repo.products()[0]
        self.assertIsNone(product.image_url)
        self.assertEqual(product.product_name, 'Test Brand Liquid')
        self.assertEqual(len(self.db.rows('SELECT * FROM import_rows')), 2)

    def test_approved_possible_candidate_is_visible_without_invented_unit_price(self):
        from services.market_analysis import analyze_market
        self.importer.run([row()])
        self.importer.run([row(company='Other', brand='Other Brand', size='')], kind='competitor')
        master, candidate = self.repo.products('pg')[0], self.repo.products('competitor')[0]
        self.assertEqual(analyze_market(master, [candidate], self.repo.companies()).competitors, [])
        reviewed = analyze_market(master, [candidate], self.repo.companies(), {candidate.id})
        self.assertEqual(len(reviewed.competitors), 1)
        self.assertFalse(reviewed.competitors[0].comparable_prices)
        self.assertIsNone(reviewed.competitors[0].normalized_price)

    def test_history_idempotence_backfill_missing_and_immutability(self):
        t1 = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        t2 = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        base = row(retailer='Test Qatar', retailer_sku='item', price=20, availability='available', observed_at=t1)
        self.importer.run([base])
        product = self.repo.products()[0]
        self.importer.run([base])
        self.assertEqual(self.repo.history(product.id)[0]['count'], 1)
        self.importer.run([base | {'price': 22, 'observed_at': t2}])
        history = self.repo.history(product.id)[0]
        self.assertEqual((history['latest_price'], history['previous_price'], history['lowest'], history['highest']), (22, 20, 20, 22))
        self.assertAlmostEqual(history['change_percent'], 10)
        self.importer.run([base | {'price': 15, 'observed_at': (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()}])
        self.assertEqual(self.repo.history(product.id)[0]['latest_price'], 22)
        self.importer.run([base | {'price': '', 'observed_at': datetime.now(timezone.utc).isoformat()}])
        self.assertIsNone(self.repo.history(product.id)[0]['latest_price'])
        self.assertIn('MISSING_PRICE', self.repo.get(product.id).quality_flags)
        for command in ('UPDATE price_observations SET price=1', 'DELETE FROM price_observations'):
            with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as db:
                db.execute(command)

    def test_duplicate_without_timestamp_does_not_refresh_listing(self):
        base = row(retailer='Test Qatar', retailer_sku='item', price=20)
        self.importer.run([base])
        before = self.db.rows('SELECT * FROM retailer_products')[0]['last_seen_at']
        result = self.importer.run([base])
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(self.db.rows('SELECT * FROM retailer_products')[0]['last_seen_at'], before)

    def test_source_isolation_stale_and_missing_flags(self):
        self.importer.run([row()], source='DEMO')
        self.assertEqual(self.repo.products(), [])
        self.importer.run([row(size='')])
        product = self.repo.products()[0]
        self.assertTrue({'MISSING_QUANTITY', 'MISSING_IMAGE', 'MISSING_PRICE', 'RETAILER_UNAVAILABLE'} <= set(product.quality_flags))
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        self.importer.run([row(retailer='Test Qatar', retailer_sku='1', price=10, observed_at=old)])
        self.assertIn('STALE_DATA', self.repo.products()[-1].quality_flags)

    def test_unit_price(self):
        self.importer.run([row()])
        product = self.repo.products()[0]
        self.assertEqual(normalize_price(product, 20), (10, 'L'))
        self.assertEqual(normalize_price(product.model_copy(update={'category': 'Personal care'}), 20), (1, '100 ml'))
        self.assertEqual(normalize_price(product.model_copy(update={'unit': 'diaper', 'size_value': 1, 'pack_quantity': 48}), 48), (1, 'diaper'))

    def test_matching_persistence_rejection_and_review_candidates(self):
        self.importer.run([row()])
        self.importer.run([row(company='Other', brand='Other Brand'), row(company='Other', brand='Other Brand', variant_name='Incomplete', size='')], kind='competitor')
        result = self.matches.recalculate()
        self.assertEqual(result['relationships'], 2)
        rows = self.matches.relationships()
        self.assertEqual(rows[0]['match_score'], 1)
        self.assertEqual(rows[1]['relationship_type'], 'possible')
        self.matches.review(rows[0]['source_product_variant_id'], rows[0]['competitor_product_variant_id'], 'rejected')
        self.matches.recalculate()
        self.assertEqual(self.matches.relationships()[0]['review_status'], 'rejected')
        product = self.repo.products('pg')[0]
        candidate = self.repo.products('competitor')[0]
        self.assertIsNone(candidate_score(product, candidate.model_copy(update={'attributes': {'form': 'powder'}})))

    def test_csv_json_import_and_large_catalogue(self):
        content = 'company,brand,category,product_name,size\nP&G,Test Brand,Laundry,Liquid,2 L\n'
        self.assertEqual(self.importer.run(read_rows(content, 'csv'))['imported'], 1)
        self.assertEqual(len(read_rows(json.dumps([row()]), 'json')), 1)
        result = self.importer.run((row(variant_name=f'Variant {i}') for i in range(1000)))
        self.assertEqual(result['imported'], 1000)
        self.assertEqual(len(self.repo.products(limit=10, offset=1000)), 1)

    def test_connector_failures_and_durable_jobs(self):
        class Broken:
            platform = 'Test Qatar'
            def search(self, query):
                raise RuntimeError('SECRET URL must not leak')
        class Unavailable:
            platform = 'Other Qatar'
            def search(self, query):
                return RetailerSearchResult(platform=self.platform, reason='No approved feed configured')
        jobs = CollectionJobs(self.repo, {'broken': Broken(), 'unavailable': Unavailable()}, self.matches)
        jobs.enqueue(['broken', 'unavailable'], 'detergent')
        jobs.process(jobs.claim())
        jobs.process(jobs.claim())
        runs = self.db.rows('SELECT * FROM data_collection_runs ORDER BY rowid')
        self.assertEqual([r['status'] for r in runs], ['ERROR', 'UNAVAILABLE'])
        self.assertNotIn('SECRET', json.dumps(runs))
        self.assertEqual(len(self.db.rows('SELECT * FROM data_collection_errors')), 2)
        self.assertEqual(self.repo.products(), [])

    def test_discovery_keeps_unknown_identity_and_partial_results(self):
        class Feed:
            platform = 'Test Qatar'
            def search(self, query):
                timestamp = datetime.now(timezone.utc)
                base = dict(platform=self.platform, product_name='Test Liquid', current_price=20, product_size='2 L',
                            data_status='LIVE', collected_at=timestamp, source_type='approved_feed')
                return RetailerSearchResult(platform=self.platform, data_status='LIVE', collected_at=timestamp, products=[
                    RetailerProduct(**base, brand='Test Brand', company='P&G', product_url='https://example.com/1'),
                    RetailerProduct(**base, product_url='https://example.com/2')])
        jobs = CollectionJobs(self.repo, {'test': Feed()}, self.matches)
        jobs.enqueue(['test'], 'liquid', {'category': 'Laundry'})
        jobs.process(jobs.claim())
        run = self.db.rows('SELECT * FROM data_collection_runs')[0]
        self.assertEqual((run['status'], run['records_found'], run['records_saved']), ('PARTIAL', 2, 1))
        self.assertEqual(len(self.db.rows('SELECT * FROM discoveries')), 2)
        self.assertEqual(self.repo.products()[0].source_state, 'COLLECTED')
        jobs.enqueue(['test'], 'liquid', {'category': 'Laundry'})
        jobs.process(jobs.claim())
        self.assertEqual(len(self.db.rows('SELECT * FROM price_observations')), 2)

    def test_admin_api_and_archive_retains_history(self):
        jobs = CollectionJobs(self.repo, {}, self.matches)
        app = FastAPI()
        app.include_router(make_router(self.repo, self.importer, jobs, self.matches))
        client = TestClient(app)
        with patch.dict(os.environ, {'INTELLIGENCE_ADMIN_TOKEN': 'test-token'}):
            payload = {'format': 'json', 'content': json.dumps([row()]), 'dry_run': False}
            self.assertEqual(client.post('/imports/products', json=payload).status_code, 401)
            response = client.post('/imports/products', json=payload, headers={'X-Admin-Token': 'test-token'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['imported'], 1)
            product = self.repo.products()[0]
            self.assertEqual(client.get(f'/products/{product.id}/prices').status_code, 200)
            self.assertEqual(client.get('/products/999/prices').status_code, 404)
            self.assertEqual(client.get('/quality').json()[0]['id'], product.id)
        self.repo.archive(product.id)
        self.assertEqual(self.repo.products(), [])
        self.assertEqual(len(self.db.rows('SELECT * FROM product_variants')), 1)

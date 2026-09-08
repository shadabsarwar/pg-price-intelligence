import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

import main
from collectors.base import BaseCollector
from models.product import PlatformListing
from services.market_analysis import analyze_market, difference
from services.market_refresh import MarketRefresher
from services.price_normalization import normalize_price
from services.product_matching import match_products


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.ariel = main.products[1].model_copy(deep=True)
        self.persil = main.competitors[1001].model_copy(deep=True)

    def test_confidence_and_equivalence(self):
        self.assertEqual(match_products(self.ariel, self.persil)["confidence"], 100)
        self.assertEqual(match_products(self.ariel, main.competitors[1002])["confidence"], 95)
        self.assertEqual(match_products(self.ariel, main.competitors[1003])["confidence"], 92.5)
        for changes in ({"company": "P&G"}, {"brand": "Ariel"}, {"subcategory": "Powder"},
                        {"purpose": "Dish washing"}, {"unit": "kg"}, {"pack_quantity": None},
                        {"attributes": {"form": "liquid", "concentration": "concentrated"}},
                        {"size_value": 100}):
            self.assertIsNone(match_products(self.ariel, self.persil.model_copy(update=changes)))

    def test_no_diaper_size_or_razor_type_false_matches(self):
        diapers = main.competitors[1004].model_copy(deep=True)
        diapers.attributes["diaper_size"] = "3"
        self.assertIsNone(match_products(main.products[2], diapers))
        razor = main.competitors[1006].model_copy(deep=True)
        razor.attributes["razor_type"] = "disposable"
        self.assertIsNone(match_products(main.products[3], razor))

    def test_normalization_and_missing_quantities(self):
        self.assertEqual(normalize_price(self.ariel, 25), (12.5, "L"))
        self.assertEqual(normalize_price(main.competitors[1003], 40), (10, "L"))
        shampoo = self.ariel.model_copy(update={"subcategory": "Shampoo", "size_value": 400, "unit": "ml"})
        self.assertEqual(normalize_price(shampoo, 20), (5, "100 ml"))
        powder = self.ariel.model_copy(update={"size_value": 500, "unit": "g", "pack_quantity": 2})
        self.assertEqual(normalize_price(powder, 15), (15, "kg"))
        self.assertEqual(normalize_price(main.products[2], 48), (1, "diaper"))
        self.assertEqual(normalize_price(main.products[3], 10), (10, "razor"))
        self.assertEqual(normalize_price(self.ariel.model_copy(update={"pack_quantity": None}), 10), (None, None))

    def test_market_unit_rank_and_differences(self):
        result = analyze_market(self.ariel, list(main.competitors.values()), main.companies)
        self.assertEqual(len(result.competitors), 3)
        bulk = next(item for item in result.competitors if item.product.id == 1003)
        self.assertEqual(bulk.normalized_price, 10)
        self.assertIn("Best value per unit", bulk.highlights)
        self.assertGreater(bulk.price_difference, 0)
        self.assertLess(bulk.normalized_difference, 0)
        self.assertAlmostEqual(result.market_position.market_average, (12.5 + 11.75 + 10) / 3, places=5)
        self.assertEqual(difference(1, 0), (1, None))

    def test_source_and_currency_isolation(self):
        for row in self.persil.listings:
            row.data_source = "verified"
            row.collection_method = "feed"
        result = analyze_market(self.ariel, [self.persil], main.companies)
        self.assertFalse(result.competitors[0].comparable_prices)
        self.assertIsNone(result.competitors[0].percentage_difference)
        self.assertEqual(result.market_position.comparable_competitor_count, 0)
        self.persil.currency = "USD"
        result = analyze_market(self.ariel, [self.persil], main.companies)
        self.assertFalse(result.competitors[0].comparable_prices)

    def test_data_status_and_stale_price_exclusion(self):
        row = self.persil.listings[0]
        self.assertEqual(row.data_status, "DEMO")
        row.data_source = "verified"
        row.collection_method = "feed"
        self.assertEqual(row.data_status, "VERIFIED")
        row.collection_method = "live"
        self.assertEqual(row.data_status, "LIVE")
        row.last_updated = datetime.now(timezone.utc) - timedelta(hours=1)
        self.assertEqual(row.data_status, "STALE")
        result = analyze_market(self.ariel, [self.persil], main.companies)
        self.assertIsNone(result.competitors[0].best_price)
        row.collection_error = "Feed failed"
        self.assertEqual(row.data_status, "ERROR")


class IntelligenceApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_and_not_found(self):
        self.assertEqual(len(await main.get_competitor_catalogue()), 6)
        for product_id, expected in ((1, 3), (2, 2), (3, 1)):
            self.assertEqual(len(await main.get_product_competitors(product_id)), expected)
            result = await main.get_competitor_comparison(product_id)
            self.assertEqual(result.data_status, "DEMO")
            self.assertTrue(result.competitor_companies)
        for endpoint in (main.get_competitor_comparison, main.get_product_competitors, main.get_market_position):
            with self.assertRaises(HTTPException) as raised:
                await endpoint(999999)
            self.assertEqual(raised.exception.status_code, 404)

    async def test_collector_failure_retains_last_observation(self):
        class Adapter(BaseCollector):
            enabled = True
            platform = "Approved test feed"
            fail = False

            def collect(self, product):
                if self.fail:
                    raise RuntimeError("Test network failure")
                return [PlatformListing(platform=self.platform, platform_product_id="TEST", product_name=product.product_name,
                                        price=10, availability="available", last_updated=datetime.now(timezone.utc),
                                        data_source="verified", collection_method="feed", source_name="Test only")]
        product = main.products[1].model_copy(deep=True)
        adapter = Adapter()
        service = MarketRefresher([adapter])
        await service.refresh([product])
        row = product.listings[-1]
        self.assertEqual(row.price, 10)
        timestamp = row.last_updated
        adapter.fail = True
        await service.refresh([product])
        self.assertEqual(product.listings[-1].last_updated, timestamp)
        self.assertEqual(product.listings[-1].data_status, "ERROR")
        self.assertEqual(service.statuses[adapter.platform]["status"], "ERROR")


if __name__ == "__main__":
    unittest.main()

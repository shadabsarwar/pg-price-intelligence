"""Synthetic transport doubles ONLY; no retailer requests or real-data claims."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import Response
from pydantic import ValidationError

import main
from collectors.base import CollectorSearchRequest, RetailerListing
from collectors.lulu_qatar import ApprovedLuluSource, LuluQatarCollector
from services.lulu_collection import LuluCollectionService, valid_gtin


class TestSource(ApprovedLuluSource):
    permission_reference = "TEST DOUBLE ONLY - not retailer permission"
    source_reference = "TEST DOUBLE ONLY - no network"

    def search(self, query):
        self.retailer_requests += 1  # Synthetic request counter; this double makes no network calls.
        return [RetailerListing(platform_product_id="TEST-ONLY", product_name="Synthetic Ariel test",
                                brand="Ariel", current_price=20, currency="QAR",
                                product_url="https://gcc.luluhypermarket.com/en-qa/test-only/",
                                image_url="https://example.com/test-only.png", availability="available",
                                source_platform="LuLu Qatar", collected_at=datetime.now(timezone.utc))]


class LuluTests(unittest.TestCase):
    def test_default_blocked_no_network_no_success(self):
        collector = LuluQatarCollector()
        with patch("urllib.request.urlopen", side_effect=AssertionError("Network must not run")):
            result = collector.search("Ariel Liquid Detergent")
        self.assertEqual(result.data_status, "ERROR")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "APPROVED_SOURCE_REQUIRED")
        self.assertEqual(result.retailer_requests, 0)
        self.assertIn("No live collection was attempted", result.message)
        self.assertEqual(result.listings, [])
        self.assertIsNone(result.collected_at)
        self.assertEqual({error.code for error in result.errors}, {"PERMISSION_REQUIRED", "ROBOTS_RESTRICTED", "APPROVED_SOURCE_MISSING"})
        self.assertIsNone(collector.status().last_successful_collection)
        self.assertEqual(collector.status().number_of_products_collected, 0)

    def test_query_validation(self):
        self.assertEqual(CollectorSearchRequest(query=" Ariel   detergent ").query, "Ariel detergent")
        for query in (" ", "a", "a" * 201):
            with self.assertRaises(ValidationError):
                CollectorSearchRequest(query=query)

    def test_injected_test_transport_validation_and_cooldown(self):
        collector = LuluQatarCollector(TestSource())
        success = collector.search("test")
        self.assertEqual(success.listings_found, 1)
        self.assertTrue(success.success)
        self.assertEqual(success.retailer_requests, 1)
        limited = collector.search("test")
        self.assertEqual(limited.errors[0].code, "RATE_LIMITED")
        self.assertEqual(limited.retailer_requests, 0)
        self.assertEqual(collector.status().retailer_requests, 1)
        self.assertEqual(collector.status().number_of_products_collected, 1)

    def test_repeated_blocked_attempts_never_increment_retailer_requests(self):
        collector = LuluQatarCollector()
        for _ in range(3):
            collector.search("Ariel")
        state = collector.status()
        self.assertEqual(state.status, "UNAVAILABLE")
        self.assertEqual(state.data_access_status, "APPROVED_SOURCE_REQUIRED")
        self.assertEqual(state.retailer_requests, 0)
        self.assertIsNone(state.last_successful_collection)
        self.assertIsNotNone(state.last_attempt_at)
        self.assertEqual(state.platform, "LuLu Qatar")

    def test_failure_keeps_last_success_and_counts_only_transport_requests(self):
        source = TestSource()
        collector = LuluQatarCollector(source)
        collector.search("test")
        last_success = collector.status().last_successful_collection
        collector._last_request = None
        def fail(query):
            source.retailer_requests += 1
            raise RuntimeError("Synthetic transport failure")
        source.search = fail
        result = collector.search("test")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "SOURCE_ERROR")
        self.assertEqual(result.retailer_requests, 1)
        self.assertEqual(collector.status().retailer_requests, 2)
        self.assertEqual(collector.status().last_successful_collection, last_success)
        self.assertEqual(collector.status().data_access_status, "APPROVED")

    def test_wrong_market_and_old_observations_rejected(self):
        for change in ({"product_url": "https://example.com/en-qa/test/"},
                       {"currency": "AED"}, {"collected_at": datetime.now(timezone.utc) - timedelta(days=1)}):
            source = TestSource()
            original = source.search
            source.search = lambda query, change=change: [original(query)[0].model_dump() | change]
            result = LuluQatarCollector(source).search("test")
            self.assertEqual(result.data_status, "ERROR")
            self.assertEqual(result.listings_found, 0)

    def test_empty_or_failed_transport_never_claims_live(self):
        source = TestSource()
        source.search = lambda query: []
        collector = LuluQatarCollector(source)
        self.assertEqual(collector.search("test").data_status, "ERROR")
        self.assertIsNone(collector.status().last_successful_collection)

    def test_integration_preserves_demo_and_updates_exact_binding(self):
        collector = LuluQatarCollector(TestSource())
        product = main.products[1].model_copy(deep=True)
        service = LuluCollectionService(collector, {"TEST-ONLY": product.id})
        result = service.integrate(collector.search("test"), [product])
        self.assertEqual(result.integrated_count, 1)
        self.assertEqual(sum(row.data_source == "demo" for row in product.listings), 3)
        self.assertEqual(product.listings[-1].price, 20)
        self.assertEqual(product.image_url, "https://example.com/test-only.png")
        timestamp = product.listings[-1].last_updated
        failure = LuluQatarCollector().search("test")
        service.integrate(failure, [product])
        self.assertEqual(product.listings[-1].last_updated, timestamp)
        self.assertEqual(product.listings[-1].data_status, "ERROR")
        self.assertTrue(all(row.data_status == "DEMO" for row in product.listings if row.data_source == "demo"))

    def test_similar_name_does_not_attach_without_identity(self):
        collector = LuluQatarCollector(TestSource())
        product = main.products[1].model_copy(deep=True)
        result = LuluCollectionService(collector).integrate(collector.search("Ariel"), [product])
        self.assertEqual(result.integrated_count, 0)
        self.assertEqual(result.unmatched_count, 1)
        self.assertEqual(len(product.listings), 3)
        self.assertFalse(valid_gtin("DEMO-ARIEL-001"))
        self.assertTrue(valid_gtin("4006381333931"))


class LuluApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_blocked_status_shape(self):
        response = Response()
        result = await main.search_lulu(CollectorSearchRequest(query="Ariel Liquid Detergent"), response)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(result.data_status, "ERROR")
        state = next(item for item in main.get_collector_status() if item.connector_name == "lulu_qatar")
        self.assertEqual(state.status, "UNAVAILABLE")
        self.assertIsNone(state.last_successful_collection)
        for connector in main.get_collector_status():
            payload = connector.model_dump()
            for key in ("connector_name", "platform", "status", "data_access_status", "last_successful_collection", "retailer_requests", "reason"):
                self.assertIn(key, payload)
            self.assertEqual(connector.status, "UNAVAILABLE")
            self.assertEqual(connector.data_access_status, "APPROVED_SOURCE_REQUIRED")
            self.assertEqual(connector.retailer_requests, 0)


if __name__ == "__main__":
    unittest.main()


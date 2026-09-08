import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

import main
from collectors.providers.base_provider import FetchResult
from collectors.providers.scraperapi_provider import ProviderError
from collectors.retailers.base_retailer import RetailerSearchResult
from models.product import PlatformListing
from services.live_comparison import build_live_comparison
from services.provider_test import ProviderTestService, safe_preview


class LiveCollectionTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"APPROVED_RETAILER_DOMAINS": "httpbin.org"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_test_endpoint_metadata_preview_and_cooldown(self):
        service = ProviderTestService()
        observed = datetime.now(timezone.utc)
        result = FetchResult(200, "https://httpbin.org/html", observed, b"<h1>synthetic-test-only</h1>")
        with patch.object(main, "public_test_service", service), patch.object(service.provider, "fetch_result", return_value=result) as fetch:
            client = TestClient(main.app)
            response = client.post("/collectors/test", json={"url": "https://httpbin.org/html"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status_code"], 200)
            self.assertEqual(response.json()["source_url"], result.source_url)
            self.assertEqual(response.json()["content_preview"], "synthetic-test-only")
            self.assertIsNotNone(response.json()["fetched_at"])
            response = client.post("/collectors/test", json={"url": "https://httpbin.org/html"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.headers["retry-after"], "60")
            self.assertEqual(fetch.call_count, 1)

    def test_unreviewed_private_and_credential_urls_rejected_without_network(self):
        service = ProviderTestService()
        with patch.object(service.provider, "fetch_result") as fetch:
            for url in ["http://127.0.0.1", "http://169.254.169.254/", "file:///etc/passwd",
                        "https://httpbin.org/html?api_key=synthetic-secret", "https://user:password@httpbin.org/html",
                        "https://gcc.luluhypermarket.com/en-qa/search/"]:
                response, status = service.test(url)
                self.assertEqual(status, 403)
                self.assertIsNone(response.source_url)
                self.assertNotIn("synthetic-secret", response.model_dump_json())
            fetch.assert_not_called()

    def test_errors_and_missing_final_url_do_not_claim_success(self):
        for code, status in [("INVALID_API_KEY", 502), ("PROVIDER_TIMEOUT", 504),
                             ("NETWORK_FAILURE", 502), ("MISSING_API_KEY", 503), ("RATE_LIMITED", 429)]:
            service = ProviderTestService()
            with patch.object(service.provider, "fetch_result", side_effect=ProviderError(code, 401 if code == "INVALID_API_KEY" else None)):
                result, http_status = service.test("https://httpbin.org/html")
                self.assertEqual(http_status, status)
                self.assertFalse(result.success)
                self.assertEqual(result.content_preview, "")
        service = ProviderTestService()
        with patch.object(service.provider, "fetch_result", return_value=FetchResult(200, None, datetime.now(timezone.utc), b"test")):
            result, status = service.test("https://httpbin.org/html")
            self.assertEqual(status, 502)
            self.assertIsNone(result.source_url)
            self.assertFalse(result.success)

    def test_preview_redacts_before_truncation(self):
        with patch.dict(os.environ, {"SCRAPERAPI_KEY": "synthetic-secret"}):
            preview = safe_preview(b"<script>hidden</script><p>synthetic-secret</p>" + b"x" * 1000)
            self.assertNotIn("synthetic-secret", preview)
            self.assertNotIn("hidden", preview)
            self.assertLessEqual(len(preview), 300)

    def test_retailer_routes_unavailable_no_network(self):
        with patch("collectors.providers.scraperapi_provider.build_opener") as network:
            client = TestClient(main.app)
            for retailer in ["lulu_qatar", "carrefour_qatar", "noon_qatar"]:
                response = client.post(f"/collectors/{retailer}/search", json={"query": "Ariel Liquid Detergent"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["data_status"], "UNAVAILABLE")
                self.assertTrue(response.json()["reason"])
                self.assertEqual(response.json()["products"], [])
                self.assertIsNone(response.json()["collected_at"])
            network.assert_not_called()
            self.assertEqual(client.post("/collectors/unknown/search", json={"query": "Ariel"}).status_code, 404)
            self.assertEqual(client.post("/collectors/lulu_qatar/search", json={"query": " "}).status_code, 422)

    def test_live_comparison_excludes_demo_and_keeps_legacy(self):
        client = TestClient(main.app)
        before = client.get("/products/1/competitor-comparison").json()
        response = client.get("/products/1/live-comparison")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data_status"], "UNAVAILABLE")
        self.assertEqual(response.json()["pg_product"]["offers"], [])
        self.assertEqual(response.json()["competitor_products"], [])
        self.assertEqual(client.get("/products/1/competitor-comparison").json(), before)
        self.assertEqual(client.get("/products/999999/live-comparison").status_code, 404)

    def test_live_and_stale_observation_timestamps_preserved(self):
        product = main.products[1].model_copy(deep=True)
        observed = datetime.now(timezone.utc)
        row = PlatformListing(platform="Synthetic test platform", platform_product_id="TEST-ONLY",
            product_name="Synthetic test", price=10, last_updated=observed,
            data_source="verified", collection_method="live")
        product.listings.append(row)
        result = build_live_comparison(product, [], [])
        self.assertEqual(result["data_status"], "LIVE")
        self.assertEqual(len(result["pg_product"]["offers"]), 1)
        self.assertEqual(result["collected_at"], observed)
        row.last_updated = observed - timedelta(hours=1)
        result = build_live_comparison(product, [], [])
        self.assertEqual(result["data_status"], "STALE")
        self.assertEqual(result["collected_at"], row.last_updated)

    def test_live_requires_observations(self):
        with self.assertRaises(ValidationError):
            RetailerSearchResult(platform="Synthetic", data_status="LIVE")
        with self.assertRaises(ValidationError):
            RetailerSearchResult(platform="Synthetic", data_status="UNAVAILABLE")

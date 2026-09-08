import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from fastapi.testclient import TestClient

import main
from config import load_environment
from collectors.scraperapi import NoRedirects, ProviderError, ScraperAPIProvider


class ScraperAPITests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"SCRAPERAPI_KEY": "synthetic-secret-only", "APPROVED_RETAILER_DOMAINS": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = ScraperAPIProvider()

    def test_environment_loading_and_process_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('SCRAPERAPI_KEY="file-test-${UNCHANGED}"\n', encoding="utf-8-sig")
            load_environment(path)
            self.assertEqual(os.environ["SCRAPERAPI_KEY"], "synthetic-secret-only")
            del os.environ["SCRAPERAPI_KEY"]
            load_environment(path)
            self.assertEqual(os.environ["SCRAPERAPI_KEY"], "file-test-${UNCHANGED}")

    def test_http_status_no_network_or_secret_and_demo_preserved(self):
        client = TestClient(main.app)
        before = client.get("/products").json()
        with patch("collectors.providers.scraperapi_provider.build_opener") as network:
            result = client.get("/collectors/providers/status")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), {"provider": "ScraperAPI", "configured": True, "status": "READY",
                "api_key_available": True, "approved_domain_count": 0, "source_configuration_status": "EMPTY"})
            os.environ["SCRAPERAPI_KEY"] = "  "
            self.assertEqual(client.get("/collectors/providers/status").json()["status"], "NOT_CONFIGURED")
            network.assert_not_called()
        self.assertEqual(client.get("/products").json(), before)
        self.assertEqual(main.lulu_collector.status().status, "UNAVAILABLE")

    def test_missing_key_no_request(self):
        os.environ["SCRAPERAPI_KEY"] = ""
        with patch("collectors.providers.scraperapi_provider.build_opener") as network:
            with self.assertRaises(ProviderError) as caught:
                self.provider.verify_account()
            self.assertEqual(caught.exception.code, "MISSING_API_KEY")
            network.assert_not_called()

    def test_network_errors_are_structured_and_logs_redacted(self):
        cases = [(HTTPError("secret-url", status, "synthetic-secret-only", {}, io.BytesIO()), code)
                 for status, code in [(401, "INVALID_API_KEY"), (403, "CREDITS_EXHAUSTED"),
                                      (429, "RATE_LIMITED"), (500, "PROVIDER_ERROR"), (504, "PROVIDER_TIMEOUT")]]
        cases += [(TimeoutError("synthetic-secret-only"), "PROVIDER_TIMEOUT"),
                  (URLError(TimeoutError()), "PROVIDER_TIMEOUT"),
                  (URLError("synthetic-secret-only"), "NETWORK_FAILURE"),
                  (OSError("synthetic-secret-only"), "NETWORK_FAILURE")]
        for error, code in cases:
            with self.subTest(code=code), patch("collectors.providers.scraperapi_provider.build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertLogs("uvicorn.error.scraperapi") as logs, self.assertRaises(ProviderError) as caught:
                    self.provider.verify_account()
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("synthetic-secret-only", str(logs.output) + json.dumps(caught.exception.as_dict()))
                self.assertEqual(opener.return_value.open.call_count, 1)

    def response(self, body):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.headers = {}
        response.__enter__.return_value.read.return_value = body
        return response

    def test_account_success_and_invalid_responses(self):
        with patch("collectors.providers.scraperapi_provider.build_opener") as opener:
            opener.return_value.open.return_value = self.response(b'{"requestCount": 0, "concurrentRequests": 0, "apiKey": "synthetic-secret-only"}')
            self.assertEqual(self.provider.verify_account()["status"], "AUTHENTICATED")
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 8)
            for body in (b"not json", b"{}", b"[]", b"x" * (self.provider.max_response_bytes + 1)):
                opener.return_value.open.return_value = self.response(body)
                with self.assertRaises(ProviderError) as caught:
                    self.provider.verify_account()
                self.assertEqual(caught.exception.code, "INVALID_RESPONSE")

    def test_default_denies_retailer_without_request(self):
        with patch("collectors.providers.scraperapi_provider.build_opener") as network:
            with self.assertRaises(ProviderError) as caught:
                self.provider.fetch("https://gcc.luluhypermarket.com/en-qa/search/?q=Ariel")
            self.assertEqual(caught.exception.code, "APPROVED_SOURCE_REQUIRED")
            network.assert_not_called()

    def test_reviewed_transport_stops_on_challenge(self):
        url = "https://example.com/test-only"
        provider = ScraperAPIProvider(frozenset({url}))
        with patch("collectors.providers.scraperapi_provider.build_opener") as opener, \
             patch("collectors.providers.scraperapi_provider.public_access_guard.check"), \
             patch("collectors.source_policy.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.215.14", 443))]):
            opener.return_value.open.return_value = self.response(b"<html>CAPTCHA</html>")
            with self.assertRaises(ProviderError) as caught:
                provider.fetch(url)
            self.assertEqual(caught.exception.code, "ACCESS_RESTRICTED")
            self.assertEqual(opener.return_value.open.call_count, 1)
            opener.return_value.open.return_value = self.response(b"synthetic public content")
            self.assertEqual(provider.fetch(url), b"synthetic public content")

    def test_redirects_never_followed(self):
        self.assertIsNone(NoRedirects().redirect_request(None, None, 302, "", {}, "https://example.com"))


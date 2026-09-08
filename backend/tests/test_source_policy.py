"""Synthetic public-source tests only; never contact a retailer or use real secrets."""
import os
import socket
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

import main
from collectors.source_policy import SourcePolicy, ApprovedTarget
from collectors.public_access import PublicAccessGuard, PublicResponse, direct_get
from collectors.providers.base_provider import FetchResult
from collectors.providers.errors import ProviderError
from collectors.providers.scraperapi_provider import ScraperAPIProvider
from services.provider_test import ProviderTestService

URL = "https://shop.example.com/products/ariel"
DNS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))]
HTML = b'<html><h1>Synthetic product</h1><p>synthetic-secret-only</p></html>'


class SourcePolicyTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"SCRAPERAPI_KEY": "synthetic-secret-only",
                                     "APPROVED_RETAILER_DOMAINS": "SHOP.example.com, other.example.com"})
        env.start()
        self.addCleanup(env.stop)

    def test_exact_host_configuration_normalization_and_no_implicit_subdomains(self):
        policy = SourcePolicy.from_environment()
        self.assertEqual(policy.validate(URL, resolve=False).hostname, "shop.example.com")
        self.assertEqual(policy.validate("https://SHOP.example.com:443/products/ariel", resolve=False).url, URL)
        for url in ("https://shop.example.com.evil.com/x", "https://evilshop.example.com/x",
                    "https://child.shop.example.com/x", "https://example.com/x"):
            with self.assertRaises(ProviderError) as caught:
                policy.validate(url, resolve=False)
            self.assertEqual(caught.exception.code, "APPROVED_SOURCE_REQUIRED")

    def test_empty_and_invalid_configuration_fail_closed(self):
        for value in ("", "https://shop.example.com", "*.example.com", "localhost", "127.0.0.1",
                      "shop.example.com:443", "shop.example.com/path", "shop.example.com,*.bad.com"):
            with patch.dict(os.environ, {"APPROVED_RETAILER_DOMAINS": value}), \
                 patch("collectors.source_policy.socket.getaddrinfo") as dns, \
                 patch("collectors.providers.scraperapi_provider.build_opener") as fetch:
                result, status = ProviderTestService().test(URL)
                self.assertIn(status, {403, 503})
                self.assertEqual(result.data_status, "ERROR")
                dns.assert_not_called()
                fetch.assert_not_called()

    def test_unsafe_syntax_rejected_without_dns(self):
        cases = ["http://shop.example.com/x", "file:///etc/passwd", "https://localhost/x",
                 "https://127.0.0.1/x", "https://[::1]/x", "https://2130706433/x",
                 "https://0177.0.0.1/x", "https://0x7f.0.0.1/x", "https://169.254.169.254/x",
                 "https://user:pass@shop.example.com/x", "https://shop.example.com:8443/x",
                 "https://shop.example.com/x#secret", "https://shop.example.com./x",
                 "https://shop.example.com\\@localhost/x", "https://shop.example.com/\r\nx",
                 "https://shop.example.com/x?api_key=foo", "https://shop.example.com/synthetic-secret-only",
                 "https://shop.example.com/x?%74oken=foo", "https://%73hop.example.com/x"]
        with patch("collectors.source_policy.socket.getaddrinfo") as dns:
            for url in cases:
                with self.subTest(url=url), self.assertRaises(ProviderError):
                    SourcePolicy.from_environment().validate(url)
            dns.assert_not_called()

    def test_dns_all_addresses_must_be_public(self):
        private = ["127.0.0.1", "10.1.2.3", "172.16.1.1", "192.168.1.1", "169.254.169.254",
                   "100.64.1.1", "168.63.129.16", "0.0.0.0", "224.0.0.1", "::1",
                   "fc00::1", "fe80::1", "::ffff:127.0.0.1"]
        for address in private:
            answers = [*DNS, (2, 1, 6, "", (address, 443))]
            with patch("collectors.source_policy.socket.getaddrinfo", return_value=answers), self.assertRaises(ProviderError) as caught:
                SourcePolicy.from_environment().validate(URL)
            self.assertEqual(caught.exception.code, "SSRF_BLOCKED")

    def test_dns_failure_structured(self):
        with patch("collectors.source_policy.socket.getaddrinfo", side_effect=socket.gaierror("secret text")):
            result, status = ProviderTestService().test(URL)
            self.assertEqual(status, 502)
            self.assertEqual(result.error_code, "NETWORK_FAILURE")
            self.assertNotIn("secret text", result.model_dump_json())

    def test_approved_product_endpoint_full_path_and_redacted_logs(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.headers = {"sa-final-url": URL, "Content-Type": "text/html"}
        response.__enter__.return_value.read.return_value = HTML
        service = ProviderTestService()
        guard = PublicAccessGuard()
        with patch.object(main, "public_test_service", service), \
             patch("collectors.source_policy.socket.getaddrinfo", return_value=DNS), \
             patch("collectors.providers.scraperapi_provider.public_access_guard", guard), \
             patch("collectors.public_access.direct_get", side_effect=[PublicResponse(200, b"User-agent: *\nAllow: /", "text/plain"), PublicResponse(200, HTML, "text/html")]) as direct, \
             patch("collectors.providers.scraperapi_provider.build_opener") as opener, \
             self.assertLogs("uvicorn.error.scraperapi", level="INFO") as logs:
            opener.return_value.open.return_value = response
            result = TestClient(main.app).post("/collectors/test", json={"url": URL})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["data_status"], "FETCHED")
            self.assertEqual(result.json()["source_url"], URL)
            self.assertIn("Synthetic product", result.json()["content_preview"])
            self.assertNotIn("synthetic-secret-only", result.text + str(logs.output))
            self.assertIn("event=FETCHING", str(logs.output))
            self.assertIn("event=SUCCESS", str(logs.output))
            self.assertEqual(direct.call_count, 2)
            query = parse_qs(urlsplit(opener.return_value.open.call_args.args[0].full_url).query)
            self.assertEqual(query["follow_redirect"], ["false"])
            self.assertEqual(query["url"], [URL])
            self.assertEqual(set(query), {"api_key", "url", "follow_redirect"})

    def test_robots_wildcard_disallow_stops_before_page_and_provider(self):
        guard = PublicAccessGuard()
        with patch("collectors.source_policy.socket.getaddrinfo", return_value=DNS), \
             patch("collectors.providers.scraperapi_provider.public_access_guard", guard), \
             patch("collectors.public_access.direct_get", return_value=PublicResponse(200, b"User-agent: *\nDisallow: /*ariel$", "text/plain")) as direct, \
             patch("collectors.providers.scraperapi_provider.build_opener") as fetch:
            result, status = ProviderTestService().test(URL)
            self.assertEqual(status, 403)
            self.assertEqual(result.error_code, "ROBOTS_RESTRICTED")
            self.assertEqual(direct.call_count, 1)
            fetch.assert_not_called()

    def test_source_denials_challenges_redirects_and_binary_stop_before_provider(self):
        pages = [PublicResponse(401, b"", "text/html"), PublicResponse(403, b"", "text/html"),
                 PublicResponse(429, b"", "text/html"), PublicResponse(302, b"", "text/html"),
                 PublicResponse(200, b"CAPTCHA", "text/html"), PublicResponse(200, b"subscribe to continue", "text/html"),
                 PublicResponse(200, b"binary", "application/pdf")]
        for page in pages:
            with patch("collectors.source_policy.socket.getaddrinfo", return_value=DNS), \
                 patch("collectors.providers.scraperapi_provider.public_access_guard", PublicAccessGuard()), \
                 patch("collectors.public_access.direct_get", side_effect=[PublicResponse(404, b"", "text/plain"), page]), \
                 patch("collectors.providers.scraperapi_provider.build_opener") as fetch:
                result, status = ProviderTestService().test(URL)
                self.assertNotEqual(status, 200)
                self.assertEqual(result.data_status, "ERROR")
                self.assertEqual(result.content_preview, "")
                fetch.assert_not_called()

    def test_final_url_revalidated_and_rebinding_rejected(self):
        with patch("collectors.providers.scraperapi_provider.public_access_guard.check"), \
             patch("collectors.source_policy.socket.getaddrinfo", return_value=DNS):
            for final in ["https://unapproved.example.com/x", "https://127.0.0.1/x", "https://shop.example.com/login"]:
                provider = ScraperAPIProvider()
                with patch.object(provider, "_request_result", return_value=FetchResult(200, final, datetime.now(timezone.utc), HTML)), self.assertRaises(ProviderError):
                    provider.fetch_result(URL)
        with patch("collectors.providers.scraperapi_provider.public_access_guard.check"), \
             patch("collectors.source_policy.socket.getaddrinfo", side_effect=[DNS, [(2, 1, 6, "", ("127.0.0.1", 443))]]), \
             patch("collectors.providers.scraperapi_provider.build_opener") as fetch, self.assertRaises(ProviderError):
            ScraperAPIProvider().fetch_result(URL)
        fetch.assert_not_called()

    def test_direct_connection_pins_numeric_address_with_host_tls(self):
        with patch("collectors.public_access.http.client.HTTPSConnection") as connection, \
             patch("collectors.public_access.socket.create_connection") as connect:
            conn = connection.return_value
            conn.getresponse.return_value.status = 200
            conn.getresponse.return_value.read.return_value = b"html"
            conn.getresponse.return_value.getheader.return_value = "text/html"
            direct_get(ApprovedTarget(URL, "shop.example.com", ("93.184.215.14",)))
            self.assertEqual(connection.call_args.args, ("shop.example.com",))
            conn._create_connection(("shop.example.com", 443), 8)
            self.assertEqual(connect.call_args.args[:2], (("93.184.215.14", 443), 8))
            conn.close.assert_called_once()

    def test_parsing_and_blocked_events_have_safe_schema(self):
        with self.assertLogs("uvicorn.error.scraperapi") as logs:
            result, _ = ProviderTestService().test("https://unapproved.example.com")
        self.assertIn("BLOCKED_BY_ALLOWLIST", str(logs.output))
        self.assertEqual(result.data_status, "ERROR")
        service = ProviderTestService()
        with patch.object(service.provider, "fetch_result", return_value=FetchResult(200, URL, datetime.now(timezone.utc), b"", "application/pdf")), self.assertLogs("uvicorn.error.scraperapi") as logs:
            result, status = service.test(URL)
        self.assertEqual(status, 502)
        self.assertIn("PARSING_ERROR", str(logs.output))
        self.assertFalse(result.success)

    def test_status_reports_key_boolean_and_policy_without_dns(self):
        with patch("collectors.source_policy.socket.getaddrinfo") as dns:
            status = TestClient(main.app).get("/collectors/providers/status").json()
        self.assertEqual(status["approved_domain_count"], 2)
        self.assertTrue(status["api_key_available"])
        self.assertNotIn("synthetic-secret-only", str(status))
        dns.assert_not_called()

    def test_crawl_delay_and_unverifiable_robots(self):
        for body, code in [(b"User-agent: *\nCrawl-delay: 20", "SOURCE_RATE_POLICY"), (b"<html>error</html>", "ROBOTS_UNAVAILABLE")]:
            with patch("collectors.source_policy.socket.getaddrinfo", return_value=DNS), \
                 patch("collectors.public_access.direct_get", return_value=PublicResponse(200, body, "text/plain")), self.assertRaises(ProviderError) as caught:
                policy = SourcePolicy.from_environment()
                PublicAccessGuard().check(policy, policy.validate(URL))
            self.assertEqual(caught.exception.code, code)

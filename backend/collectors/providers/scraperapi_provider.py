"""ScraperAPI transport, separate from retailer approval and LIVE observations.

Approved hostnames come from server configuration. Credentials grant no permission.
"""
import json
import logging
import socket
from http.client import HTTPException
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import BaseModel

from config import scraperapi_key
from collectors.providers.base_provider import BaseProvider, FetchResult
from collectors.providers.errors import ProviderError
from collectors.source_policy import SourcePolicy
from collectors.public_access import PublicAccessGuard, reject_restrictions

logger = logging.getLogger("uvicorn.error.scraperapi")

public_access_guard = PublicAccessGuard()


class ProviderStatus(BaseModel):
    provider: str = "ScraperAPI"
    configured: bool
    status: str
    api_key_available: bool
    approved_domain_count: int = 0
    source_configuration_status: str = "EMPTY"


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a credential-bearing request to another destination.
        return None


class ScraperAPIProvider(BaseProvider):
    timeout_seconds = 8
    max_response_bytes = 2 * 1024 * 1024

    def __init__(self, approved_urls: frozenset[str] | None = None):
        # Existing exact-URL adapters still undergo every network/access check.
        self._approved_urls = approved_urls

    def source_policy(self):
        if self._approved_urls is not None:
            return SourcePolicy(frozenset(urlsplit(url).hostname or "" for url in self._approved_urls))
        return SourcePolicy.from_environment()

    def validate_source(self, url, *, resolve=True):
        policy = self.source_policy()
        if self._approved_urls is not None and url not in self._approved_urls:
            self._fail("APPROVED_SOURCE_REQUIRED")
        return policy.validate(url, resolve=resolve)

    def status(self) -> ProviderStatus:
        configured = bool(scraperapi_key())
        count, policy_status = 0, "INVALID_CONFIGURATION"
        try:
            count = len(self.source_policy().domains)
            policy_status = "READY" if count else "EMPTY"
        except ProviderError:
            pass
        return ProviderStatus(configured=configured,
                              status="READY" if configured else "NOT_CONFIGURED",
                              api_key_available=configured, approved_domain_count=count,
                              source_configuration_status=policy_status)

    def _fail(self, code, status_code=None):
        logger.warning("scraperapi request failed code=%s", code)
        raise ProviderError(code, status_code) from None

    def _request(self, path: str, parameters: dict) -> bytes:
        return self._request_result(path, parameters).body

    def _request_result(self, path: str, parameters: dict) -> FetchResult:
        key = scraperapi_key()
        if not key:
            self._fail("MISSING_API_KEY")
        # urllib does not log URLs; do not enable HTTP wire debugging.
        request = Request("https://api.scraperapi.com" + path + "?" +
                          urlencode({"api_key": key, **parameters}))
        try:
            with build_opener(NoRedirects()).open(request, timeout=self.timeout_seconds) as response:
                status_code = response.status
                final_url = response.headers.get("sa-final-url")
                content_type = response.headers.get("Content-Type", "")
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    self._fail("INVALID_RESPONSE")
        except HTTPError as error:
            code = {401: "INVALID_API_KEY", 403: "CREDITS_EXHAUSTED",
                    429: "RATE_LIMITED", 408: "PROVIDER_TIMEOUT", 504: "PROVIDER_TIMEOUT"}.get(
                        error.code, "PROVIDER_ERROR")
            error.close()
            self._fail(code, error.code)
        except (TimeoutError, socket.timeout):
            self._fail("PROVIDER_TIMEOUT")
        except URLError as error:
            self._fail("PROVIDER_TIMEOUT" if isinstance(error.reason, TimeoutError) else "NETWORK_FAILURE")
        except (OSError, HTTPException):
            self._fail("NETWORK_FAILURE")
        logger.info("scraperapi request completed bytes=%d", len(body))
        # Never use response.geturl(): that is the provider URL containing the key.
        # An absent final-source header means the final URL is unknown, not assumed.
        return FetchResult(status_code=status_code, source_url=final_url,
                           fetched_at=datetime.now(timezone.utc), body=body, content_type=content_type)

    def verify_account(self) -> dict:
        """Explicit diagnostic; never returns the account body or key."""
        body = self._request("/account", {})
        try:
            account = json.loads(body)
            if not isinstance(account, dict) or not {"requestCount", "concurrentRequests"} <= account.keys():
                self._fail("INVALID_RESPONSE")
        except (ValueError, UnicodeError):
            self._fail("INVALID_RESPONSE")
        return {"provider": "ScraperAPI", "configured": True, "status": "AUTHENTICATED"}

    def fetch(self, url: str) -> bytes:
        return self.fetch_result(url).body

    def fetch_result(self, url: str) -> FetchResult:
        """For reviewed adapters only; raw content is never labeled LIVE here.

        Review must cover retailer permission, robots/path rules and the provider
        collection method. No blocked-source fallback, retries, premium proxies,
        rendering, sessions, cookies or CAPTCHA solving are configured here.
        """
        target = self.validate_source(url)
        if not scraperapi_key():
            self._fail("MISSING_API_KEY")
        public_access_guard.check(self.source_policy(), target)
        self.validate_source(url)  # Recheck DNS before the provider request.
        logger.info("scraperapi event=FETCHING")
        result = self._request_result("/", {"url": target.url, "follow_redirect": "false"})
        if result.source_url is not None:
            final = self.validate_source(result.source_url)
            if final.url != target.url:
                self._fail("REDIRECT_BLOCKED", result.status_code)
        if result.status_code != 200:
            self._fail("PROVIDER_ERROR", result.status_code)
        reject_restrictions(result.body, result.status_code)
        return result

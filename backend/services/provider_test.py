"""Bounded public diagnostic, not an arbitrary URL proxy."""
import re
import logging
import threading
import time
from html import unescape
from typing import Literal
from urllib.parse import quote, quote_plus

from pydantic import AwareDatetime, BaseModel, Field

from config import scraperapi_key
from collectors.providers.scraperapi_provider import ScraperAPIProvider, ProviderError

logger = logging.getLogger("uvicorn.error.scraperapi")
BLOCK_CODES = {"APPROVED_SOURCE_REQUIRED", "INVALID_URL", "SSRF_BLOCKED",
               "INVALID_SOURCE_CONFIGURATION"}


class ProviderTestRequest(BaseModel):
    url: str = Field(description="HTTPS public product page on an exact hostname in APPROVED_RETAILER_DOMAINS.")


class ProviderTestResult(BaseModel):
    provider: str = "ScraperAPI"
    success: bool = False
    data_status: Literal["FETCHED", "ERROR"] = "ERROR"
    status_code: int | None = None
    source_url: str | None = None
    fetched_at: AwareDatetime | None = None
    content_preview: str = ""
    error_code: str | None = None
    reason: str | None = None


def safe_preview(body: bytes) -> str:
    text = unescape(body.decode("utf-8", errors="replace"))
    key = scraperapi_key()
    if key:
        for secret in {key, quote(key, safe=""), quote_plus(key)}:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?is)<(script|style)\b[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r'(?i)(api[_-]?key|authorization|token)\s*[=:]\s*[^\s<>]+', r'\1=[REDACTED]', text)
    return " ".join(text.split())[:300]


class ProviderTestService:
    def __init__(self):
        self.provider = ScraperAPIProvider()
        self._lock = threading.Lock()
        self._last_attempt = None

    def test(self, url: str) -> tuple[ProviderTestResult, int]:
        try:
            self.provider.validate_source(url, resolve=False)
        except ProviderError as error:
            return self.failure(error)
        with self._lock:
            if self._last_attempt is not None and time.monotonic() - self._last_attempt < 60:
                return self.failure(ProviderError("RATE_LIMITED"))
            self._last_attempt = time.monotonic()
        try:
            result = self.provider.fetch_result(url)
            if result.source_url is None:
                raise ProviderError("INVALID_RESPONSE", result.status_code)
            if not result.content_type.lower().startswith(("text/html", "application/xhtml+xml")):
                raise ProviderError("PARSING_ERROR", result.status_code)
            preview = safe_preview(result.body)
            if not preview:
                raise ProviderError("PARSING_ERROR", result.status_code)
            logger.info("scraperapi event=SUCCESS status_code=%d", result.status_code)
            return ProviderTestResult(success=True, data_status="FETCHED", status_code=result.status_code,
                source_url=result.source_url, fetched_at=result.fetched_at,
                content_preview=preview), 200
        except ProviderError as error:
            return self.failure(error)
        except (ValueError, UnicodeError, TypeError):
            return self.failure(ProviderError("PARSING_ERROR"))

    @staticmethod
    def failure(error):
        event = "BLOCKED_BY_ALLOWLIST" if error.code in BLOCK_CODES else "PARSING_ERROR" if error.code in {"PARSING_ERROR", "INVALID_RESPONSE"} else "PROVIDER_ERROR"
        logger.warning("scraperapi event=%s code=%s", event, error.code)
        http_status = {"RATE_LIMITED": 429, "PROVIDER_TIMEOUT": 504,
                       "APPROVED_SOURCE_REQUIRED": 403, "SSRF_BLOCKED": 403,
                       "INVALID_URL": 403, "ACCESS_RESTRICTED": 403,
                       "ROBOTS_RESTRICTED": 403, "REDIRECT_BLOCKED": 403,
                       "INVALID_SOURCE_CONFIGURATION": 503, "MISSING_API_KEY": 503}.get(error.code, 502)
        return ProviderTestResult(status_code=error.status_code, error_code=error.code,
                                  reason=error.message), http_status

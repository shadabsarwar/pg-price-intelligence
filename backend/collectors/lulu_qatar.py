"""LuLu Qatar connector. Public search is blocked; no scraping transport is installed.

A reviewed retailer-authorized adapter can be injected by application code after
permission, endpoint, schema, permitted paths and rate limits have been verified.
There is deliberately no environment flag that turns website scraping on.
"""
import logging
import math
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urlsplit

from collectors.base import (
    BaseCollector, CollectorError, CollectorSearchResponse, ConnectorStatus, RetailerListing,
)
from models.product import PlatformListing, Product

logger = logging.getLogger("uvicorn.error.lulu")


class ApprovedLuluSource(ABC):
    """Extension contract, NOT an implemented or verified live transport.

    Implement only against a retailer-authorized source. Search must enforce its
    approved robots/path policy, <=8s network timeout, response-size limits and
    schema validation, and stop on 401/403/429/CAPTCHA (no automatic retries).
    Return only observations retrieved in this request, never cached/demo rows.
    Credentials belong in server configuration and must never be logged.
    """

    permission_reference: str
    source_reference: str
    minimum_interval_seconds: float = 60
    # Concrete transports increment immediately before each outbound HTTP request.
    # Permission checks, cache reads and local validation must not increment this.
    retailer_requests: int = 0

    @abstractmethod
    def search(self, query: str) -> list[RetailerListing]:
        raise NotImplementedError


class LuluQatarCollector(BaseCollector):
    platform = "LuLu Qatar"
    # Not scheduled by the generic 10-second worker. Searches are explicit and throttled.
    enabled = False

    def __init__(self, source: ApprovedLuluSource | None = None):
        self.source = source
        self._lock = threading.Lock()
        self._last_request = None
        self._status = ConnectorStatus(connector_name="lulu_qatar", source_platform=self.platform,
                                       status="UNAVAILABLE", errors=self.access_errors())

    @staticmethod
    def access_errors():
        return [
            CollectorError(code="PERMISSION_REQUIRED", message="LuLu terms section 4.1 requires written permission for commercial content reuse; no permission is recorded."),
            CollectorError(code="ROBOTS_RESTRICTED", message="Reviewed robots.txt disallows /search/, /api/ and q query URLs. Website search scraping is not implemented."),
            CollectorError(code="APPROVED_SOURCE_MISSING", message="A retailer-approved API/feed, its schema, usage scope and rate limits are not configured."),
        ]

    def status(self) -> ConnectorStatus:
        with self._lock:
            snapshot = self._status.model_copy(deep=True)
        if snapshot.data_status == "LIVE" and snapshot.last_successful_collection:
            if (datetime.now(timezone.utc) - snapshot.last_successful_collection).total_seconds() > 900:
                snapshot.data_status = "STALE"
                snapshot.status = "STALE"
                snapshot.message = "Live data currently unavailable; last collection is stale."
                snapshot.reason = snapshot.message
        return snapshot

    def search(self, query: str) -> CollectorSearchResponse:
        # One request at a time; the HTTP route runs this synchronous adapter in a thread.
        if not self._lock.acquire(blocking=False):
            return self._failure("COLLECTION_BUSY", "A collection is already in progress.")
        try:
            started = datetime.now(timezone.utc)
            self._status.last_attempt_at = started
            logger.info("lulu search requested query_length=%d", len(query))
            if self.source is None:
                self._status.status = "UNAVAILABLE"
                self._status.data_status = "ERROR"
                self._status.data_access_status = "APPROVED_SOURCE_REQUIRED"
                self._status.reason = "No approved API, product feed, or permitted data source has been configured."
                self._status.errors = self.access_errors()
                self._status.message = "Live data currently unavailable"
                logger.warning("lulu blocked: permission and approved source missing; retailer_requests=0")
                return CollectorSearchResponse(source_platform=self.platform, errors=self.access_errors(),
                    error_code="APPROVED_SOURCE_REQUIRED",
                    message="No approved API, product feed, or permitted data source has been configured. No live collection was attempted and no retailer request was made.")
            references = [getattr(self.source, key, None) for key in ("permission_reference", "source_reference")]
            if any(not isinstance(value, str) or not value.strip() for value in references):
                return self._record_failure("APPROVAL_INCOMPLETE", "Approved adapter has no permission/source reference.")
            configured_interval = self.source.minimum_interval_seconds
            if not isinstance(configured_interval, (int, float)) or not math.isfinite(configured_interval) or configured_interval <= 0:
                return self._record_failure("INVALID_CONFIGURATION", "Approved source rate limit is invalid.")
            interval = max(60, configured_interval)
            if self._last_request is not None and time.monotonic() - self._last_request < interval:
                return self._failure("RATE_LIMITED", "Connector cooldown is active; no retailer request was sent.")
            self._last_request = time.monotonic()
            self._status.data_access_status = "APPROVED"
            requests_before = self.source.retailer_requests
            requests_made = 0
            try:
                try:
                    rows = self.source.search(query)
                finally:
                    requests_made = max(0, self.source.retailer_requests - requests_before)
                    self._status.retailer_requests += requests_made
                if len(rows) > 100:
                    raise ValueError("Source returned more than the 100-listing proof-of-concept limit.")
                listings = [RetailerListing.model_validate(row) for row in rows]
                seen = set()
                for row in listings:
                    parsed = urlsplit(str(row.product_url))
                    if row.source_platform != self.platform or parsed.scheme != "https" or parsed.hostname != "gcc.luluhypermarket.com" or not parsed.path.startswith("/en-qa/") or parsed.username or parsed.password:
                        raise ValueError("Observation is not a LuLu Qatar product URL.")
                    if not started <= row.collected_at <= datetime.now(timezone.utc):
                        raise ValueError("Observation was not retrieved during this request.")
                    if row.platform_product_id in seen:
                        raise ValueError("Duplicate retailer product identifier.")
                    seen.add(row.platform_product_id)
            except Exception as error:
                # Log class, not arbitrary exception text, which can contain credentials or bodies.
                logger.error("lulu collection failed exception_type=%s", type(error).__name__)
                return self._record_failure("SOURCE_ERROR", "Approved source retrieval or validation failed; no observations were accepted.", requests_made)
            if not listings:
                return self._record_failure("NO_VERIFIED_LISTINGS", "Source returned no verified product listings; no live success claimed.", requests_made)
            collected_at = max(row.collected_at for row in listings)
            self._status.status = "LIVE"
            self._status.data_status = "LIVE"
            self._status.last_successful_collection = collected_at
            self._status.number_of_products_collected = len(listings)
            self._status.errors = []
            self._status.message = "Retailer listings retrieved through the approved source."
            self._status.reason = self._status.message
            logger.info("lulu collection accepted listings=%d", len(listings))
            return CollectorSearchResponse(source_platform=self.platform, listings=listings,
                                           listings_found=len(listings), data_status="LIVE", collected_at=collected_at,
                                           success=True, retailer_requests=requests_made, message=self._status.message)
        finally:
            self._lock.release()

    def _failure(self, code, message, retailer_requests=0):
        logger.warning("lulu request not completed code=%s", code)
        return CollectorSearchResponse(source_platform=self.platform, errors=[CollectorError(code=code, message=message)],
                                       error_code=code, message=message, retailer_requests=retailer_requests)

    def _record_failure(self, code, message, retailer_requests=0):
        response = self._failure(code, message, retailer_requests)
        self._status.status = "ERROR"
        self._status.data_status = "ERROR"
        self._status.message = "Live data currently unavailable"
        self._status.errors = response.errors
        self._status.reason = message
        if code == "APPROVAL_INCOMPLETE":
            self._status.status = "UNAVAILABLE"
            self._status.data_access_status = "APPROVED_SOURCE_REQUIRED"
            response.error_code = "APPROVED_SOURCE_REQUIRED"
        return response

    def collect(self, product: Product) -> list[PlatformListing]:
        raise RuntimeError("Use the explicit LuLu search service; exact SKU binding is required before integration.")

import asyncio
from datetime import datetime, timezone

from collectors.base import BaseCollector
from models.product import PlatformListing, Product


class MarketRefresher:
    """Approved collectors must implement their own network timeouts and exact SKU matching."""

    def __init__(self, collectors: list[BaseCollector]):
        self.collectors = collectors
        self.statuses = {collector.platform: {
            "platform": collector.platform, "status": "NOT_CONFIGURED" if not collector.enabled else "PENDING",
            "message": "No approved live data access configured." if not collector.enabled else "Waiting for collection.",
            "last_successful_update": None,
        } for collector in collectors}

    async def refresh(self, products: list[Product]):
        for collector in self.collectors:
            if not collector.enabled:
                continue
            errors = []
            for product in products:
                try:
                    rows = await asyncio.wait_for(asyncio.to_thread(collector.collect, product), timeout=8)
                    validated = [PlatformListing.model_validate(row) for row in rows]
                    if any(row.platform != collector.platform or row.data_source != "verified" for row in validated):
                        raise ValueError("Approved adapter must return its own verified platform observations.")
                    # An empty success is authoritative: previously listed offers are removed.
                    product.listings = [row for row in product.listings if row.platform != collector.platform or row.data_source == "demo"] + validated
                except Exception as error:
                    # Status endpoints must not expose transport URLs or secrets.
                    errors.append("Approved collection failed; previous observations retained.")
                    for row in product.listings:
                        if row.platform == collector.platform and row.data_source == "verified":
                            row.collection_error = "Latest collection failed; previous observation retained."
            state = self.statuses[collector.platform]
            state["status"] = "ERROR" if errors else "OK"
            state["message"] = "; ".join(errors) if errors else "Approved collector refresh completed."
            if not errors:
                state["last_successful_update"] = datetime.now(timezone.utc).isoformat()

    async def run(self, get_products):
        while True:
            await self.refresh(get_products())
            await asyncio.sleep(10)

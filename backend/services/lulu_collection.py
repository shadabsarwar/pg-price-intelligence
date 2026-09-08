import asyncio
import logging

from collectors.base import CollectorSearchResponse
from collectors.lulu_qatar import LuluQatarCollector
from models.product import PlatformListing, Product

logger = logging.getLogger("uvicorn.error.lulu")


def valid_gtin(value: str | None) -> bool:
    if not value or not value.isascii() or not value.isdigit() or len(value) not in {8, 12, 13, 14}:
        return False
    checksum = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(value[:-1])))
    return (10 - checksum % 10) % 10 == int(value[-1])


class LuluCollectionService:
    def __init__(self, collector: LuluQatarCollector, approved_bindings: dict[str, int] | None = None):
        self.collector = collector
        # Explicitly reviewed retailer SKU -> master/competitor ID, not fuzzy name matching.
        self.approved_bindings = approved_bindings or {}

    async def search(self, query: str, catalogue: list[Product]) -> CollectorSearchResponse:
        response = await asyncio.to_thread(self.collector.search, query)
        return self.integrate(response, catalogue)

    def integrate(self, response: CollectorSearchResponse, catalogue: list[Product]) -> CollectorSearchResponse:
        if response.data_status != "LIVE":
            # Busy/rate-limit requests are local deferrals, not failed retailer observations.
            deferred = any(error.code in {"RATE_LIMITED", "COLLECTION_BUSY"} for error in response.errors)
            if not deferred:
                for product in catalogue:
                    for row in product.listings:
                        if row.platform == self.collector.platform and row.data_source == "verified":
                            row.collection_error = "Live data currently unavailable; previous observation retained."
            return response
        for observation in response.listings:
            bound_id = self.approved_bindings.get(observation.platform_product_id)
            if bound_id is not None:
                matches = [product for product in catalogue if product.id == bound_id]
            elif valid_gtin(observation.barcode):
                matches = [product for product in catalogue if product.barcode == observation.barcode]
            else:
                matches = []
            if len(matches) != 1 or (observation.brand and observation.brand.casefold().strip() != matches[0].brand.casefold().strip()):
                response.unmatched_count += 1
                continue
            product = matches[0]
            listing = PlatformListing(platform=self.collector.platform, platform_product_id=observation.platform_product_id,
                                      product_name=observation.product_name, price=observation.current_price,
                                      original_price=observation.original_price, currency=observation.currency,
                                      product_url=observation.product_url, image_url=observation.image_url,
                                      availability=observation.availability, last_updated=observation.collected_at,
                                      data_source="verified", source_name="LuLu Qatar approved retailer source",
                                      collection_method="live")
            product.listings = [row for row in product.listings if not (
                row.platform == listing.platform and row.platform_product_id == listing.platform_product_id
                and row.data_source == "verified")] + [listing]
            if not product.image_url and observation.image_url:
                product.image_url = str(observation.image_url)
            response.integrated_count += 1
        logger.info("lulu integration accepted=%d unmatched=%d demo_rows_preserved=true", response.integrated_count, response.unmatched_count)
        return response

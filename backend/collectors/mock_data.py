import json
from datetime import datetime, timezone
from pathlib import Path

from collectors.base import BaseCollector
from models.product import PlatformListing, Product


class DemoCollector(BaseCollector):
    """Synthetic fixtures, never retailer observations. No network requests."""

    def __init__(self):
        path = Path(__file__).resolve().parents[1] / "data" / "demo_listings.json"
        self.fixtures = json.loads(path.read_text(encoding="utf-8"))
        self.generated_at = datetime.now(timezone.utc)

    def collect(self, product: Product) -> list[PlatformListing]:
        return [PlatformListing(
            **row,
            platform_product_id=f"DEMO-{product.id}-{index}",
            product_name=product.product_name,
            currency="QAR",
            availability="available",
            last_updated=self.generated_at,
            data_source="demo",
            # No fabricated product links or unverified image URLs.
        ) for index, row in enumerate(self.fixtures.get(str(product.id), []), start=1)]

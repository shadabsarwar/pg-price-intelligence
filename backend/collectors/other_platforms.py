from collectors.base import BaseCollector
from models.product import PlatformListing, Product


class OtherPlatformsCollector(BaseCollector):
    platform = "Other platforms"

    def collect(self, product: Product) -> list[PlatformListing]:
        raise NotImplementedError("No approved source configured. Implement an adapter and enable it explicitly.")

from collectors.base import BaseCollector
from models.product import PlatformListing, Product


class CarrefourQatarCollector(BaseCollector):
    """Reserved for an official API, feed, or approved collection method."""

    platform = "Carrefour Qatar"

    def collect(self, product: Product) -> list[PlatformListing]:
        raise NotImplementedError("Carrefour Qatar has no configured approved data source.")

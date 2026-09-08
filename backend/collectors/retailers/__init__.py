from collectors.retailers.lulu_qatar import LuluQatarRetailer
from collectors.retailers.carrefour_qatar import CarrefourQatarRetailer
from collectors.retailers.noon_qatar import NoonQatarRetailer


def retailer_registry():
    return {item.slug: item for item in (
        LuluQatarRetailer(), CarrefourQatarRetailer(), NoonQatarRetailer())}

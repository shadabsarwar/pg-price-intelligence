from collectors.retailers.base_retailer import UnavailableRetailer


class CarrefourQatarRetailer(UnavailableRetailer):
    slug = "carrefour_qatar"
    platform = "Carrefour Qatar"
    reason = ("A permitted Qatar product feed or collection route has not been verified. "
              "The terms page could not be retrieved during review; public visibility "
              "does not establish collection permission. No retailer request was made.")
    policy_url = "https://www.carrefourqatar.com/mafqat/en/terms-and-conditions"

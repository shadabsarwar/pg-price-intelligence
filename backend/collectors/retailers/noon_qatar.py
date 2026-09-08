from collectors.retailers.base_retailer import UnavailableRetailer


class NoonQatarRetailer(UnavailableRetailer):
    slug = "noon_qatar"
    platform = "Noon Qatar"
    reason = ("Noon Qatar terms prohibit automated crawling/scraping of the service. "
              "No separately authorized Qatar API/feed is configured. No retailer request was made.")
    policy_url = "https://www.noon.com/qatar-en/terms-of-sale/"

from collectors.retailers.base_retailer import UnavailableRetailer
from collectors.retailers.base_retailer import RetailerProduct, RetailerSearchResult


class LuluQatarRetailer(UnavailableRetailer):
    slug = "lulu_qatar"
    platform = "LuLu Qatar"
    reason = ("LuLu Qatar terms section 4.1 requires written permission for commercial "
              "content reuse. No permission or approved feed is configured; robots.txt "
              "also restricts search/API paths. No retailer request was made.")
    policy_url = "https://gcc.luluhypermarket.com/en-qa/termsAndConditions/"

    def __init__(self, collector=None):
        self.collector = collector

    def search(self, query):
        if self.collector is None or self.collector.source is None:
            return super().search(query)
        result = self.collector.search(query)
        return self.from_result(result)

    def from_result(self, result):
        if result.data_status != 'LIVE':
            return RetailerSearchResult(platform=self.platform, reason=result.message)
        products = [RetailerProduct(platform=self.platform, product_name=row.product_name,
            brand=row.brand, company=row.company, category=row.category, barcode=row.barcode,
            retailer_sku=row.platform_product_id, product_size=row.size, current_price=row.current_price,
            original_price=row.original_price, product_image=row.image_url, product_url=row.product_url,
            currency=row.currency, availability=row.availability, data_status='LIVE',
            collected_at=row.collected_at, source_type='approved_feed') for row in result.listings]
        return RetailerSearchResult(platform=self.platform, data_status='LIVE', products=products,
                                    collected_at=result.collected_at, retailer_requests=result.retailer_requests)

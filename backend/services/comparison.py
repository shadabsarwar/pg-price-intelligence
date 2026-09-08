from models.product import Product, ProductComparison


def compare_product(product: Product) -> ProductComparison:
    # Never compare different currencies or mix verified prices with demo prices.
    same_currency = [item for item in product.listings if item.currency == product.currency]
    source = "verified" if any(item.data_source == "verified" for item in same_currency) else "demo"
    eligible = [item for item in same_currency if item.data_source == source and item.availability == "available"
                and item.data_status not in {"STALE", "ERROR"}]
    lowest = min((item.price for item in eligible), default=None)
    highest = max((item.price for item in eligible), default=None)
    return ProductComparison(
        product=product,
        image_url=product.image_url,
        listings=product.listings,
        currency=product.currency,
        data_source=source if same_currency else "none",
        lowest_price=lowest,
        highest_price=highest,
        best_deals=[item for item in eligible if item.price == lowest],
        number_of_platforms=len({item.platform for item in product.listings}),
        last_updated=max((item.last_updated for item in product.listings), default=None),
    )

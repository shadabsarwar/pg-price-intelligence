import unittest
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

import main
from models.product import PlatformListing, Product, ProductCreate
from services.comparison import compare_product


def listing(price, **overrides):
    values = dict(platform=f"Platform {price}", platform_product_id=str(price),
                  product_name="Test", price=price, currency="QAR",
                  availability="available", last_updated=datetime.now(timezone.utc))
    return PlatformListing(**(values | overrides))


class ComparisonTests(unittest.TestCase):
    def product(self, listings):
        return main.products[1].model_copy(update={"listings": listings})

    def test_demo_seed_and_stable_timestamps(self):
        for product in main.products.values():
            comparison = compare_product(product)
            self.assertEqual(comparison.number_of_platforms, 3)
            self.assertTrue(all(item.data_source == "demo" for item in product.listings))
            self.assertEqual(comparison.last_updated, compare_product(product).last_updated)
        self.assertEqual(compare_product(main.products[1]).lowest_price, 28.75)

    def test_excludes_unavailable_and_other_currency(self):
        result = compare_product(self.product([
            listing(1, availability="out_of_stock"), listing(2, currency="USD"),
            listing(30), listing(40), listing(0, availability="unknown"),
        ]))
        self.assertEqual((result.lowest_price, result.highest_price), (30, 40))

    def test_verified_and_demo_never_rank_together(self):
        result = compare_product(self.product([listing(1), listing(30, data_source="verified")]))
        self.assertEqual(result.lowest_price, 30)
        self.assertEqual(result.data_source, "verified")
        unavailable = compare_product(self.product([listing(1), listing(30, data_source="verified", availability="out_of_stock")]))
        self.assertIsNone(unavailable.lowest_price)

    def test_ties_zero_price_and_empty(self):
        result = compare_product(self.product([listing(0), listing(0, platform="Other")]))
        self.assertEqual(result.lowest_price, 0)
        self.assertEqual(len(result.best_deals), 2)
        empty = compare_product(self.product([]))
        self.assertIsNone(empty.lowest_price)
        self.assertIsNone(empty.last_updated)
        self.assertEqual(empty.number_of_platforms, 0)

    def test_listing_validation(self):
        for overrides in ({"price": -1}, {"price": float("inf")}, {"product_url": "javascript:alert(1)"}, {"last_updated": "2026-09-05T00:00:00"}):
            with self.assertRaises(ValidationError):
                listing(10, **overrides) if "price" not in overrides else PlatformListing(**(listing(10).model_dump() | overrides))


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_create_get_delete_and_new_routes(self):
        self.assertEqual(main.home(), {"message": "P&G Price Intelligence API is running"})
        payload = main.products[1].model_dump(exclude={"id", "listings", "image_url"})
        product = await main.create_product(ProductCreate(**payload))
        try:
            self.assertIsNone(product.image_url)
            self.assertEqual(await main.get_listings(product.id), [])
            self.assertIsNone((await main.get_best_price(product.id)).lowest_price)
            self.assertEqual((await main.get_comparison(product.id)).product.id, product.id)
        finally:
            await main.delete_product(product.id)
        for endpoint in (main.get_product, main.get_listings, main.get_comparison, main.get_best_price, main.delete_product):
            with self.assertRaises(HTTPException) as raised:
                await endpoint(product.id)
            self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

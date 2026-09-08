import json
from datetime import datetime, timezone
from pathlib import Path

from models.brand import Brand
from models.company import Company
from models.product import PlatformListing, Product


def load_competitor_catalogue(masters: dict[int, Product]):
    config = json.loads((Path(__file__).resolve().parents[1] / "data" / "competitor_catalogue.json").read_text(encoding="utf-8-sig"))
    companies = {row["id"]: Company(**row) for row in config["companies"]}
    brands = {row["id"]: Brand(**row) for row in config["brands"]}
    for brand in brands.values():
        if brand.company_id not in companies:
            raise ValueError(f"Unknown company for brand {brand.name}")
    for product_id, attributes in config["master_attributes"].items():
        if int(product_id) in masters:
            values = masters[int(product_id)].model_dump(exclude={"data_status"}) | attributes
            masters[int(product_id)] = Product.model_validate(values)
    competitors = {}
    collected_at = datetime.now(timezone.utc)
    for row in config["products"]:
        values = dict(row)
        prices = values.pop("prices")
        brand = brands[values["brand_id"]]
        company = companies[brand.company_id]
        product = Product(**values, company=company.name, company_id=company.id, brand=brand.name,
                          barcode=f"DEMO-COMP-{values['id']}", currency="QAR", price=min(prices))
        product.listings = [PlatformListing(
            platform=platform, platform_product_id=f"DEMO-{product.id}-{index}",
            product_name=product.product_name, price=price, currency="QAR", availability="available",
            last_updated=collected_at, source_name="Synthetic competitor fixture",
        ) for index, (platform, price) in enumerate(zip(["Carrefour Qatar", "LuLu Qatar", "Demo Qatar Store"], prices))]
        if product.id in competitors or product.id in masters:
            raise ValueError("Duplicate catalogue product ID")
        competitors[product.id] = product
    return companies, brands, competitors

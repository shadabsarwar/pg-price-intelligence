from models.product import Product


def quantity(product: Product) -> tuple[float, str] | None:
    """Total package content; size_value is per item, pack_quantity is item count."""
    if product.size_value is None or product.pack_quantity is None or product.unit is None:
        return None
    factors = {"L": (1, "L"), "ml": (0.001, "L"), "kg": (1, "kg"),
               "g": (0.001, "kg"), "diaper": (1, "diaper"), "razor": (1, "razor")}
    factor, dimension = factors[product.unit]
    return product.size_value * product.pack_quantity * factor, dimension


def normalize_price(product: Product, price: float | None) -> tuple[float | None, str | None]:
    amount = quantity(product)
    if amount is None:
        return None, None
    total, unit = amount
    scale = 0.1 if unit == "L" and ((product.subcategory or "").casefold() == "shampoo" or product.category.casefold() in {"personal care", "hair care", "skin care"}) else 1
    normalized_unit = "100 ml" if scale == 0.1 else unit
    return (round(price / total * scale, 6) if price is not None else None), normalized_unit

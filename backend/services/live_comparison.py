"""Live observations stay independent of the development catalogue prices."""
from services.competitor_matching import find_competitors
from services.price_normalization import normalize_price


def live_offers(product):
    rows = []
    for row in product.listings:
        if row.data_source != "verified" or row.collection_method != "live" or row.data_status not in {"LIVE", "STALE"}:
            continue
        unit_price, unit = normalize_price(product, row.price)
        rows.append({"platform": row.platform, "product_name": row.product_name,
            "company": product.company, "brand": product.brand,
            "product_image": str(row.image_url) if row.image_url else None,
            "product_url": str(row.product_url) if row.product_url else None,
            "current_price": row.price, "original_price": row.original_price,
            "currency": row.currency, "product_size": product.size,
            "price_per_unit": unit_price, "normalized_unit": unit,
            "availability": row.availability, "collected_at": row.last_updated,
            "data_status": row.data_status, "source_type": "approved_source"})
    return rows


def build_live_comparison(product, candidates, source_results):
    pg_offers = live_offers(product)
    competitor_offers = [row for candidate, _ in find_competitors(product, candidates)
                         for row in live_offers(candidate)]
    all_rows = [*pg_offers, *competitor_offers]
    status = "LIVE" if any(row["data_status"] == "LIVE" for row in all_rows) else "STALE" if all_rows else "UNAVAILABLE"
    return {"product_id": product.id, "data_status": status,
            "reason": "No permitted live retailer observations are available." if not all_rows else None,
            "pg_product": {"product_name": product.product_name, "offers": pg_offers},
            "competitor_products": competitor_offers,
            "sources": source_results,
            "collected_at": max((row["collected_at"] for row in all_rows), default=None)}

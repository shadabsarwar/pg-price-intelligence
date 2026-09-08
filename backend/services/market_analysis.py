from models.company import Company
from models.intelligence import CompetitorComparison, CompetitorMatch, MarketPosition, ProductPrice
from models.product import Product
from services.comparison import compare_product
from services.competitor_matching import find_competitors
from services.price_normalization import normalize_price


def price_summary(product: Product) -> ProductPrice:
    comparison = compare_product(product)
    normalized, unit = normalize_price(product, comparison.lowest_price)
    return ProductPrice(product=product, best_price=comparison.lowest_price, highest_price=comparison.highest_price,
                        normalized_price=normalized, normalized_unit=unit,
                        platforms_found=comparison.number_of_platforms, data_source=comparison.data_source,
                        data_status=product.data_status, last_updated=comparison.last_updated)


def difference(price, baseline):
    if price is None or baseline is None:
        return None, None
    return round(price - baseline, 6), round((price - baseline) / baseline * 100, 4) if baseline else None


def analyze_market(master: Product, candidates: list[Product], companies: dict[str, Company], approved: set[int] | None = None) -> CompetitorComparison:
    pg = price_summary(master)
    matches = []
    for product, match in find_competitors(master, candidates, approved):
        summary = price_summary(product)
        comparable = (summary.data_source == pg.data_source and product.currency == master.currency
                      and summary.normalized_unit == pg.normalized_unit and pg.normalized_unit is not None
                      and summary.best_price is not None and pg.best_price is not None
                      and summary.data_status not in {"STALE", "ERROR"} and pg.data_status not in {"STALE", "ERROR"})
        delta, percent = difference(summary.best_price, pg.best_price) if comparable else (None, None)
        unit_delta, unit_percent = difference(summary.normalized_price, pg.normalized_price) if comparable else (None, None)
        matches.append(CompetitorMatch(**summary.model_dump(), match_confidence=match["confidence"],
                       match_breakdown=match["breakdown"], match_explanation=match["explanation"],
                       price_difference=delta, percentage_difference=percent,
                       normalized_difference=unit_delta, normalized_percentage_difference=unit_percent,
                       comparable_prices=comparable))
    eligible = [item for item in matches if item.comparable_prices and item.normalized_price is not None]
    if matches:
        closest = max(item.match_confidence for item in matches)
        for item in matches:
            if item.match_confidence == closest:
                item.highlights.append("Closest match")
    if eligible:
        for item in eligible:
            if item.best_price == min(row.best_price for row in eligible):
                item.highlights.append("Cheapest package")
            if item.best_price == max(row.best_price for row in eligible):
                item.highlights.append("Most expensive package")
            if item.normalized_price == min(row.normalized_price for row in eligible):
                item.highlights.append("Best value per unit")
    average = sum(item.normalized_price for item in eligible) / len(eligible) if eligible else None
    market = MarketPosition(normalized_unit=pg.normalized_unit, pg_price=pg.best_price,
                            pg_normalized_price=pg.normalized_price,
                            market_average=round(average, 6) if average is not None else None,
                            cheapest_competitor=min((item.normalized_price for item in eligible), default=None),
                            percentage_above_market=difference(pg.normalized_price, average)[1],
                            comparable_competitor_count=len(eligible), data_status=pg.data_status)
    company_ids = {item.product.company_id for item in matches}
    timestamps = [item.last_updated for item in [pg, *matches] if item.last_updated]
    return CompetitorComparison(pg_product=pg, competitors=matches,
                                competitor_companies=[company for key, company in companies.items() if key in company_ids],
                                market_position=market, data_status=pg.data_status,
                                last_updated=max(timestamps, default=None))

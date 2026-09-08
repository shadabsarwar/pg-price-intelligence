from pydantic import AwareDatetime, BaseModel, Field

from models.company import Company
from models.platform_listing import DataStatus
from models.product import Product


class ProductPrice(BaseModel):
    product: Product
    best_price: float | None
    highest_price: float | None
    normalized_price: float | None
    normalized_unit: str | None
    platforms_found: int
    data_source: str
    data_status: DataStatus
    last_updated: AwareDatetime | None


class CompetitorMatch(ProductPrice):
    match_confidence: float
    match_breakdown: dict[str, float]
    match_explanation: str
    price_difference: float | None
    percentage_difference: float | None
    normalized_difference: float | None
    normalized_percentage_difference: float | None
    comparable_prices: bool
    highlights: list[str] = Field(default_factory=list)


class MarketPosition(BaseModel):
    basis: str = "Available same-source, same-currency normalized competitor prices; competitor-only average."
    normalized_unit: str | None = None
    pg_price: float | None = None
    pg_normalized_price: float | None = None
    market_average: float | None = None
    cheapest_competitor: float | None = None
    percentage_above_market: float | None = None
    comparable_competitor_count: int = 0
    data_status: DataStatus


class CompetitorComparison(BaseModel):
    pg_product: ProductPrice
    competitors: list[CompetitorMatch]
    competitor_companies: list[Company]
    market_position: MarketPosition
    data_status: DataStatus
    last_updated: AwareDatetime | None

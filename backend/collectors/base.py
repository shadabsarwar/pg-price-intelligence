from abc import ABC, abstractmethod
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, computed_field, field_validator

from models.product import PlatformListing, Product


class RetailerListing(BaseModel):
    """Retailer facts only. Unknown metadata stays null, never inferred from brand names."""

    platform_product_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    brand: str | None = None
    company: str | None = None
    category: str | None = None
    size: str | None = None
    barcode: str | None = None
    current_price: float = Field(ge=0, allow_inf_nan=False)
    original_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: Literal["QAR"] = "QAR"
    product_url: HttpUrl
    image_url: HttpUrl | None = None
    availability: Literal["available", "out_of_stock", "unknown"] = "unknown"
    source_platform: str
    collected_at: AwareDatetime


class CollectorSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=200)

    @field_validator("query", mode="before")
    @classmethod
    def clean_query(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value


class CollectorError(BaseModel):
    code: str
    message: str


class CollectorSearchResponse(BaseModel):
    success: bool = False
    error_code: str | None = None
    message: str = "Live data currently unavailable"
    retailer_requests: int = Field(default=0, ge=0)
    listings: list[RetailerListing] = Field(default_factory=list)
    listings_found: int = 0
    source_platform: str
    data_status: Literal["LIVE", "VERIFIED", "STALE", "DEMO", "ERROR"] = "ERROR"
    collected_at: AwareDatetime | None = None
    errors: list[CollectorError] = Field(default_factory=list)
    integrated_count: int = 0
    unmatched_count: int = 0


class ConnectorStatus(BaseModel):
    connector_name: str
    source_platform: str
    status: str
    data_access_status: str = "APPROVED_SOURCE_REQUIRED"
    retailer_requests: int = Field(default=0, ge=0)
    reason: str = "No approved API, product feed, or permitted data source has been configured."
    data_status: Literal["LIVE", "VERIFIED", "STALE", "DEMO", "ERROR"] = "ERROR"
    last_successful_collection: AwareDatetime | None = None
    last_attempt_at: AwareDatetime | None = None
    number_of_products_collected: int = 0
    message: str = "Live data currently unavailable"
    errors: list[CollectorError] = Field(default_factory=list)

    @computed_field
    @property
    def platform(self) -> str:
        return self.source_platform


class BaseCollector(ABC):
    """Adapters return normalized, exact-product matches, with source timestamps.

    Set data_source='verified' only after validating an approved source and the
    product/pack-size match. Do not refresh timestamps just because data is read.
    """

    platform = "Unconfigured platform"
    enabled = False

    @abstractmethod
    def collect(self, product: Product) -> list[PlatformListing]:
        raise NotImplementedError

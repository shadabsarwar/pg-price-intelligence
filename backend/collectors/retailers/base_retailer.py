"""Validated observation contract; unknown facts stay null."""
from abc import ABC, abstractmethod
from typing import Literal
from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, model_validator


class RetailerProduct(BaseModel):
    platform: str
    product_name: str = Field(min_length=1)
    brand: str | None = None
    company: str | None = None
    category: str | None = None
    barcode: str | None = None
    retailer_sku: str | None = None
    subcategory: str | None = None
    purpose: str | None = None
    variant_name: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    current_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    original_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: Literal["QAR"] = "QAR"
    product_size: str | None = None
    product_image: HttpUrl | None = None
    product_url: HttpUrl
    availability: Literal["available", "out_of_stock", "unknown"] = "unknown"
    data_status: Literal["LIVE", "STALE"]
    collected_at: AwareDatetime
    source_type: Literal["permitted_public_page", "approved_api", "approved_feed"]


class RetailerSearchResult(BaseModel):
    platform: str
    data_status: Literal["LIVE", "STALE", "UNAVAILABLE"] = "UNAVAILABLE"
    reason: str | None = None
    products: list[RetailerProduct] = Field(default_factory=list)
    collected_at: AwareDatetime | None = None
    retailer_requests: int = 0
    policy_url: str | None = None

    @model_validator(mode="after")
    def honest_result(self):
        if self.data_status == "UNAVAILABLE":
            if self.products or self.collected_at or not self.reason:
                raise ValueError("Unavailable results require a reason and no observations.")
        elif not self.products or not self.collected_at:
            raise ValueError("Successful collection requires actual observations and timestamp.")
        elif any(row.platform != self.platform or row.data_status != self.data_status for row in self.products):
            raise ValueError("Observation platform and status must match the collection.")
        return self


class BaseRetailer(ABC):
    slug: str
    platform: str

    @abstractmethod
    def search(self, query: str) -> RetailerSearchResult:
        raise NotImplementedError

    def search_products(self, query: str) -> RetailerSearchResult:
        return self.search(query)

    def get_product_details(self, url_or_id: str) -> RetailerSearchResult:
        return RetailerSearchResult(platform=self.platform, reason='No approved detail source configured for this connector.')

    def collect_category(self, category: str) -> RetailerSearchResult:
        return self.search(category)

    def normalize_product(self, raw_product: dict) -> RetailerProduct:
        return RetailerProduct.model_validate(raw_product)


class UnavailableRetailer(BaseRetailer):
    reason: str
    policy_url: str | None = None

    def search(self, query: str) -> RetailerSearchResult:
        return RetailerSearchResult(platform=self.platform, reason=self.reason,
                                    policy_url=self.policy_url)

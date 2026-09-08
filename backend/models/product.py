from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, Field, computed_field
from models.platform_listing import DataStatus, PlatformListing


class ProductCreate(BaseModel):
    company: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    size: str = Field(min_length=1)
    barcode: str = ''
    price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    image_url: Optional[str] = None
    company_id: Optional[str] = None
    brand_id: Optional[str] = None
    subcategory: Optional[str] = None
    purpose: Optional[str] = None
    variant: Optional[str] = None
    size_value: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    unit: Optional[Literal["L", "ml", "kg", "g", "diaper", "razor"]] = None
    pack_quantity: Optional[int] = Field(default=None, gt=0)
    attributes: dict[str, str] = Field(default_factory=dict)


class Product(ProductCreate):
    id: int = Field(gt=0)
    listings: list[PlatformListing] = Field(default_factory=list)
    source_state: DataStatus = "MANUAL"
    quality_flags: list[str] = Field(default_factory=list)
    product_family: Optional[str] = None
    verified: bool = False
    updated_at: Optional[str] = None

    @computed_field
    @property
    def data_status(self) -> DataStatus:
        observations = [item for item in self.listings if item.data_source == "verified"] or self.listings
        statuses = {item.data_status for item in observations}
        if not statuses:
            return self.source_state
        if "ERROR" in statuses:
            return "ERROR"
        if "STALE" in statuses:
            return "STALE"
        if statuses == {"DEMO"}:
            return "DEMO"
        return next(iter(statuses)) if len(statuses) == 1 else self.source_state


class PriceSummary(BaseModel):
    currency: str
    data_source: Literal["demo", "verified", "none"]
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    best_deals: list[PlatformListing] = Field(default_factory=list)
    number_of_platforms: int
    last_updated: Optional[AwareDatetime] = None


class ProductComparison(PriceSummary):
    product: Product
    image_url: Optional[str] = None
    listings: list[PlatformListing]

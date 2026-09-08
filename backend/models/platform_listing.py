from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, computed_field

DataStatus = Literal["LIVE", "VERIFIED", "STALE", "DEMO", "ERROR", "IMPORTED", "MANUAL", "COLLECTED", "UNAVAILABLE"]


class PlatformListing(BaseModel):
    platform: str = Field(min_length=1)
    platform_product_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    price: float = Field(ge=0, allow_inf_nan=False)
    original_price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str = Field(default="QAR", pattern=r"^[A-Z]{3}$")
    product_url: Optional[HttpUrl] = None
    image_url: Optional[HttpUrl] = None
    availability: Literal["available", "out_of_stock", "unknown"] = "unknown"
    last_updated: AwareDatetime
    data_source: Literal["demo", "verified"] = "demo"
    source_name: str = "Development fixture"
    collection_method: Literal["demo", "feed", "live"] = "demo"
    collection_error: Optional[str] = None
    provenance: Optional[DataStatus] = None

    @computed_field
    @property
    def data_status(self) -> DataStatus:
        if self.collection_error:
            return "ERROR"
        if self.data_source == "demo":
            return "DEMO"
        age = (datetime.now(timezone.utc) - self.last_updated).total_seconds()
        if age < -60:
            return "ERROR"
        limit = 900 if self.collection_method == "live" else 86400
        if age > limit:
            return "STALE"
        if self.provenance:
            return self.provenance
        return "LIVE" if self.collection_method == "live" else "VERIFIED"

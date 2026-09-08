from pydantic import BaseModel, Field


class Brand(BaseModel):
    id: str
    name: str = Field(min_length=1)
    company_id: str
    ownership_source: str | None = None
    market_note: str = "Demo catalogue mapping; exact Qatar SKU and distribution require verification."

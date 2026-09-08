from pydantic import BaseModel, Field


class Company(BaseModel):
    id: str
    name: str = Field(min_length=1)

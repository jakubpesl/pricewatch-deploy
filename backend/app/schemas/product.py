from pydantic import BaseModel, field_validator, HttpUrl
from datetime import datetime


class DiscoveryRequest(BaseModel):
    model_number: str
    markets: list[str] | None = None  # None = all EU markets

    @field_validator("model_number")
    @classmethod
    def clean_model_number(cls, v: str) -> str:
        return v.strip()


class ProductRetailerOut(BaseModel):
    id: int
    retailer_name: str
    retailer_domain: str
    country_code: str
    product_url: str
    currency: str
    current_price: float | None
    original_price: float | None
    in_stock: bool | None
    rating: float | None
    review_count: int | None
    screenshot_url: str | None
    source: str
    last_scraped_at: datetime | None

    model_config = {"from_attributes": True}


class PricePointOut(BaseModel):
    price: float
    currency: str
    in_stock: bool | None
    observed_at: datetime

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    model_number: str
    name: str | None
    brand: str | None
    category: str | None
    ean: str | None
    image_url: str | None
    retailers: list[ProductRetailerOut] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class DiscoveryJobOut(BaseModel):
    id: int
    model_number: str
    status: str
    retailers_found: int
    sources_completed: list[str] | None
    error_message: str | None = None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}

from pydantic import BaseModel
from datetime import datetime


class HardwareOut(BaseModel):
    id: int
    type: str
    name: str
    vram: int | None = None
    socket: str | None = None
    ram_type: str | None = None
    ram_capacity_gb: int | None = None
    ram_channels: int | None = None
    avg_price: int | None = None
    price_source: str | None = None
    price_date: datetime | None = None
    price_market: str | None = None
    price_url: str | None = None
    sample_count: int | None = None
    average_method: str | None = None
    price_origin: str | None = None
    source_price_at: datetime | None = None
    price_freshness: str | None = None
    optimizer_eligibility: bool | None = None
    purchase_ready: bool | None = None

    model_config = {"from_attributes": True}

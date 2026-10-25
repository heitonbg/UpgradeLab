from pydantic import BaseModel


class HardwareOut(BaseModel):
    id: int
    type: str
    name: str
    vram: int | None = None
    socket: str | None = None
    ram_type: str | None = None
    ram_capacity_gb: int | None = None
    ram_channels: int | None = None

    model_config = {"from_attributes": True}
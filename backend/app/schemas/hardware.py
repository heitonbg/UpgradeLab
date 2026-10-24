from pydantic import BaseModel


class HardwareOut(BaseModel):
    id: int
    type: str
    name: str

    model_config = {"from_attributes": True}
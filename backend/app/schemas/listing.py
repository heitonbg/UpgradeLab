from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

Condition = Literal["Новое", "Б/У"]


class ListingCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    condition: Condition
    price: str = Field(min_length=1, max_length=50)
    contact: str = Field(min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class ListingOut(BaseModel):
    id: int
    title: str
    condition: Condition
    price: str
    contact: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
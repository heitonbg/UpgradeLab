from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import base64
import binascii
from urllib.parse import urlsplit

Condition = Literal["Новое", "Б/У"]


class ListingCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    condition: Condition
    price: str = Field(min_length=1, max_length=50)
    contact: str = Field(min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    listing_type: Literal["sale", "exchange"] = "sale"
    exchange_for: str | None = Field(default=None, max_length=500)
    photo_url: str | None = Field(default=None, max_length=1400000)

    @field_validator("title", "price", "contact")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Поле не может быть пустым")
        return value.strip()

    @field_validator("photo_url")
    @classmethod
    def valid_photo(cls, value):
        if not value:
            return None
        if value.startswith("https://") and urlsplit(value).hostname and len(value) <= 2000:
            return value
        try:
            header, encoded = value.split(",", 1)
            data = base64.b64decode(encoded, validate=True)
            valid = ((header == "data:image/jpeg;base64" and data.startswith(b"\xff\xd8\xff")) or
                     (header == "data:image/png;base64" and data.startswith(b"\x89PNG\r\n\x1a\n")) or
                     (header == "data:image/webp;base64" and data.startswith(b"RIFF") and data[8:12] == b"WEBP"))
            if valid and len(data) <= 1024 * 1024:
                return value
        except (ValueError, binascii.Error):
            pass
        raise ValueError("Добавьте HTTPS-ссылку или фото JPEG, PNG, WebP до 1 МБ")

    @model_validator(mode="after")
    def exchange_terms(self):
        if self.listing_type == "exchange" and not (self.exchange_for or "").strip():
            raise ValueError("Укажите, какой компонент или услугу хотите получить")
        return self


class ListingOut(BaseModel):
    id: int
    title: str
    condition: Condition
    price: str
    contact: str
    description: Optional[str]
    created_at: datetime
    listing_type: Literal["sale", "exchange"] = "sale"
    exchange_for: str | None = None
    photo_url: str | None = None

    model_config = {"from_attributes": True}

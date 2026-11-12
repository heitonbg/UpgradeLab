from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator, computed_field, field_serializer
import base64
import binascii
from urllib.parse import urlsplit

from app.schemas.listing_details import SellerDelivery,validate_characteristics

Condition = Literal["Новое", "Б/У", "Неисправное"]


class ListingCreate(BaseModel):
    characteristics:dict=Field(default_factory=dict)
    delivery:SellerDelivery|None=None
    @model_validator(mode="after")
    def specs_contract(self):
        self.characteristics=validate_characteristics(self.category,self.characteristics)
        return self
    title: str = Field(min_length=2, max_length=200)
    condition: Condition
    price: str = Field(min_length=1, max_length=50)
    contact: str = Field(min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    listing_type: Literal["sale", "exchange"] = "sale"
    exchange_for: str | None = Field(default=None, max_length=500)
    photo_url: str | None = Field(default=None, max_length=1400000)


    city_id: str | None = Field(default=None, max_length=100)
    category: Literal["CPU","GPU","memory","motherboard","storage","psu","case","cooler"] | None = None
    hardware_id: int | None = Field(default=None, gt=0)
    contact_type: Literal["telegram","phone","email"] | None = None
    publication_status: Literal["active","sold","withdrawn"] = "active"
    confirm_availability: bool = False

    @field_validator("city_id")
    @classmethod
    def known_city(cls, value):
        from app.services.cities import BY_ID
        if value is not None and value not in BY_ID:
            raise ValueError("Выберите город из справочника")
        return value

    @model_validator(mode="after")
    def canonical_contact(self):
        from app.services.contacts import normalize_contact
        self.contact, self.contact_type = normalize_contact(self.contact, self.contact_type)
        return self

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
        if value.startswith('https://') and len(value)<=2000:
            from app.services.network_policy import validate_url
            try:return validate_url(value).url
            except ValueError:raise ValueError('Нужна безопасная HTTPS-ссылка без учётных данных и внутренних адресов') from None
            except RuntimeError:raise ValueError('Нужна безопасная HTTPS-ссылка без учётных данных и внутренних адресов') from None
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
    characteristics:dict=Field(default_factory=dict)
    delivery:dict|None=None
    technical_assessment:dict=Field(default_factory=dict)
    seller_name:str|None=None
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

    city_id: str | None = None
    category: str | None = None
    hardware_id: int | None = None
    contact_type: str | None = None
    publication_status: str = "active"
    updated_at: datetime | None = None
    availability_confirmed_at: datetime | None = None

    @computed_field
    @property
    def city_label(self) -> str | None:
        from app.services.cities import city_name
        return city_name(self.city_id)

    @computed_field
    @property
    def seller_availability(self) -> str:
        from app.services.listing_validation import seller_availability
        return seller_availability(self)

    @field_serializer("created_at","updated_at","availability_confirmed_at")
    def utc_date(self, value):
        from app.core.price_time import iso_utc
        return iso_utc(value)

    model_config = {"from_attributes": True}


class ListingUpdate(BaseModel):
    characteristics:dict|None=None
    delivery:SellerDelivery|None=None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    condition: Condition | None = None
    price: str | None = Field(default=None, min_length=1, max_length=50)
    contact: str | None = Field(default=None, min_length=2, max_length=200)
    contact_type: Literal["telegram","phone","email"] | None = None
    description: str | None = Field(default=None, max_length=2000)
    listing_type: Literal["sale","exchange"] | None = None
    exchange_for: str | None = Field(default=None, max_length=500)
    photo_url: str | None = Field(default=None, max_length=1400000)
    city_id: str | None = Field(default=None, max_length=100)
    category: Literal["CPU","GPU","memory","motherboard","storage","psu","case","cooler"] | None = None
    hardware_id: int | None = Field(default=None, gt=0)
    publication_status: Literal["active","sold","withdrawn"] | None = None
    confirm_availability: bool = False
    model_config = {"extra":"forbid"}

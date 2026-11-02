from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
import re
from app.core.stores import STORES

Source = Literal["ozon", "avito", "wb", "yandex", "dns", "citilink", "regard", "oldi", "kns", "xcom", "onlinetrade", "nix"]
Category = Literal["CPU", "GPU", "motherboard", "memory", "storage", "psu", "case", "cooler"]
DOMAINS = {key: store["domain"] for key, store in STORES.items()}
LABELS = {key: store["name"] for key, store in STORES.items()}


def store_url(source, url):
    parsed = urlsplit(url)
    domain = DOMAINS[source]
    host = parsed.hostname or ""
    product = bool(re.search(STORES[source]["product"], parsed.path, re.I))
    return (product and parsed.scheme == "https" and not parsed.username and not parsed.password and
            parsed.port in (None, 443) and (host == domain or host.endswith("." + domain)))


class OfferInput(BaseModel):
    source: Source
    name: str = Field(min_length=2, max_length=300)
    category: Category
    price_rub: int = Field(gt=0, le=100000000)
    url: str = Field(max_length=2000)
    condition: Literal["new", "used"] = "new"
    observed_at: datetime
    model_name: str | None = Field(default=None, max_length=200)
    attributes: dict = Field(default_factory=dict)
    available: bool = True

    @field_validator("attributes")
    @classmethod
    def typed_attributes(cls, value):
        if 'nvme_2280' in value and type(value['nvme_2280']) is not bool:
            raise ValueError('Параметр nvme_2280 должен быть логическим значением')
        for key in ("capacity_gb", "modules", "watts"):
            if key in value and (type(value[key]) is not int or value[key] <= 0):
                raise ValueError(f"Параметр {key} должен быть положительным целым числом")
        for key in ("sockets", "board_formats", "psu_formats"):
            if key in value and (not isinstance(value[key], list) or not all(isinstance(v, str) for v in value[key])):
                raise ValueError(f"Параметр {key} должен содержать список строк")
        for key in ("socket", "ram_type", "form_factor", "interface"):
            if key in value and not isinstance(value[key], str):
                raise ValueError(f"Параметр {key} должен быть строкой")
        return value

    @field_validator("observed_at")
    @classmethod
    def utc_date(cls, value):
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        if value > datetime.utcnow() + timedelta(minutes=5):
            raise ValueError("Дата цены не может быть в будущем")
        return value

    @model_validator(mode="after")
    def correct_store(self):
        if not store_url(self.source, self.url):
            raise ValueError("Ссылка не принадлежит выбранной площадке")
        if self.source != "avito" and self.condition == "used":
            raise ValueError("Б/у предложения поддерживаются для Avito")
        return self


class SearchOffers(BaseModel):
    _deadline: float | None = PrivateAttr(default=None)
    query: str = Field(min_length=2, max_length=160)
    category: Category
    sources: list[Source] = Field(default_factory=lambda: list(DOMAINS), min_length=1, max_length=len(STORES))
    hardware_id: int | None = Field(default=None, gt=0)
    method: Literal["http", "browser", "discovery"] = "http"

    @model_validator(mode="after")
    def browser_batch(self):
        if self.method != "http" and len(set(self.sources)) > 3:
            raise ValueError("Для браузерного поиска выберите не больше трёх площадок за запрос")
        return self


class OfferLink(BaseModel):
    source: Source
    category: Category
    url: str = Field(max_length=2000)
    method: Literal["http", "browser"] = "http"

    @model_validator(mode="after")
    def product_link(self):
        if not store_url(self.source, self.url):
            raise ValueError("Нужна HTTPS-ссылка на товар выбранной площадки")
        return self

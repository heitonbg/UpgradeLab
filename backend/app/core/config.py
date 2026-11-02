from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Literal
from pydantic import Field, field_validator
from urllib.parse import urlsplit
import json
from app.core.stores import STORES

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "sqlite:///" + (BACKEND_DIR / "pc_upgrade.db").as_posix()
    cookie_secure: bool = False
    frontend_url: str = "http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    offers_feed_file: str = ""
    offers_feed_urls: str = "{}"
    offers_feed_tokens: str = "{}"
    offers_live_search: bool = True
    offers_browser_enabled: bool = True
    offers_browser_channel: str = "msedge"
    offers_browser_cdp_url: str = ""
    offers_browser_timeout_ms: int = Field(default=12000, ge=2000, le=30000)
    offers_browser_product_limit: int = Field(default=3, ge=1, le=5)
    offers_browser_search_engine: Literal["bing", "google", "yandex"] = "bing"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"

    @field_validator("offers_feed_urls")
    @classmethod
    def feed_mapping(cls, value):
        mapping = json.loads(value)
        if not isinstance(mapping, dict) or any(source not in STORES for source in mapping):
            raise ValueError("OFFERS_FEED_URLS должен содержать JSON-объект с известными площадками")
        for url in mapping.values():
            if not isinstance(url, str) or urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
                raise ValueError("Для выгрузки нужен HTTPS URL")
        return value

    @field_validator("offers_feed_tokens")
    @classmethod
    def feed_tokens(cls, value):
        mapping = json.loads(value)
        if not isinstance(mapping, dict) or any(key not in STORES or
                                                not isinstance(token, str) or '\n' in token or '\r' in token
                                                for key, token in mapping.items()):
            raise ValueError("OFFERS_FEED_TOKENS должен содержать JSON-объект токенов площадок")
        return value

    @field_validator("offers_browser_cdp_url")
    @classmethod
    def local_browser_only(cls, value):
        if value:
            parsed = urlsplit(value)
            if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "[::1]", "::1") or parsed.username or parsed.password:
                raise ValueError("CDP разрешён только для локального браузера по HTTP")
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Literal
from pydantic import Field, field_validator, SecretStr
from urllib.parse import urlsplit
import json
import os
from app.core.stores import STORES
from app.services.network_policy import validate_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = ("sqlite:////data/pc_upgrade.db" if os.getenv("AMVERA") == "1"
                         else "sqlite:///" + (BACKEND_DIR / "pc_upgrade.db").as_posix())
    cookie_secure: bool = Field(default_factory=lambda: os.getenv("AMVERA") == "1")
    frontend_url: str = "http://localhost:5173"
    builder_max_cpu_candidates: int = Field(default=48, ge=1, le=100)
    builder_max_gpu_candidates: int = Field(default=48, ge=1, le=100)
    builder_seconds_per_profile: float = Field(default=3.0, ge=0.1, le=10)
    openrouter_api_key: SecretStr = Field(default=SecretStr(''),exclude=True,repr=False)
    openrouter_primary_model: str = ''
    openrouter_fallback_model: str = ''
    openrouter_search_enabled: bool = False
    openrouter_allow_paid_web: bool = False
    openrouter_daily_requests: int = Field(default=20,ge=0,le=1000)
    openrouter_daily_tokens: int = Field(default=100000,ge=0,le=10000000)
    openrouter_daily_web_microusd: int = Field(default=0,ge=0,le=10000000)
    openrouter_max_output_tokens: int = Field(default=1200,ge=100,le=4000)
    openrouter_timeout_seconds: int = Field(default=20,ge=3,le=30)
    catalog_preliminary_hours: int = Field(default=72, ge=24, le=168)
    regard_download_enabled: bool = False
    regard_catalog_admin_token: SecretStr = Field(default=SecretStr(''),exclude=True,repr=False)
    regard_price_url: str = ''
    regard_source_utc_offset_minutes: int = Field(default=180,ge=-720,le=840)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    offers_feed_file: str = ""
    offers_feed_urls: str = "{}"
    offers_feed_tokens: str = "{}"
    source_permissions: str = "{}"
    offers_live_search: bool = True
    offers_http_workers: int = Field(default=2, ge=1, le=5)
    offers_browser_enabled: bool = False
    offers_browser_channel: str = Field(default_factory=lambda: "" if os.getenv("AMVERA") == "1" else "msedge")
    offers_browser_cdp_url: str = ""
    offers_browser_timeout_ms: int = Field(default=12000, ge=2000, le=30000)
    offers_browser_product_limit: int = Field(default=3, ge=1, le=5)
    offers_browser_search_engine: Literal["bing", "google", "yandex"] = "bing"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"


    # Authentication quotas: shared through SQLite, charged before password work.
    auth_login_window_seconds: int = Field(default=900, ge=10, le=86400)
    auth_login_ip_limit: int = Field(default=60, ge=1, le=100000)
    auth_login_pair_limit: int = Field(default=10, ge=1, le=100000)
    auth_login_account_limit: int = Field(default=20, ge=1, le=100000)
    auth_register_window_seconds: int = Field(default=3600, ge=10, le=86400)
    auth_register_ip_limit: int = Field(default=5, ge=1, le=100000)
    auth_register_account_limit: int = Field(default=3, ge=1, le=100000)
    auth_password_window_seconds: int = Field(default=3600, ge=10, le=86400)
    auth_password_ip_limit: int = Field(default=20, ge=1, le=100000)
    auth_password_account_limit: int = Field(default=10, ge=1, le=100000)
    auth_recovery_window_seconds: int = Field(default=3600, ge=10, le=86400)
    auth_recovery_ip_limit: int = Field(default=10, ge=1, le=100000)
    auth_recovery_account_limit: int = Field(default=3, ge=1, le=100000)
    auth_reset_ip_limit: int = Field(default=20, ge=1, le=100000)
    auth_challenge_bits: int = Field(default=18, ge=8, le=22)
    auth_challenge_ttl_seconds: int = Field(default=120, ge=30, le=600)
    auth_ipv6_prefix: int = Field(default=64, ge=32, le=128)

    @field_validator("offers_feed_urls")
    @classmethod
    def feed_mapping(cls, value):
        mapping = json.loads(value)
        if not isinstance(mapping, dict) or any(source not in STORES for source in mapping):
            raise ValueError("OFFERS_FEED_URLS должен содержать JSON-объект с известными площадками")
        for url in mapping.values():
            try:
                validate_url(url)
            except RuntimeError:
                raise ValueError("Для выгрузки нужен допустимый публичный HTTPS URL без авторизации") from None
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

from sqlalchemy import UniqueConstraint
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Index, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column,relationship
from app.db.base import Base


class Hardware(Base):
    __tablename__ = "hardware"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    type: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_score: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_score: Mapped[int] = mapped_column(Integer, nullable=False)
    cores: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vram: Mapped[int | None] = mapped_column(Integer, nullable=True)  # VRAM в ГБ (только для GPU)
    socket: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Сокет CPU (AM4, AM5, LGA1700 и т.д.)
    ram_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # DDR3, DDR4, DDR5
    ram_capacity_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Объём RAM
    ram_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 или 2 канала

    __table_args__ = (Index("ix_hardware_type_score", "type", "normalized_score"),)


class HardwareSpecification(Base):
    """Optional, provenance-carrying technical specification for one catalog item."""
    __tablename__ = "hardware_specifications"
    hardware_id: Mapped[int] = mapped_column(ForeignKey("hardware.id", ondelete="CASCADE"), primary_key=True)
    normalized_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    specs_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    conflicts_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Listing(Base):
    __tablename__ = "listings"
    details:Mapped["ListingDetails"] = relationship('ListingDetails',uselist=False,cascade='all, delete-orphan',lazy='selectin')
    @property
    def characteristics(self):
        import json
        try:return json.loads(self.details.data) if self.details else {}
        except (ValueError,TypeError):return {}


    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    condition: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[str] = mapped_column(String(50), nullable=False)
    contact: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_type: Mapped[str] = mapped_column(String(20), default="sale", server_default="sale")
    exchange_for: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hardware_id: Mapped[int | None] = mapped_column(ForeignKey("hardware.id"), nullable=True)
    contact_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    publication_status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    availability_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )


class HardwarePrice(Base):
    __tablename__ = "hardware_prices"
    hardware_id: Mapped[int] = mapped_column(ForeignKey("hardware.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    price_rub: Mapped[int] = mapped_column(Integer)
    market: Mapped[str] = mapped_column(String(40))
    source_url: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
    sample_count: Mapped[int] = mapped_column(Integer, default=1)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(Text)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ListingOwner(Base):
    __tablename__ = "listing_owners"
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class SavedBuild(Base):
    __tablename__ = "saved_builds"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class ResetRequestLimit(Base):
    __tablename__ = "reset_request_limits"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class StoreOffer(Base):
    __tablename__ = "store_offers"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    url: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(20), index=True)
    price_rub: Mapped[int] = mapped_column(Integer)
    condition: Mapped[str] = mapped_column(String(10), default="new")
    hardware_id: Mapped[int | None] = mapped_column(ForeignKey("hardware.id"), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    origin: Mapped[str] = mapped_column(String(20))
    attributes: Mapped[str] = mapped_column(Text, default="{}")


class OfferSearch(Base):
    __tablename__ = "offer_searches"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime)
    statuses: Mapped[str] = mapped_column(Text)


class SearchJob(Base):
    __tablename__ = 'search_jobs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), index=True)
    progress: Mapped[str] = mapped_column(String(300))
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_hash: Mapped[str] = mapped_column(String(64))
    bits: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class CatalogAccess(Base):
    __tablename__ = 'catalog_access'
    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    rights: Mapped[str] = mapped_column(Text)
    public_enabled: Mapped[int] = mapped_column(Integer, default=0)
    fixture: Mapped[int] = mapped_column(Integer, default=0)


class CatalogProduct(Base):
    """Source identity and private normalized record, not a second hardware catalogue."""
    __tablename__ = 'catalog_products'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    external_key: Mapped[str] = mapped_column(String(200))
    payload: Mapped[str] = mapped_column(Text)
    offer_id: Mapped[int | None] = mapped_column(ForeignKey('store_offers.id'), nullable=True, unique=True)


class CatalogImport(Base):
    __tablename__ = 'catalog_imports'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    report: Mapped[str] = mapped_column(Text)


class CatalogObservation(Base):
    __tablename__ = 'catalog_observations'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(64), index=True)
    import_key: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime)


class ListingDelivery(Base):
    __tablename__='listing_delivery'
    listing_id:Mapped[int]=mapped_column(ForeignKey('listings.id'),primary_key=True)
    evidence:Mapped[str]=mapped_column(Text)


class ListingDetails(Base):
    __tablename__='listing_details'
    listing_id:Mapped[int]=mapped_column(ForeignKey('listings.id'),primary_key=True)
    data:Mapped[str]=mapped_column(Text)


class CatalogDailyPrice(Base):
    __tablename__='catalog_daily_prices'
    product_key:Mapped[str]=mapped_column(String(64),primary_key=True)
    source_day:Mapped[str]=mapped_column(String(10),primary_key=True)
    source:Mapped[str]=mapped_column(String(20),index=True)
    price_kopecks:Mapped[int]=mapped_column(Integer)
    import_key:Mapped[str]=mapped_column(String(64))

class CatalogPriceCorrection(Base):
    __tablename__='catalog_price_corrections'
    id:Mapped[int]=mapped_column(primary_key=True)
    product_key:Mapped[str]=mapped_column(String(64),index=True)
    source_day:Mapped[str]=mapped_column(String(10))
    previous_price_kopecks:Mapped[int]=mapped_column(Integer)
    previous_import_key:Mapped[str]=mapped_column(String(64))
    import_key:Mapped[str]=mapped_column(String(64))

class CatalogSyncRun(Base):
    __tablename__='catalog_sync_runs'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    source:Mapped[str]=mapped_column(String(20),index=True)
    started_at:Mapped[datetime]=mapped_column(DateTime)
    finished_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    status:Mapped[str]=mapped_column(String(20))
    report:Mapped[str]=mapped_column(Text,default='{}')

class ExternalSearchJob(Base):
    __tablename__='external_search_jobs'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    request_key:Mapped[str]=mapped_column(String(64),index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    status:Mapped[str]=mapped_column(String(20))
    result:Mapped[str]=mapped_column(Text,default='{}')

class AiDailyBudget(Base):
    __tablename__='ai_daily_budgets'
    day:Mapped[str]=mapped_column(String(10),primary_key=True)
    requests:Mapped[int]=mapped_column(Integer,default=0)
    reserved_tokens:Mapped[int]=mapped_column(Integer,default=0)
    reserved_microusd:Mapped[int]=mapped_column(Integer,default=0)
    blocked_until:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    errors:Mapped[int]=mapped_column(Integer,default=0)
    used_tokens:Mapped[int]=mapped_column(Integer,default=0)
    used_microusd:Mapped[int]=mapped_column(Integer,default=0)

class BenchmarkSubmission(Base):
    """Account-submitted game run awaiting human review; never part of public aggregates."""
    __tablename__='benchmark_submissions'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    created_at:Mapped[datetime]=mapped_column(DateTime,index=True)
    status:Mapped[str]=mapped_column(String(20),default='pending',index=True)
    payload:Mapped[str]=mapped_column(Text)
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    reviewed_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'),nullable=True)
    review_note:Mapped[str|None]=mapped_column(String(500),nullable=True)


class SharedConfiguration(Base):
    __tablename__ = 'shared_configurations'
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    payload: Mapped[str] = mapped_column(Text)
    __table_args__ = (Index('ix_shared_owner_fingerprint', 'user_id', 'fingerprint', unique=True),)


class BenchmarkCapture(Base):
    __tablename__ = 'benchmark_captures'
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey('benchmark_submissions.id'), unique=True)
    evidence: Mapped[str] = mapped_column(Text)


class BenchmarkQuota(Base):
    __tablename__ = 'benchmark_quotas'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer)


class BenchmarkSource(Base):
    """License and immutable snapshot provenance for a benchmark publisher."""
    __tablename__ = 'benchmark_sources'
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    publisher: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    license: Mapped[str] = mapped_column(String(80), nullable=False)
    attribution: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_manifest: Mapped[str] = mapped_column(Text, nullable=False, default='[]')


class BenchmarkMeasurement(Base):
    """Normalized published measurement; complete original fields stay in payload."""
    __tablename__ = 'benchmark_measurements'
    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_fingerprint: Mapped[str] = mapped_column(ForeignKey('benchmark_sources.fingerprint'), nullable=False, index=True)
    game: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    cpu: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    cpu_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    gpu: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    gpu_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    resolution: Mapped[str | None] = mapped_column(String(30), nullable=True)
    preset: Mapped[str | None] = mapped_column(String(80), nullable=True)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    record_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    average_fps: Mapped[float] = mapped_column(Float, nullable=False)
    one_percent_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    series_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index('ix_bench_game_normalized_pair', 'game', 'cpu_key', 'gpu_key', 'resolution', 'preset'),)


class SteamRequirements(Base):
    __tablename__ = 'steam_requirements'
    game_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    app_id: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(240), default='')
    minimum_html: Mapped[str] = mapped_column(Text, default='')
    recommended_html: Mapped[str] = mapped_column(Text, default='')
    parsed_json: Mapped[str] = mapped_column(Text, default='{}')
    source_url: Mapped[str] = mapped_column(String(300), default='')
    source_type: Mapped[str] = mapped_column(String(60), default='steam_developer_requirements')
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    parsing_status: Mapped[str] = mapped_column(String(40), default='pending')
    match_confidence: Mapped[str] = mapped_column(String(20), default='none')
    parser_version: Mapped[str] = mapped_column(String(40), default='steam_requirements_v1')
    content_sha256: Mapped[str] = mapped_column(String(64), default='')

class SteamEnrichmentTask(Base):
    __tablename__ = 'steam_enrichment_tasks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(40), default='requirements', nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='queued', nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint('game_id','task_type',name='uq_steam_game_task'),
        Index('ix_steam_queue_due','status','next_attempt_at'),
    )

class SteamSourceState(Base):
    __tablename__ = 'steam_source_state'
    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    next_request_at: Mapped[datetime | None] = mapped_column(DateTime)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(String(200))

from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
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


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    condition: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[str] = mapped_column(String(50), nullable=False)
    contact: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

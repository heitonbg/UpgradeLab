from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, Index
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
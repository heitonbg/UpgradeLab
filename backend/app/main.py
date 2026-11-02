from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import hardware, calculate, listings, autodetect, account
from app.db.base import Base, engine, SessionLocal
from app.db import models  # noqa: F401
from app.db.models import Hardware
from sqlalchemy import select, inspect, text

def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)
    # Additive migration for existing installations; no listings are discarded.
    columns = {column["name"] for column in inspect(engine).get_columns("listings")}
    with engine.begin() as connection:
        for name, definition in {"listing_type": "VARCHAR(20) NOT NULL DEFAULT 'sale'",
                                 "exchange_for": "VARCHAR(500)", "photo_url": "TEXT"}.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE listings ADD COLUMN {name} {definition}"))
    with SessionLocal() as db:
        has_hardware = db.scalar(select(Hardware.id).limit(1)) is not None
    if not has_hardware:
        from scripts.init_db import seed
        seed()
    from app.services.prices import load_price_cache
    with SessionLocal() as db:
        load_price_cache(db)
        from app.services.offers import load_offer_file
        load_offer_file(db)
    app = FastAPI(title="UpgradeLab", version="1.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(hardware.router)
    app.include_router(calculate.router)
    app.include_router(listings.router)
    app.include_router(autodetect.router)
    app.include_router(account.router)
    from app.api import recovery, offers
    app.include_router(recovery.router)
    app.include_router(offers.router)

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app

app = create_app()

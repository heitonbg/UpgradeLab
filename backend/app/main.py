from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import hardware, calculate, listings, autodetect, account
from app.db.base import Base, engine, SessionLocal
from app.db import models  # noqa: F401
from app.db.models import Hardware
from sqlalchemy import select

def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        has_hardware = db.scalar(select(Hardware.id).limit(1)) is not None
    if not has_hardware:
        from scripts.init_db import seed
        seed()
    from app.services.prices import load_price_cache
    with SessionLocal() as db:
        load_price_cache(db)
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

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app

app = create_app()

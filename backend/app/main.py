from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
from starlette.staticfiles import StaticFiles
from app.core.config import settings
from app.api import hardware, calculate, listings, autodetect, account
from app.db.base import Base, engine, SessionLocal
from app.db import models  # noqa: F401
from app.db.models import Hardware
from sqlalchemy import select

def create_app() -> FastAPI:
    Base.metadata.create_all(bind=engine)
    from app.db.migrations import migrate_listings
    migrate_listings(engine)
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

    from app.api import games, catalog_history, product_discovery, catalog_admin, catalog_public
    app.include_router(product_discovery.router)
    app.include_router(catalog_history.router)
    app.include_router(catalog_admin.router)
    app.include_router(catalog_public.router)
    app.include_router(games.router)
    app.include_router(hardware.router)
    app.include_router(calculate.router)
    app.include_router(listings.router)
    app.include_router(autodetect.router)
    app.include_router(account.router)
    from app.api import recovery, offers
    app.include_router(recovery.router)
    app.include_router(offers.router)
    from app.api import search_jobs
    app.include_router(search_jobs.router)
    from app.services.search_jobs import recover_jobs
    recover_jobs()

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok", "search_revision": "server-jobs-http-v2"}

    # The Amvera root Dockerfile builds Vite and places its production assets
    # next to this backend. Local development keeps using the Vite dev server.
    frontend_dist = Path(os.getenv('FRONTEND_DIST', Path(__file__).resolve().parents[2] / 'web-dist')).resolve()
    if frontend_dist.is_dir():
        app.mount('/', StaticFiles(directory=frontend_dist, html=True), name='frontend')

    return app

app = create_app()

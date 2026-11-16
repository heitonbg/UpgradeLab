from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import threading
from starlette.staticfiles import StaticFiles
from app.core.config import settings
from app.api import hardware, calculate, listings, autodetect, account
from app.db.base import Base, engine, SessionLocal
from app.db import models  # noqa: F401
from app.db.models import Hardware
from sqlalchemy import select

def create_app() -> FastAPI:
    from app.db.migrations import migrate_steam_requirements
    migrate_steam_requirements(engine)
    Base.metadata.create_all(bind=engine)
    from app.db.migrations import migrate_listings, migrate_benchmarks, migrate_hardware_specifications
    migrate_listings(engine)
    migrate_benchmarks(engine)
    migrate_hardware_specifications(engine)
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

    @app.on_event("startup")
    def start_steam_worker():
        app.state.steam_worker = None
        if settings.steam_requirements_enabled and settings.steam_worker_enabled:
            from app.services.steam_lifecycle import SteamSupervisor
            app.state.steam_worker = SteamSupervisor()
            app.state.steam_worker.start()

    @app.on_event("shutdown")
    def stop_steam_worker():
        supervisor = getattr(app.state, 'steam_worker', None)
        if supervisor is not None:
            supervisor.close()

    @app.on_event("startup")
    def start_regard_import():
        if os.getenv("AMVERA") == "1":
            from scripts.startup import run_import
            threading.Thread(target=run_import, name="regard-bootstrap", daemon=True).start()

    @app.on_event("startup")
    def import_benchmark_snapshot():
        if settings.benchmark_import_on_start:
            from app.services.benchmark_storage import import_curated_benchmarks
            with SessionLocal() as db:
                import_curated_benchmarks(db)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api import games, benchmarks, catalog_history, product_discovery, catalog_admin, catalog_public
    from app.api import shared_builds
    app.include_router(shared_builds.router)
    app.include_router(benchmarks.router)
    app.include_router(product_discovery.router)
    app.include_router(catalog_history.router)
    app.include_router(catalog_admin.router)
    app.include_router(catalog_public.router)
    from app.api import steam_requirements
    app.include_router(steam_requirements.router)
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

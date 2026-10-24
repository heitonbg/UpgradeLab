from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import hardware, calculate, listings, autodetect # <-- ДОБАВИТЬ autodetect

def create_app() -> FastAPI:
    app = FastAPI(title="PC Upgrade MVP", version="1.0.0")

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
    app.include_router(autodetect.router) # <-- ДОБАВИТЬ ЭТУ СТРОКУ

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app

app = create_app()
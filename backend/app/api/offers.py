from fastapi import APIRouter, HTTPException
from app.api.deps import DBSession
from app.db.models import Hardware
from app.schemas.offers import SearchOffers, OfferLink, LABELS
from app.services.offers import search_offers, available_offers, upsert, public_offer
from app.services.store_providers import fetch, parse_html
from app.api.account import AuthUser
from app.db.models import StoreOffer, OfferSearch
from sqlalchemy import select
from threading import BoundedSemaphore
from urllib.parse import urlsplit, urlunsplit
from app.core.config import settings
import json
from datetime import datetime

router = APIRouter(prefix="/api/offers", tags=["offers"])
slots = BoundedSemaphore(3)


@router.post("/search")
def search(payload: SearchOffers, db: DBSession):
    if payload.hardware_id:
        hw = db.get(Hardware, payload.hardware_id)
        if not hw or hw.type != payload.category:
            raise HTTPException(400, "Компонент не соответствует категории поиска")
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Поиск занят. Повторите запрос через несколько секунд.")
    try:
        return search_offers(db, payload)
    finally:
        slots.release()


@router.post("/from-url")
def from_url(payload: OfferLink, db: DBSession, user: AuthUser):
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Поиск занят. Повторите запрос через несколько секунд.")
    try:
        if payload.method == "browser":
            from app.services.browser_offers import read_browser_product
            rows = read_browser_product(payload.source, payload.url, payload.category)
        else:
            rows = parse_html(payload.source, fetch(payload.url, store=payload.source, product=True), payload.category, payload.url,
                              require_single_price=True)
            for row in rows:
                row.attributes['price_verification'] = {'status': 'verified',
                    'checked_at': datetime.utcnow().isoformat(), 'method': 'product_page'}
        def canonical(url):
            parsed = urlsplit(url)
            return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip('/'), '', ''))
        rows = [row for row in rows if canonical(row.url) == canonical(payload.url)]
        if not rows:
            raise ValueError("No exact product")
        upsert(db, rows, "browser_page" if payload.method == "browser" else "product_page")
        offer = db.scalar(select(StoreOffer).where(StoreOffer.url == rows[0].url))
        return public_offer(offer)
    except Exception:
        raise HTTPException(502, "Не удалось получить цену товара: площадка ограничила доступ или не отдала данные. Неподтверждённая цена не добавлена.")
    finally:
        slots.release()


@router.get("/status")
def status(db: DBSession):
    from app.services.browser_offers import browser_diagnostics
    rows = available_offers(db)
    feeds = json.loads(settings.offers_feed_urls)
    latest = {}
    for search in db.scalars(select(OfferSearch).order_by(OfferSearch.checked_at.desc()).limit(50)):
        for result in json.loads(search.statuses):
            latest.setdefault(result['source'], {'status': result['status'], 'method': result.get('method', 'http'),
                'message': result['message'], 'checked_at': result.get('checked_at', search.checked_at.isoformat() + 'Z'),
                'search_engines': result.get('search_engines', [])})
    return {"search_mode": "public_pages", "search_revision": "server-jobs-http-v2",
            "http_workers": settings.offers_http_workers, "browser": browser_diagnostics(),
            "sources": [{"source": source, "label": label,
                         "fresh_offers": sum(row.source == source for row in rows),
                         "feed_configured": source in feeds,
                         "public_search_enabled": settings.offers_live_search,
                         "browser_enabled": settings.offers_browser_enabled,
                         "last_search": latest.get(source)} for source, label in LABELS.items()]}

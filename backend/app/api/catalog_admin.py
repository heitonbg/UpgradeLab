"""Loopback-only, token-protected view of explicitly authorized private Regard analysis."""
import hmac
import ipaddress
import json
from datetime import timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.core.config import settings
from app.core.price_time import as_utc, utc_now
from app.db.models import CatalogAccess, CatalogDailyPrice, CatalogProduct, StoreOffer
from app.schemas.offers import store_url
from app.services.catalog_access import closed_catalog_analysis, validated_rights

router = APIRouter(prefix='/api/admin/catalog/regard', tags=['local-private-catalog'])


def _authorize(request: Request, db, token: str | None):
    configured = settings.regard_catalog_admin_token.get_secret_value()
    if not configured:
        raise HTTPException(404, 'Локальный просмотр каталога выключен')
    try:
        peer = ipaddress.ip_address(request.client.host if request.client else '')
    except ValueError:
        peer = None
    if not peer or not peer.is_loopback:
        raise HTTPException(404, 'Локальный просмотр каталога недоступен')
    if not token or not hmac.compare_digest(token, configured):
        raise HTTPException(403, 'Нет доступа к закрытому каталогу')
    from app.services.catalog_access import analysis_database
    try:
        analysis_database(db.get_bind())
    except ValueError:
        raise HTTPException(404, 'Локальный просмотр каталога недоступен') from None
    access = db.get(CatalogAccess, 'regard')
    rights = validated_rights(access) if access else None
    if (not access or not rights or rights.source != 'regard' or not rights.development
            or bool(access.fixture)):
        raise HTTPException(404, 'Закрытый каталог не разрешён для локального просмотра')


def _status(payload):
    availability = payload.get('availability')
    state = {'in_stock': 'В наличии по прайс-листу',
             'out_of_stock': 'Нет в наличии по прайс-листу'}.get(availability, 'Наличие в прайс-листе не указано')
    if payload.get('missing_from_feed'):
        return 'Отсутствует в последнем импорте'
    if payload.get('analysis_eligible'):
        return state + ' · доступен только в локальном анализе'
    labels = {
        'ambiguous': 'модель сопоставлена неоднозначно',
        'unmatched': 'нет точного соответствия компоненту',
        'missing_product_url': 'страница товара в прайсе отсутствует',
        'availability_unknown': 'наличие не указано',
        'out_of_stock': 'по прайсу нет в наличии',
        'unknown_source_date': 'дата цены не указана',
    }
    reasons = [labels.get(str(item), 'проверка не пройдена') for item in (payload.get('reasons') or [])[:3]]
    return state + (' · ' + '; '.join(dict.fromkeys(reasons)) if reasons else '')


def _card(item, db):
    try:
        payload = json.loads(item.payload)
    except (TypeError, ValueError):
        payload = {}
    if payload.get('missing_from_feed'):
        return None
    offer = db.get(StoreOffer, item.offer_id) if item.offer_id else None
    product_url = payload.get('product_url') or (offer.url if offer else None)
    if not product_url or not store_url('regard', product_url):
        product_url = None
    image_url = payload.get('image_url')
    if not isinstance(image_url, str) or not image_url.startswith('https://'):
        image_url = None
    try:
        price = float(Decimal(str(payload['price'])))
        if not (price > 0 and price < 100_000_000):
            price = None
    except (KeyError, TypeError, ValueError, InvalidOperation):
        price = None
    return {
        'product_key': item.key,
        'catalog_product_id': item.key,
        'store_offer_id': item.offer_id,
        'name': payload.get('title') or (offer.name if offer else 'Без названия'),
        'manufacturer': payload.get('brand') or None,
        'price_rub': price,
        'price_date': payload.get('source_updated_at'),
        'category': payload.get('category'),
        'status': _status(payload),
        'availability': payload.get('availability') or 'unknown',
        'product_url': product_url,
        'image_url': image_url,
        'history_available': True,
    }


@router.get('')
def list_catalog(
    request: Request,
    response: Response,
    db: DBSession,
    admin_token: str | None = Header(default=None, alias='X-UpgradeLab-Catalog-Admin'),
    q: str = Query(default='', max_length=120),
    category: str | None = Query(default=None, pattern='^(CPU|GPU|motherboard|memory|storage|psu|case|cooler)$'),
    offset: int = Query(default=0, ge=0, le=100000),
    limit: int = Query(default=60, ge=1, le=100),
):
    _authorize(request, db, admin_token)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Vary'] = 'X-UpgradeLab-Catalog-Admin'
    with closed_catalog_analysis(db.get_bind()):
        products = list(db.scalars(select(CatalogProduct).where(CatalogProduct.source == 'regard').order_by(CatalogProduct.key)))
        cards = [card for item in products if (card := _card(item, db)) is not None]
        query = q.strip().casefold()
        if query:
            cards = [card for card in cards if query in str(card['name']).casefold()
                     or query in str(card['manufacturer'] or '').casefold()]
        if category:
            cards = [card for card in cards if card['category'] == category]
        linked = sum(item.offer_id is not None and not json.loads(item.payload).get('missing_from_feed') for item in products)
        total = len(cards)
        import_row = db.execute(select(CatalogDailyPrice.source_day).where(
            CatalogDailyPrice.source == 'regard').order_by(CatalogDailyPrice.source_day.desc()).limit(1)).first()
        return {
            'mode': 'local_development_only',
            'public_display': False,
            'commercial_use': False,
            'source_label': 'Регард · закрытый локальный каталог',
            'source_date': import_row[0] if import_row else None,
            'catalog_product_count': sum(1 for item in products if not json.loads(item.payload).get('missing_from_feed')),
            'linked_store_offer_count': linked,
            'total': total,
            'offset': offset,
            'limit': limit,
            'items': cards[offset:offset + limit],
        }


@router.get('/{product_key}/price-history')
def history(
    product_key: str,
    request: Request,
    response: Response,
    db: DBSession,
    days: int = Query(default=14, ge=7, le=14),
    admin_token: str | None = Header(default=None, alias='X-UpgradeLab-Catalog-Admin'),
):
    if days not in (7, 14):
        raise HTTPException(422, 'Допустимы 7 или 14 дней')
    _authorize(request, db, admin_token)
    response.headers['Cache-Control'] = 'no-store'
    item = db.get(CatalogProduct, product_key)
    if not item or item.source != 'regard' or json.loads(item.payload).get('missing_from_feed'):
        raise HTTPException(404, 'История недоступна')
    access = db.get(CatalogAccess, 'regard')
    rights = validated_rights(access) if access else None
    if not rights or not rights.development:
        raise HTTPException(404, 'История недоступна')
    latest = utc_now().astimezone(timezone(timedelta(minutes=settings.regard_source_utc_offset_minutes))).date()
    cutoff = (latest - timedelta(days=days - 1)).isoformat()
    rows = list(db.scalars(select(CatalogDailyPrice).where(
        CatalogDailyPrice.product_key == product_key,
        CatalogDailyPrice.source == 'regard',
        CatalogDailyPrice.source_day >= cutoff,
    ).order_by(CatalogDailyPrice.source_day)))
    prices = [row.price_kopecks for row in rows]
    return {
        'product_id': product_key,
        'days': days,
        'observations': [{'date': row.source_day, 'price_rub': row.price_kopecks / 100} for row in rows],
        'minimum': min(prices) / 100 if prices else None,
        'maximum': max(prices) / 100 if prices else None,
        'change_rub': (prices[-1] - prices[0]) / 100 if len(prices) > 1 else None,
        'note': 'Дневные наблюдения импортированного прайс-листа; наличие и цена страницы магазина не подтверждены.',
    }

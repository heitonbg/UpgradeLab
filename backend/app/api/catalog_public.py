"""Public, paginated view of products from explicitly display-authorized catalogs."""
import json
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Query, Response
from sqlalchemy import false, func, select

from app.api.deps import DBSession
from app.db.models import CatalogAccess, CatalogProduct, StoreOffer
from app.schemas.offers import store_url
from app.services.catalog_access import validated_rights
from app.core.price_time import OFFER_TTL, OBSERVATION_SKEW, is_fresh

router = APIRouter(prefix='/api/catalog', tags=['catalog'])
VALID_CATEGORIES = ('CPU', 'GPU', 'motherboard', 'memory', 'storage', 'psu', 'case', 'cooler')


@router.get('/products')
def products(
    db: DBSession,
    response: Response,
    q: str = Query(default='', max_length=120),
    category: str | None = Query(default=None, pattern='^(CPU|GPU|motherboard|memory|storage|psu|case|cooler)$'),
    source: str = Query(default='regard', pattern='^regard$'),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=24, ge=1, le=100),
):
    response.headers['Cache-Control'] = 'no-store'
    access = db.get(CatalogAccess, source)
    rights = validated_rights(access) if access else None
    if not access or not access.public_enabled or access.fixture or not rights or not rights.public_display:
        return {'source': source, 'total': 0, 'page': page, 'page_size': page_size, 'items': []}

    query = select(CatalogProduct).where(
        CatalogProduct.source == source,
        func.coalesce(func.json_extract(CatalogProduct.payload, '$.missing_from_feed'), false()) == false(),
    )
    count_query = select(func.count()).select_from(CatalogProduct).where(
        CatalogProduct.source == source,
        func.coalesce(func.json_extract(CatalogProduct.payload, '$.missing_from_feed'), false()) == false(),
    )
    if category:
        predicate = func.json_extract(CatalogProduct.payload, '$.category') == category
        query = query.where(predicate)
        count_query = count_query.where(predicate)
    term = q.strip().casefold()
    if term:
        escaped = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        predicate = (func.lower(func.json_extract(CatalogProduct.payload, '$.title')).like(f'%{escaped}%', escape='\\') |
                     func.lower(func.json_extract(CatalogProduct.payload, '$.brand')).like(f'%{escaped}%', escape='\\') |
                     func.lower(func.json_extract(CatalogProduct.payload, '$.model')).like(f'%{escaped}%', escape='\\'))
        query = query.where(predicate)
        count_query = count_query.where(predicate)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(CatalogProduct.key).offset((page - 1) * page_size).limit(page_size))
    items = []
    for item in rows:
        try:
            payload = json.loads(item.payload)
            price = int(Decimal(str(payload.get('price'))))
        except (TypeError, ValueError, InvalidOperation):
            continue
        offer_id = item.offer_id
        offer = db.get(StoreOffer, offer_id) if offer_id else None
        metadata = json.loads(offer.attributes).get('catalog_import', {}) if offer else {}
        url = payload.get('product_url')
        if not isinstance(url, str) or not store_url(source, url):
            url = None
        availability = payload.get('availability') or 'unknown'
        price_fresh = is_fresh(payload.get('source_updated_at'), OFFER_TTL, inclusive=True,
                               future_tolerance=OBSERVATION_SKEW)
        from app.services.catalog_freshness import catalog_price_state
        catalog_state = catalog_price_state(payload.get('source_updated_at'))
        items.append({
            **catalog_state,
            'optimizer_eligibility': bool(payload.get('eligible') or payload.get('preliminary_eligible')) and availability != 'out_of_stock' and offer_id is not None and catalog_state['optimizer_eligibility'],
            'product_key': item.key,
            'offer_id': offer_id,
            'imported_at': metadata.get('imported_at'),
            'stock_status': availability,
            'product_url_status': 'derived_source_id_not_checked' if payload.get('product_url_origin') == 'regard_external_product_id' else 'source_supplied' if url else 'missing',
            'name': payload.get('title'),
            'manufacturer': payload.get('brand') or None,
            'category': payload.get('category'),
            'price_rub': price,
            'price_date': payload.get('source_updated_at'),
            'price_fresh': price_fresh,
            'availability': availability,
            'availability_label': {'in_stock': 'Указано в прайс-листе', 'out_of_stock': 'Нет в наличии по прайс-листу'}.get(availability, 'Наличие не указано'),
            'preliminary_candidate': bool(payload.get('eligible') or payload.get('preliminary_eligible')) and availability != 'out_of_stock' and offer_id is not None and catalog_state['optimizer_eligibility'],
            'image_url': payload.get('image_url') or None,
            'product_url': url,
            'url_provenance': payload.get('product_url_origin'),
            'history_available': True,
        })
    return {'source': source, 'total': total, 'page': page, 'page_size': page_size, 'items': items}


@router.get('/readiness')
def catalog_readiness(db: DBSession, response: Response):
    """Public catalogue availability, separate from /api/health."""
    from app.services.catalog_freshness import catalog_price_state
    response.headers['Cache-Control'] = 'no-store'
    import os
    from app.core.config import settings
    bootstrap_enabled = os.getenv('REGARD_BOOTSTRAP_ON_START', 'false').strip().lower() in ('1', 'true', 'yes')
    network_enabled = settings.regard_download_enabled
    access = db.get(CatalogAccess, 'regard')
    rights = validated_rights(access) if access else None
    automatic_download_allowed = bool(rights and rights.automatic_download)
    download_status = ('enabled' if bootstrap_enabled and network_enabled and automatic_download_allowed
                       else 'bootstrap_disabled' if not bootstrap_enabled
                       else 'network_disabled' if not network_enabled
                       else 'permission_missing')
    download = {'status': download_status, 'bootstrap_enabled': bootstrap_enabled,
                'network_enabled': network_enabled,
                'permission_granted': automatic_download_allowed,
                'daily_scheduler_enabled': settings.regard_daily_sync_enabled}
    if not access:
        return {'source': 'regard', 'ready': False, 'status': 'not_imported',
                'products': 0, 'usable_offers': 0, 'automatic_download': download}
    if not access or not access.public_enabled or access.fixture or not rights or not rights.public_display:
        return {'source': 'regard', 'ready': False, 'status': 'not_authorized',
                'products': 0, 'usable_offers': 0, 'automatic_download': download}
    rows = db.execute(select(CatalogProduct, StoreOffer.id).outerjoin(StoreOffer, CatalogProduct.offer_id == StoreOffer.id).where(CatalogProduct.source == 'regard'))
    from app.core.price_time import as_utc, iso_utc
    products = usable = 0
    newest_price = None
    for row, offer_id in rows:
        try:
            payload = json.loads(row.payload)
        except (ValueError, TypeError):
            continue
        if payload.get('missing_from_feed'):
            continue
        products += 1
        observed = as_utc(payload.get('source_updated_at'))
        if observed is not None and (newest_price is None or observed > newest_price):
            newest_price = observed
        if (offer_id and (payload.get('eligible') or payload.get('preliminary_eligible'))
                and payload.get('availability') != 'out_of_stock'
                and catalog_price_state(payload.get('source_updated_at'))['optimizer_eligibility']):
            usable += 1
    return {'source': 'regard', 'ready': usable > 0,
            'status': 'ready' if usable else 'empty_or_historical',
            'products': products, 'usable_offers': usable,
            'latest_source_price_at': iso_utc(newest_price),
            'automatic_download': download}

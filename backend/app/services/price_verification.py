"""Product-page confirmation before returning a priced automatic PC."""
import json
from datetime import timedelta
from app.core.price_time import is_fresh, iso_utc, db_now, current_verification
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select
from app.db.models import StoreOffer, Hardware
from app.services.store_providers import fetch, parse_html, source_blocked
from app.services.offers import match_offer
from app.services.search_time import remaining
from app.core.config import settings


def recent_check(metadata, minutes=15):
    return isinstance(metadata, dict) and is_fresh(metadata.get('checked_at'), timedelta(minutes=minutes))


def pending_build_prices(db, result):
    ids = {part['offer_id'] for variant in result.get('alternatives', [result])
           for part in variant['parts'] if part.get('offer_id')}
    rows = list(db.scalars(select(StoreOffer).where(StoreOffer.id.in_(ids))))
    from app.services.offers import fresh
    return [row for row in rows if not fresh(row) or (row.origin != 'feed'
               and current_verification(json.loads(row.attributes).get('price_verification', {})) is None)]


def build_prices_confirmed(db, result):
    return not pending_build_prices(db, result)


def verify_build_prices(db, result, browser_sources=None, deadline=None):
    pending = pending_build_prices(db, result)
    if not pending:
        return False
    def inspect(row):
        try:
            remaining(deadline,5)
            kwargs={'deadline':deadline} if deadline is not None else {}
            try:
                candidates = parse_html(row.source, fetch(row.url, store=row.source,product=True,**kwargs), row.category,
                                        row.url, require_single_price=True)
            except Exception:
                if not browser_sources or row.source not in browser_sources:
                    raise
                from app.services.browser_offers import read_browser_product
                remaining(deadline,5)
                candidates = read_browser_product(row.source,row.url,row.category,**kwargs)
            if len(candidates) != 1:
                raise RuntimeError('Товар не найден по точной ссылке')
            return row.id, candidates[0], None
        except TimeoutError:
            return row.id,None,'request_deadline'
        except Exception as error:
            return row.id, None, str(error)[:240]
    with ThreadPoolExecutor(max_workers=settings.offers_http_workers) as pool:
        outcomes = list(pool.map(inspect, pending))
    hardware = list(db.scalars(select(Hardware)))
    checked_at = iso_utc(db_now())
    blocked = {row.source for row in pending if source_blocked(row.source, product=True)}
    for row_id, candidate, error in outcomes:
        row = db.get(StoreOffer, row_id)
        data = json.loads(row.attributes)
        if error=='request_deadline':
            continue
        previous_check=data.get('price_verification',{})
        if previous_check.get('status')=='verified':
            data['last_verified_price']={'price_rub':row.price_rub,'checked_at':previous_check.get('checked_at'),
                'observed_at':iso_utc(row.observed_at)}
        if candidate and row.hardware_id:
            matched = match_offer(hardware, candidate)
            if not matched or matched.id != row.hardware_id:
                candidate, error = None, 'Модель на странице товара не соответствует выбранной комплектующей'
        if candidate:
            row.price_rub, row.name, row.observed_at = candidate.price_rub, candidate.name, candidate.observed_at
            row.condition = candidate.condition
            data.update(candidate.attributes)
            method = candidate.attributes.get('price_verification',{}).get('method','product_page')
            data['price_verification'] = {'status': 'verified', 'checked_at': checked_at, 'method': method}
            row.origin = 'product_page'
            data['last_verified_price']={'price_rub':row.price_rub,'checked_at':checked_at,
                                         'observed_at':iso_utc(row.observed_at)}
        else:
            data['price_verification'] = {'status': 'unavailable', 'checked_at': checked_at,
                                          'message': error or 'Цена товара не подтверждена'}
        row.attributes = json.dumps(data, ensure_ascii=False)
    # Once a shop refuses access, do not repeatedly select its other search
    # prices and hit it again. Already confirmed quotes and feeds remain usable.
    if blocked:
        for row in db.scalars(select(StoreOffer).where(StoreOffer.source.in_(blocked))):
            data = json.loads(row.attributes)
            verification = data.get('price_verification', {})
            if row.origin == 'feed' or verification.get('status') == 'verified' and recent_check(verification):
                continue
            if verification.get('status')=='verified':
                data['last_verified_price']={'price_rub':row.price_rub,'checked_at':verification.get('checked_at'),
                    'observed_at':iso_utc(row.observed_at)}
            data['price_verification'] = {'status': 'unavailable', 'checked_at': checked_at,
                                          'message': 'Площадка ограничила доступ; цена страницы не подтверждена'}
            row.attributes = json.dumps(data, ensure_ascii=False)
    db.commit()
    return True

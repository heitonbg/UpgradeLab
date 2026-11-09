"""Read-only price evidence for immutable saved build/upgrade snapshots."""
import json
import re
from sqlalchemy import select
from app.core.price_time import as_utc, iso_utc, current_verification, OFFER_TTL, VERIFICATION_TTL
from app.core import price_time
from app.db.models import StoreOffer
from app.services.offers import fresh, signature, available_offers


def amount(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def snapshot_items(result):
    """Selected configuration only; alternatives and expected resale are not purchases."""
    parts = result.get('parts') or result.get('upgrade_parts') or []
    if not parts and isinstance(result.get('upgrade_price'), dict):
        quote = result['upgrade_price']
        if amount(result.get('avg_price')) is not None:
            parts = [{**quote, 'price': result['avg_price'],
                      'name': result.get('upgrade_name') or result.get('upgrade_component') or 'Апгрейд'}]
    return [{
        'name': part.get('name') or 'Компонент', 'type': part.get('type'),
        'historical_price': amount(part.get('price')),
        'offer_id': part.get('offer_id'), 'url': part.get('price_url'),
        'offer_name': part.get('price_offer_name'),
        'observed_at': iso_utc(part.get('price_observed_at') or part.get('price_date')),
        'verified_at': iso_utc(part.get('price_verified_at')),
    } for part in parts if isinstance(part, dict)]


def linked_offer(db, item):
    url = item.get('url')
    if not url:
        return None
    row = db.get(StoreOffer, item['offer_id']) if isinstance(item.get('offer_id'), int) else db.scalar(
        select(StoreOffer).where(StoreOffer.url == url))
    if row is None or row.url != url or item.get('type') and row.category != item['type']:
        return None
    name = item.get('offer_name') or item.get('name') or ''
    normalized = lambda value: re.sub(r'\W', '', value.lower())
    if normalized(name) != normalized(row.name):
        # Legacy CPU/GPU results often store the catalogue model rather than
        # the seller's full title. Never substitute a different model.
        if item.get('offer_name') or row.category not in ('CPU', 'GPU'):
            return None
        model = signature(name, row.category)
        if not model or model != signature(row.name, row.category):
            return None
        memory = re.search(r'(\d+)\s*(?:gb|гб)\b', name, re.I)
        current_memory = re.search(r'(\d+)\s*(?:gb|гб)\b', row.name, re.I)
        if row.category == 'GPU' and memory and (not current_memory or memory[1] != current_memory[1]):
            return None
    return row


def capture_snapshot(db, result):
    """Capture evidence once; later GET/POST never update this JSON."""
    items = snapshot_items(result)
    for item in items:
        row = linked_offer(db, item)
        if row is not None and row.price_rub == item['historical_price']:
            item['offer_name'] = row.name
            item['observed_at'] = item['observed_at'] or iso_utc(row.observed_at)
            try:
                verification = json.loads(row.attributes).get('price_verification', {})
            except (ValueError, TypeError, AttributeError):
                verification = {}
            verification = verification if isinstance(verification, dict) else {}
            item['verified_at'] = item['verified_at'] or (
                current_verification(verification) if fresh(row) else None)
    return {'version': 1, 'items': items}


def review_prices(db, data):
    result = data.get('result') if isinstance(data.get('result'), dict) else {}
    historical = amount(result.get('total_price') if 'total_price' in result else result.get('avg_price'))
    stored = data.get('price_snapshot')
    items = stored.get('items') if isinstance(stored, dict) and stored.get('version') == 1 else None
    items = items if isinstance(items, list) else snapshot_items(result)
    try:
        safe_ids = {row.id for row in available_offers(db)}
    except (ValueError, TypeError, AttributeError):
        # Corrupt legacy metadata must not prevent access to historical data.
        safe_ids = set()
    output = []
    for item in items:
        if not isinstance(item, dict):
            continue
        price = amount(item.get('historical_price'))
        observed = iso_utc(item.get('observed_at'))
        entry = {**item, 'historical_price': price, 'latest_price': price if observed else None,
                 'latest_observed_at': observed, 'confirmed_price': None, 'confirmed_at': None,
                 'valid_until': None, 'changed': False, 'state': 'unknown'}
        if not item.get('offer_id') and not item.get('url'):
            entry['state'] = 'user_zero_cost' if price == 0 else (
                'historical_observation' if item.get('observed_at') else 'manual')
            if price == 0:
                entry['confirmed_price'] = 0
            output.append(entry)
            continue
        row = linked_offer(db, item)
        if row is None:
            entry['state'] = 'missing'
            output.append(entry)
            continue
        entry.update(latest_price=row.price_rub, latest_observed_at=iso_utc(row.observed_at),
                     changed=price is not None and row.price_rub != price, state='unconfirmed')
        try:
            verification = json.loads(row.attributes).get('price_verification', {})
        except (ValueError, TypeError, AttributeError):
            verification = {}
        verification = verification if isinstance(verification, dict) else {}
        checked = current_verification(verification)
        safe = row.id in safe_ids
        if fresh(row) and safe and verification.get('status') != 'unavailable' and (checked or row.origin == 'feed'):
            observed = as_utc(row.observed_at)
            until = observed + OFFER_TTL
            if checked:
                until = min(until, as_utc(checked) + VERIFICATION_TTL)
            entry.update(confirmed_price=row.price_rub, confirmed_at=checked,
                         valid_until=iso_utc(until), state='confirmed' if checked else 'feed')
        elif verification.get('status') == 'unavailable':
            entry['state'] = 'unavailable'
        output.append(entry)
    covered = bool(output) and historical is not None and all(
        item['historical_price'] is not None for item in output
    ) and sum(item['historical_price'] for item in output) == historical
    confirmed = covered and all(item['confirmed_price'] is not None for item in output)
    return {
        'historical_total': historical,
        'current_total': sum(item['confirmed_price'] for item in output) if confirmed else None,
        'items': output, 'evaluated_at': iso_utc(price_time.utc_now()), 'check_method': 'local_observations',
        'note': 'Историческая стоимость не изменяется. Последние наблюдения не гарантируют наличие товара. '
                'Проверка использует только уже полученные сервером данные; запросы к магазинам не выполняются. '
                'При отсутствии свежего подтверждения актуальная сумма неизвестна.',
    }


def saved_build_view(db, build):
    data = json.loads(build.data)
    return {**data, 'id': build.id, 'created_at': iso_utc(build.created_at),
            'price_review': review_prices(db, data)}

"""Market estimates for upgrades; never turn one listing into an average."""
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median, mean
from types import SimpleNamespace
from urllib.parse import urlsplit
import json
import re
from sqlalchemy import select
from app.db.models import Hardware, HardwarePrice, StoreOffer

from app.services.prices import price_map


def upgrade_market_rows(db, sources=None):
    """Safe seven-day observations for estimates, never a current-stock claim."""
    from app.services.offer_safety import safe_offers
    hardware = {h.id: h for h in db.scalars(select(Hardware))}
    rows = list(db.scalars(select(StoreOffer).where(
        StoreOffer.observed_at >= datetime.utcnow() - timedelta(days=7),
        StoreOffer.observed_at <= datetime.utcnow())))
    result = []
    for row in safe_offers(rows, hardware):
        verification = json.loads(row.attributes).get('price_verification', {})
        if re.search(r'не соответствует выбранной|модель.*не соответствует|outofstock|soldout|нет в наличии',
                     str(verification.get('message', '')), re.I):
            continue
        if (row.price_rub > 300 or row.category == 'CPU' and row.price_rub >= 100) and (sources is None or row.source in sources):
            result.append(row)
    return result


def avito_price_estimates(db):
    """Seven-day used-market asking-price estimates, independently of purchase stores."""
    quotes = {}
    for quote in db.scalars(select(HardwarePrice).where(HardwarePrice.source == 'avito_snapshot')):
        if quote.price_rub > 0 and datetime.utcnow() - timedelta(days=30) <= quote.observed_at <= datetime.utcnow():
            quotes[quote.hardware_id] = quote
    grouped = defaultdict(dict)
    hardware = list(db.scalars(select(Hardware)))
    hardware_by_id = {item.id: item for item in hardware}
    for row in upgrade_market_rows(db, ['avito']):
        hardware_id = row.hardware_id
        if hardware_id is None and row.category in ('CPU', 'GPU'):
            from app.services.offers import match_offer
            model = match_offer(hardware, SimpleNamespace(name=row.name, category=row.category, url=row.url, model_name=None))
            hardware_id = model.id if model else None
        model = hardware_by_id.get(hardware_id)
        minimum = 100 if model and model.type == 'CPU' and model.raw_score < 10000 else 301
        if row.source == 'avito' and hardware_id and row.category in ('CPU', 'GPU') and row.condition == 'used' and row.price_rub >= minimum:
            path = urlsplit(row.url).path.rstrip('/')
            item_id = re.search(r'_(\d{6,})$', path)
            identity = item_id.group(1) if item_id else path
            previous = grouped[hardware_id].get(identity)
            if previous is None or (row.observed_at, row.id) > (previous.observed_at, previous.id):
                grouped[hardware_id][identity] = row
    for hardware_id, observations in grouped.items():
        rows = list(observations.values())
        # Exclude extreme outliers independently of the general ad safety rules.
        centre = median(row.price_rub for row in rows)
        clean = [row for row in rows if centre * .5 <= row.price_rub <= centre * 2]
        if not clean:
            continue
        typical = round(mean(row.price_rub for row in clean))
        representative = min(clean, key=lambda row: abs(row.price_rub - typical))
        quotes[hardware_id] = SimpleNamespace(
            price_rub=typical, source='avito', market='used_ru', source_url=representative.url,
            observed_at=min(row.observed_at for row in clean), sample_count=len(clean),
            origin='single_listing' if len(clean) == 1 else 'market_average' if len(clean) >= 3 else 'limited_sample',
            offer_id=representative.id if len(clean) == 1 else None,
            offer_name=representative.name if len(clean) == 1 else None, verified_at=None,
            average_method='one_offer' if len(clean) == 1 else 'mean' if len(clean) >= 3 else 'limited',
            observation_days=7,
        )
    return quotes


def upgrade_price_map(db, sources=None):
    quotes = price_map(db, sources)
    if sources is None or 'avito' in sources:
        quotes.update(avito_price_estimates(db))
    return quotes


def refresh_avito(db, hardware, cpu, gpu, deadline, search, game=None, mode=None, single_offer_fallback=False):
    """Bounded, targeted refresh; the catalog can be covered over many searches."""
    from app.schemas.offers import SearchOffers
    from app.core.config import settings
    import time
    from app.services.store_providers import source_blocked
    candidates = [cpu, gpu]
    from app.services.performance import cpu_capacity, cs2_cpu_basis
    from app.schemas.calculate import GameName
    candidates_cpu = [h for h in hardware if h.type == 'CPU' and h.socket == cpu.socket and h.id != cpu.id]
    if game and mode:
        current = cpu_capacity(cpu.raw_score, cpu.name, game, mode)
        candidates_cpu = [h for h in candidates_cpu if cpu_capacity(h.raw_score, h.name, game, mode) > current]
    cpu_choices = sorted(candidates_cpu, key=lambda h: (
        0 if game == GameName.CS2 and cs2_cpu_basis(h.name) else 1,
        abs(h.raw_score - cpu.raw_score * 1.25)))
    gpu_choices = sorted((h for h in hardware if h.type == 'GPU' and h.id != gpu.id
                          and h.raw_score > gpu.raw_score),
                         key=lambda h: abs(h.raw_score - gpu.raw_score * 1.25))
    candidates += cpu_choices[:2] + gpu_choices[:2]
    statuses = []
    for item in candidates:
        from app.services.offers import signature
        model_signature = signature(item.name, item.type)
        query = 'AMD FX-' + model_signature[2:] if item.type == 'CPU' and model_signature and model_signature.startswith('fx') else item.name
        discovery_query = model_signature if model_signature and model_signature.startswith('fx') else query
        fallback_method = 'discovery' if single_offer_fallback else 'browser'
        if source_blocked('avito'):
            if settings.offers_browser_enabled and time.monotonic() < deadline:
                request = SearchOffers(query=discovery_query if single_offer_fallback else query, category=item.type, sources=['avito'], hardware_id=item.id, method=fallback_method)
                request._deadline = deadline
                try:
                    statuses.extend(search(db, request).get('sources', []))
                except Exception:
                    statuses.append({'source': 'avito', 'status': 'unavailable', 'message': 'Avito временно ограничил доступ.'})
            else:
                statuses.append({'source': 'avito', 'status': 'unavailable', 'message': 'Avito временно ограничил доступ.'})
            break
        if time.monotonic() >= deadline:
            break
        request = SearchOffers(query=query, category=item.type, sources=['avito'], hardware_id=item.id)
        request._deadline = deadline
        try:
            result = search(db, request)
        except Exception:
            statuses.append({'source': 'avito', 'status': 'unavailable', 'message': 'Не удалось обновить предложения Avito.'})
            break
        current_status = result.get('sources', [])
        failed = any(row.get('status') in ('timeout', 'unavailable') for row in current_status)
        if (failed or single_offer_fallback and not result.get('offers')) and settings.offers_browser_enabled and time.monotonic() < deadline:
            request = SearchOffers(query=discovery_query if single_offer_fallback else query, category=item.type, sources=['avito'], hardware_id=item.id, method=fallback_method)
            request._deadline = deadline
            try:
                browser = search(db, request)
                current_status = browser.get('sources', []) or current_status
            except Exception:
                pass
        statuses.extend(current_status)
        if failed:
            # After a direct-access restriction do not repeatedly hit Avito.
            break
    return statuses

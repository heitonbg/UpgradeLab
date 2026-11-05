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
    # Upgrade estimates deliberately accept the documented seven-day observation window.
    # The generic offer list uses a stricter 24-hour window intended for a new PC purchase.
    for row in upgrade_market_rows(db, sources):
        if not row.hardware_id:
            continue
        previous = quotes.get(row.hardware_id)
        if previous is not None:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            previous_rank = (previous.observed_at < cutoff, previous.price_rub)
            row_rank = (row.observed_at < cutoff, row.price_rub)
            if previous_rank <= row_rank:
                continue
        verification = json.loads(row.attributes).get('price_verification', {})
        quotes[row.hardware_id] = SimpleNamespace(
            price_rub=row.price_rub, source=row.source,
            market='used_ru' if row.condition == 'used' else 'retail_ru',
            source_url=row.url, observed_at=row.observed_at, sample_count=1,
            origin=row.origin, offer_id=row.id, offer_name=row.name,
            verified_at=verification.get('checked_at') + 'Z'
            if verification.get('status') == 'verified' and verification.get('checked_at') else None,
        )
    if sources is None or 'avito' in sources:
        for hardware_id, quote in avito_price_estimates(db).items():
            previous = quotes.get(hardware_id)
            if (previous is None or previous.source in ('avito', 'avito_snapshot') or
                    quote.price_rub <= previous.price_rub):
                quotes[hardware_id] = quote
    return quotes


def upgrade_search_summary(statuses, prices, resale_quotes, sources, started, names):
    """Distinguish an actual refresh, a saved estimate, and an inaccessible source."""
    from app.schemas.offers import LABELS
    selected = list(dict.fromkeys(sources if sources is not None else LABELS))
    if any(row.get('source') == 'avito' for row in statuses) and 'avito' not in selected:
        selected.append('avito')
    searched_models = {row.get('model') for row in statuses}
    # Only report prices for models involved in this calculation, not the whole catalog.
    quotes = {(ident, quote.source, quote.observed_at, quote.price_rub): quote
              for pool in (prices, resale_quotes) for ident, quote in pool.items()
              if names.get(ident) in searched_models}
    result = []
    for source in selected:
        attempts = [row for row in statuses if row.get('source') == source and row.get('attempted', True)]
        used = [quote for quote in quotes.values() if quote.source == source or
                source == 'avito' and quote.source == 'avito_snapshot']
        fresh = sum(quote.observed_at >= started for quote in used)
        errors = [row for row in attempts if row.get('status') in ('unavailable', 'timeout')]
        state = ('refreshed' if fresh else 'cached' if used else 'unavailable' if errors else
                 'not_found' if attempts else 'not_attempted')
        result.append({'source': source, 'label': LABELS[source], 'status': state,
            'attempted': bool(attempts), 'models_searched': len({row.get('model') for row in attempts}),
            'fresh_quotes': fresh, 'cached_quotes': len(used)-fresh,
            'last_error': errors[-1]['message'] if errors else None,
            'checked_at': max((row.get('checked_at') or '' for row in attempts), default=None) or None})
    return result


def upgrade_search_candidates(hardware, cpu, gpu, game=None, mode=None, target_fps=60,
                              ram_type=None, ram_channels=None):
    """Choose replacements by their gaming outcome, not multi-core score proximity."""
    from app.services.performance import cpu_capacity, gpu_capacity, estimate_fps, ram_performance_factor, cs2_cpu_basis
    from app.services.calculator import meaningful_upgrade
    from app.services.builds import desktop_gpu
    from app.schemas.calculate import GameName

    if game is None or mode is None:
        return [cpu, gpu], cpu
    factor = ram_performance_factor(game, cpu.name, ram_type, ram_channels)
    cpu_cap = cpu_capacity(cpu.raw_score, cpu.name, game, mode, factor)
    gpu_cap = gpu_capacity(gpu.raw_score, gpu.name, game, mode)
    current = estimate_fps(cpu.raw_score, gpu.raw_score, gpu.name, game, mode, factor, cpu.name)
    limiting = cpu if cpu_cap < gpu_cap else gpu
    def after(item):
        return (estimate_fps(item.raw_score, gpu.raw_score, gpu.name, game, mode, factor, item.name)
                if item.type == 'CPU' else
                estimate_fps(cpu.raw_score, item.raw_score, item.name, game, mode, factor, cpu.name))
    choices = [item for item in hardware if item.id != limiting.id and item.type == limiting.type and (
        bool(cpu.socket) and 'BGA' not in cpu.socket.upper() and item.socket == cpu.socket
        if item.type == 'CPU' else desktop_gpu(item.name)) and meaningful_upgrade(current, after(item))]
    if limiting.type == 'CPU' and game == GameName.CS2 and cs2_cpu_basis(cpu.name):
        based = [item for item in choices if cs2_cpu_basis(item.name)]
        choices = based or choices
    # Strongest first keeps X3D in the search even if a 5700X is already priced.
    def capacity(item):
        return (cpu_capacity(item.raw_score, item.name, game, mode, factor) if item.type == 'CPU'
                else gpu_capacity(item.raw_score, item.name, game, mode))
    fastest = sorted(choices, key=lambda item: (-after(item), -capacity(item), item.raw_score, item.id))
    target = sorted(choices, key=lambda item: (after(item) < target_fps,
        abs(after(item)-target_fps), item.raw_score, item.id))
    modest = sorted(choices, key=lambda item: (after(item), item.raw_score, item.id))
    selected, seen = [], {cpu.id, gpu.id}
    for item in [*fastest[:2], *target[:1], *modest, *fastest]:
        if item.id not in seen:
            selected.append(item)
            seen.add(item.id)
        if len(selected) == 4:
            break
    other = gpu if limiting.type == 'CPU' else cpu
    return [limiting, *selected, other], limiting


def refresh_upgrade_prices(db, hardware, cpu, gpu, deadline, search, sources=None, game=None, mode=None,
                           resale_fallback=False, target_fps=60, ram_type=None, ram_channels=None, focus_id=None):
    """Bounded search of every selected source, including Avito alongside retailers."""
    import time
    from app.core.config import settings
    from app.core.stores import STORES
    from app.schemas.offers import SearchOffers, LABELS
    from app.services.offers import search_offers as default_search, batch_search_offers, signature, available_offers
    from app.services.search_jobs import report_progress

    selected = list(dict.fromkeys(sources if sources is not None else STORES.keys()))
    if resale_fallback and 'avito' not in selected:
        selected.insert(0, 'avito')
    priority = ['avito', 'regard', 'kns', 'oldi', *selected]
    request_sources = list(dict.fromkeys(source for source in priority if source in selected))
    candidates, limiting = upgrade_search_candidates(hardware, cpu, gpu, game, mode, target_fps,
                                                     ram_type, ram_channels)
    if focus_id:
        focus = next((item for item in hardware if item.id == focus_id), None)
        if not focus or focus.type != limiting.type or focus.type == 'CPU' and focus.socket != cpu.socket:
            from fastapi import HTTPException
            raise HTTPException(422, 'Модель для уточнения цены не соответствует текущему апгрейду')
        candidates = [focus, *[item for item in candidates if item.id != focus_id]]
    report_progress('Ищем цены текущих деталей и подходящих замен на выбранных площадках')
    statuses, pending, direct = [], [], {}
    started = time.monotonic()
    http_deadline = started + max(0, deadline-started) * (.5 if settings.offers_browser_enabled else .7)
    def request_for(item, method='http', stores=None):
        model = signature(item.name, item.type)
        query = 'AMD FX-' + model[2:] if item.type == 'CPU' and model and model.startswith('fx') else item.name
        request = SearchOffers(query=query, category=item.type, sources=stores or request_sources,
                               hardware_id=item.id, method=method)
        request._deadline = http_deadline if method == 'http' else deadline
        request._source_timeout = 4
        return request
    if search is default_search:
        # Batch results already contain status information. Do not re-run six
        # complete SQL/filter passes merely to read the searches just saved.
        primary = next((item for item in candidates if item.id == focus_id), None) or next(
            (item for item in candidates if item.id not in (cpu.id, gpu.id)), limiting)
        results = batch_search_offers(db, [request_for(item) for item in candidates], source_first=True,
                                      priority_queries=[request_for(primary).query])
        by_query = {result['query']: result for result in results}
        for item in candidates:
            result = by_query[request_for(item).query]
            statuses.extend({**row, 'model': item.name} for row in result['sources'])
        successful = {(row['model'], row['source']) for row in statuses
                      if row['status'] in ('public_page', 'feed', 'browser_page')}
        names = {item.id: item.name for item in candidates}
        for row in available_offers(db, selected):
            if (names.get(row.hardware_id), row.source) in successful:
                direct.setdefault(row.hardware_id, set()).add(row.source)
    else:
        for index, item in enumerate(candidates):
            if time.monotonic() >= http_deadline:
                break
            request = request_for(item)
            request._deadline = min(http_deadline, time.monotonic() +
                                   (http_deadline-time.monotonic())/(len(candidates)-index))
            try:
                result = search(db, request)
                statuses.extend({**row, 'model': item.name} for row in result.get('sources', []))
                direct[item.id] = {row.get('source') for row in result.get('offers', [])}
            except Exception:
                statuses.append({'source': 'search', 'status': 'unavailable', 'model': item.name,
                                 'message': 'Не удалось выполнить поиск цен по выбранным площадкам.'})

    # A retailer price never suppresses Avito. Resale must follow the actual
    # limiting component, including GPU-limited games. Every job gets its own
    # slice, leaving later replacements a chance to run.
    replacements = [item for item in candidates if item.id not in (cpu.id, gpu.id)]
    need_resale = resale_fallback and limiting.id not in avito_price_estimates(db)
    avito_order = [limiting, *replacements] if need_resale and not focus_id else [*replacements, limiting]
    for item in avito_order:
        found = direct.get(item.id, set())
        if 'avito' in selected and 'avito' not in found:
            pending.append((item, ['avito']))
    for item in candidates:
        if not direct.get(item.id):
            stores = [source for source in request_sources if source != 'avito'][:2]
            if stores:
                pending.append((item, stores))
    if search is default_search and pending:
        item = pending[0][0]
        web_sources = [source for source in request_sources if source not in direct.get(item.id, set())][:3]
        web_deadline = min(deadline-(8 if settings.offers_browser_enabled else 0), time.monotonic()+12)
        if web_sources and time.monotonic() < web_deadline-3:
            report_progress(f'Ищем страницы {item.name} через бесплатную HTTP-выдачу поисковиков')
            request = request_for(item, 'web', web_sources)
            request._deadline = web_deadline
            result = search(db, request)
            statuses.extend({**row, 'model': item.name} for row in result.get('sources', []))
            found = {row.get('source') for row in result.get('offers', [])}
            pending = [(model, [source for source in stores if model.id != item.id or source not in found])
                       for model, stores in pending]
    blocked, browser_attempts = set(), defaultdict(int)
    for index, (item, stores) in enumerate(pending):
        if not settings.offers_browser_enabled or time.monotonic() >= deadline:
            break
        stores = [source for source in stores if source not in blocked and browser_attempts[source] < 2]
        if not stores:
            continue
        denied_http = any(row.get('source') == 'avito' and row.get('method', 'http') == 'http'
                          and row.get('status') == 'unavailable' and any(marker in row.get('message', '').lower()
                          for marker in ('http 403', 'http 429', 'http 439', 'captcha', 'ограничила доступ', 'приостановлены'))
                          for row in statuses)
        method = 'discovery' if stores == ['avito'] and denied_http else 'browser'
        request = request_for(item, method, stores)
        report_progress(f'Проверяем {item.name}: ' + ', '.join(LABELS[source] for source in stores))
        for source in stores:
            browser_attempts[source] += 1
        # At most two Avito browser starts in a request; one can otherwise spend
        # the entire window trying to launch a browser absent from the image.
        remaining_jobs = min(2, sum(any(source not in blocked for source in batch)
                                   for _, batch in pending[index:]))
        request._deadline = min(deadline, time.monotonic() +
                                (deadline-time.monotonic())/max(1, remaining_jobs))
        try:
            result = search(db, request)
            statuses.extend({**row, 'model': item.name} for row in result.get('sources', []))
            for row in result.get('sources', []):
                message = row.get('message', '').lower()
                if row.get('status') in ('unavailable', 'timeout') and any(marker in message for marker in (
                    'captcha', 'http 401', 'http 403', 'http 429', 'http 439',
                    'запрет доступа', 'запустить', 'не установлен', 'браузер занят')):
                    blocked.add(row['source'])
                    if any(marker in message for marker in ('запустить', 'не установлен', 'браузер занят')):
                        blocked.update(selected)
        except Exception:
            statuses.extend({'source': source, 'label': LABELS[source], 'status': 'unavailable',
                             'method': 'browser', 'model': item.name,
                             'message': 'Браузерный поиск не завершился; сохранённые цены показаны отдельно.'}
                            for source in stores)
    return statuses


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

"""Continue a PC search across stores; retain usable results when a store fails."""
import json
import time
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import settings
from app.db.models import Hardware
from app.schemas.offers import LABELS, SearchOffers
from app.services.assembly_policy import search_queries, part_limit
from app.services.automatic_builds import board_matches, memory_matches, part
from app.services.adaptive_builds import platform_candidates, solve_profiles
from app.services.component_quality import quality_check
from app.services.gaming_selection import gaming_cases
from app.services.offers import available_offers
from app.services.price_verification import pending_build_prices, recent_check, verify_build_prices
from app.services.store_providers import search_url, source_blocked
from app.services.assembly_draft import draft_build, observed_rows, quote_evidence

SEARCH_SECONDS = 45
CATEGORIES = ('CPU', 'GPU', 'motherboard', 'memory', 'storage', 'psu', 'case', 'cooler')
PART_LABELS = dict(zip(CATEGORIES, ('Процессор', 'Видеокарта', 'Материнская плата',
                                  'Память', 'SSD', 'Блок питания', 'Корпус', 'Кулер')))
# Readable retail pages first; each failure moves the request to another shop.
STORE_ORDER = ('regard', 'oldi', 'kns', 'xcom', 'citilink', 'onlinetrade', 'nix',
               'dns', 'yandex', 'ozon', 'wb', 'avito')


def confirmed(row):
    check = json.loads(row.attributes).get('price_verification', {})
    return row.origin == 'feed' or check.get('status') == 'verified' and recent_check(check)


def queries_for(payload):
    profiles = platform_candidates(payload)
    queries = search_queries(payload.budget, payload.socket)
    boards = {
        'AM4': ['MSI B450M-A PRO MAX', 'ASRock B450M-HDV R4.0', 'MSI B550M PRO-VDH'],
        'AM5': ['MSI PRO B650M-B', 'ASRock A620M'],
        'LGA1700': [f'Gigabyte H610M K {payload.ram_type}', f'MSI PRO H610M-E {payload.ram_type}'],
    }
    queries['CPU'] = list(dict.fromkeys([query for index in range(8) for profile in profiles
        for query in search_queries(payload.budget,profile.socket)['CPU'][index:index+1]]))
    queries['motherboard'] = list(dict.fromkeys([query for index in range(4) for profile in profiles
        for query in (boards.get(profile.socket,[]) + [f'материнская плата {profile.socket} {profile.ram_type}'])[index:index+1]]))
    queries['memory'] = list(dict.fromkeys([query for ram in dict.fromkeys(profile.ram_type for profile in profiles)
        for query in [f'{ram} {payload.ram_capacity_gb} ГБ',f'{ram} 2x{payload.ram_capacity_gb//2}GB',
                      f'{ram} {payload.ram_capacity_gb}GB KIT']]))
    queries['case'] = {'gaming': ['DeepCool CC560', 'Montech X3 Mesh'],
                       'minimal': ['DeepCool CH510', 'Montech AIR 100'],
                       'budget': ['корпус ATX', 'DeepCool CC560']}[payload.case_style]
    return {category: queries[category] for category in CATEGORIES}


def inventory(payload, db, excluded, observed=False):
    from app.services.builds import desktop_gpu
    hardware = {item.id: item for item in db.scalars(select(Hardware))}
    pool = {category: [] for category in CATEGORIES}
    profiles = platform_candidates(payload)
    for row in available_offers(db, payload.price_sources,include_unavailable=observed):
        if row.id in excluded or row.category not in pool:
            continue
        if row.category in ('CPU', 'GPU'):
            hw = hardware.get(row.hardware_id)
            if not hw or row.category == 'CPU' and hw.socket not in {profile.socket for profile in profiles}:
                continue
            if row.category == 'GPU' and not desktop_gpu(hw.name):
                continue
        else:
            if row.price_rub > part_limit(row.category, payload.budget, flexible=True):
                continue
            if row.category in ('storage', 'psu', 'cooler') and quality_check(row, payload.socket)[0] is None:
                continue
            if row.category == 'motherboard' and not any(board_matches(row, profile) for profile in profiles):
                continue
            if row.category == 'memory' and not any(memory_matches(row, profile) for profile in profiles):
                continue
            if row.category == 'case' and not gaming_cases([row], payload.budget, payload.case_style, flexible=True):
                continue
        pool[row.category].append(row)
    return pool


def assemble_resilient(payload, db, search):
    started=time.monotonic()
    deadline = started + SEARCH_SECONDS
    http_deadline = deadline - min(10, SEARCH_SECONDS / 4)
    phase_deadline=deadline
    selected = list(dict.fromkeys(payload.price_sources or LABELS))
    preferred = 'avito' if 'avito' in selected else None
    active = ['avito'] if preferred and payload.selected_cpu_id is None else list(selected)
    excluded, attempted, statuses = set(), set(), {}
    queries = queries_for(payload)
    last_reason = 'Пока не найден полный совместимый комплект в бюджете.'
    verification_batches = 0
    failed_http,failed_browser=set(),set()
    failure_counts={}

    def request_payload():
        return payload.model_copy(update={'price_sources': list(active)})

    def report():
        return {'selected_sources': selected, 'searched_sources': list(active),
                'additional_sources': [source for source in active if source not in selected],
                'rejected_offers': len(excluded), 'sources': list(statuses.values()),'preferred_source':preferred,
                'elapsed_seconds':round(time.monotonic()-started)}

    def finish(result,mode='complete'):
        data = {**report(),'selection_changes':result.get('selection_changes',[]),
                'preferred_parts_count':result.get('preferred_parts_count',0),
                'actual_config':result.get('actual_config'),'result_mode':mode,
                'price_note':result.get('price_note')}
        for variant in result.get('alternatives', []):
            variant['search_report'] = data
            variant['status'] = mode
        return {**result, 'status': mode, 'search_report': data,'purchase_ready':mode=='complete'}

    def settle(batches=1):
        nonlocal verification_batches, last_reason
        for attempt in range(batches + 1):
            rows = [row for row in available_offers(db, active) if row.id not in excluded]
            checked_ids = {row.id for row in rows if confirmed(row)}
            try:
                # A ready PC must survive an unavailable alternative or a cheaper
                # unverified ad. Rebuild alternatives from confirmed quotes only.
                return solve_profiles(request_payload(), db, allowed_offer_ids=checked_ids, preferred_source=preferred)
            except HTTPException as error:
                if error.status_code != 400:
                    raise
                last_reason = str(error.detail)
            if attempt == batches or time.monotonic() >= phase_deadline or verification_batches >= 8:
                return None
            try:
                candidate = solve_profiles(request_payload(), db, allowed_offer_ids={row.id for row in rows}, preferred_source=preferred)
            except HTTPException as error:
                if error.status_code != 400:
                    raise
                last_reason = str(error.detail)
                return None
            # Verify one complete option first. Extra cards cannot prevent a
            # working recommended build from being returned.
            primary = {'parts': candidate['parts']}
            pending = pending_build_prices(db, primary)
            if not pending:
                return candidate
            verify_build_prices(db, primary, browser_sources={'avito'} if preferred and settings.offers_browser_enabled
                                and 'avito' not in failed_browser else None,deadline=phase_deadline)
            verification_batches += 1
            excluded.update(row.id for row in pending if json.loads(row.attributes).get('price_verification',{}).get('status')=='unavailable')
        return None

    def lookup(category, query, sources, method='http'):
        feeds = json.loads(settings.offers_feed_urls)
        sources = [source for source in sources if (method!='http' or source not in failed_http and
                   (not source_blocked(source) or source in feeds)) and (method=='http' or source not in failed_browser)]
        limit=min(phase_deadline,http_deadline if method=='http' else deadline)
        if not sources or time.monotonic() >= limit:
            return False
        key = category, query, tuple(sources), method
        if key in attempted:
            return False
        attempted.add(key)
        try:
            request=SearchOffers(category=category, query=query[:160], sources=sources, method=method)
            request._deadline=limit
            response = search(db, request)
            for item in (response or {}).get('sources', []):
                statuses[(item['source'], method)] = item
                if item['status'] in ('unavailable','timeout'):
                    source=item['source'];failure_counts[source]=failure_counts.get(source,0)+1
                    message=item.get('message','').lower()
                    denied=any(word in message for word in ('403','429','439','captcha','запрет доступа','ограничила доступ','доступ ограничен'))
                    if method=='http' and (denied or failure_counts[source]>=2):failed_http.add(source)
                    if method!='http':failed_browser.add(source)
        except (HTTPException, RuntimeError) as error:
            for source in sources:
                statuses[(source, method)] = {'source': source, 'label': LABELS[source],
                    'status': 'unavailable', 'method': method, 'message': str(getattr(error, 'detail', error))[:250]}
        return True

    result = settle(batches=0)
    if result:
        return finish(result)

    # A usable observed PC must not wait through a long outage. Reserve a short
    # refresh window, then return a visibly preliminary configuration.
    preview_sources=list(dict.fromkeys([*selected,*STORE_ORDER])) if payload.allow_store_fallback else selected
    preview=draft_build(payload.model_copy(update={'price_sources':preview_sources}),db,preferred_source=preferred)
    if preview:
        deadline=min(deadline,time.monotonic()+15)
        http_deadline=min(http_deadline,deadline-3)
        phase_deadline=deadline

    # Avito has its own complete search phase before any ready retail PC can
    # short-circuit the request. Search other platforms and cheaper GPU/CPU
    # models here as well, not only replacements for a fixed shopping list.
    if preferred and payload.selected_cpu_id is None:
        preferred_deadline = min(deadline - 5, time.monotonic() + 8)
        phase_deadline=preferred_deadline
        for index in range(3):
            pool=inventory(request_payload(),db,excluded)
            for category in sorted(CATEGORIES,key=lambda category:bool(pool[category])):
                if index < len(queries[category]) and (index==0 or category in ('CPU','GPU','motherboard','memory','storage')):
                    lookup(category,queries[category][index],['avito'])
                    result=settle()
                    if result:return finish(result)
                if time.monotonic()>=preferred_deadline:break
            if time.monotonic()>=preferred_deadline:break
        if settings.offers_browser_enabled:
            failures=0
            pool=inventory(request_payload(),db,excluded)
            categories=sorted(CATEGORIES,key=lambda category:bool(pool[category]))
            for category in categories:
                if time.monotonic()>=preferred_deadline:break
                lookup(category,queries[category][0],['avito'],'browser')
                result=settle()
                if result:return finish(result)
                status=statuses.get(('avito','browser'),{})
                failures=failures+1 if status.get('status')=='unavailable' else 0
                if failures>=2:break

    phase_deadline=deadline
    active.extend(source for source in selected if source not in active)

    # Reuse a complete, freshly confirmed fallback before waiting on a blocked
    # preferred shop again. The user's fallback setting still controls expansion.
    all_sources = list(dict.fromkeys([*selected, *STORE_ORDER]))
    if payload.allow_store_fallback and len(all_sources) > len(selected):
        checked_ids = {row.id for row in available_offers(db, all_sources) if row.id not in excluded and confirmed(row)}
        try:
            ready = solve_profiles(payload.model_copy(update={'price_sources': all_sources}), db,
                                   allowed_offer_ids=checked_ids, preferred_source=preferred)
        except HTTPException as error:
            if error.status_code != 400:
                raise
        else:
            active[:] = all_sources
            return finish(ready)

    # Search selected stores first, then expand automatically instead of asking
    # the user to restart the same request with a different set of checkboxes.
    stages = [selected]
    other_stores = [source for source in STORE_ORDER if source not in selected]
    if payload.allow_store_fallback and other_stores:
        stages.append(other_stores)
    for sources in stages:
        active.extend(source for source in sources if source not in active)
        result = settle()
        if result:
            return finish(result)
        missing = inventory(request_payload(), db, excluded)
        ordered = sorted(CATEGORIES, key=lambda category: bool(missing[category]))
        for category in ordered:
            lookup(category, queries[category][0], sources)
            result = settle()
            if result:
                return finish(result)
            if time.monotonic() >= http_deadline:
                break
        if time.monotonic() >= http_deadline:
            break

    # Try other models too: switching only stores would keep looking for the
    # same unavailable SSD/cooler. Round-robin avoids spending the whole request
    # on one component or one brand.
    for index in range(1, max(map(len, queries.values()))):
        pool = inventory(request_payload(), db, excluded)
        for category in sorted(CATEGORIES, key=lambda category: bool(pool[category])):
            if index < len(queries[category]):
                lookup(category, queries[category][index], active)
                result = settle()
                if result:
                    return finish(result)
            if time.monotonic() >= http_deadline:
                break
        if time.monotonic() >= http_deadline:
            break

    if payload.allow_store_fallback:
        active.extend(source for source in other_stores if source not in active)
    if settings.offers_browser_enabled and time.monotonic() < deadline:
        pool = inventory(request_payload(), db, excluded)
        missing = [category for category in CATEGORIES if not any(confirmed(row) for row in pool[category])]
        # Browser discovery reads product pages; search snippets are only links.
        browser_order = (['avito'] if preferred else []) + list(STORE_ORDER)
        browser_sources = list(dict.fromkeys(source for source in browser_order if source in active))
        for index, source in enumerate(browser_sources[:6]):
            category = (missing or list(CATEGORIES))[index % len(missing or CATEGORIES)]
            lookup(category, queries[category][0], [source], 'discovery')
            result = settle()
            if result:
                return finish(result)
            if time.monotonic() >= deadline:
                break

    result = settle(batches=0)
    if result:
        return finish(result)

    draft=draft_build(request_payload(),db,preferred_source=preferred)
    if draft:
        return finish(draft,mode='draft')

    # An outage still has a useful response. These are individual offers, never
    # a claim that an incomplete or incompatible PC is ready to purchase.
    pool = inventory(request_payload(), db, set(), observed=True)
    observed_ids={row.id for row in observed_rows(db,active)}
    found = []
    for category in CATEGORIES:
        row = next((row for row in pool[category] if row.id in observed_ids), None)
        if row:
            quality = quality_check(row, payload.socket)[0] if category in ('storage', 'psu', 'cooler') else None
            found.append({**part(row, quality),**quote_evidence(row)})
    gaps = [category for category in CATEGORIES if not any(item['type'] == category for item in found)]
    missing = [{'type': category, 'label': PART_LABELS[category], 'query': queries[category][0],
                'links': [{'source': source, 'label': LABELS[source], 'url': search_url(source, queries[category][0])}
                          for source in active]} for category in gaps or CATEGORIES]
    partial_report={**report(),'preferred_parts_count':sum(item['price_source']==LABELS.get(preferred) for item in found)}
    return {'scenario': 'build', 'status': 'partial', 'alternatives': [], 'parts': found,
            'found_parts_count': len(found), 'missing_parts': missing, 'search_report': partial_report,
            'message': 'Площадки не дали завершить проверку цен. Ниже сохранены найденные предложения; их текущие цены и наличие требуют проверки.',
            'reason': last_reason,
            'note': 'Найденные предложения показаны отдельно. Их совместимость в составе полного ПК и итоговая стоимость ещё не подтверждены.'}

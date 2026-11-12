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
from app.services.offers import available_offers, fresh, search_offers as default_search, batch_search_offers
from app.services.price_verification import pending_build_prices, recent_check, verify_build_prices
from app.services.store_providers import search_url, source_blocked
from app.services.assembly_draft import draft_build, observed_rows, quote_evidence
from app.services.search_jobs import report_progress

SEARCH_SECONDS = 45
CATEGORIES = ('CPU', 'GPU', 'motherboard', 'memory', 'storage', 'psu', 'case', 'cooler')
PART_LABELS = dict(zip(CATEGORIES, ('Процессор', 'Видеокарта', 'Материнская плата',
                                  'Память', 'SSD', 'Блок питания', 'Корпус', 'Кулер')))
# Readable retail pages first; each failure moves the request to another shop.
STORE_ORDER = ('upgradelab', 'regard', 'kns', 'oldi', 'xcom', 'citilink', 'onlinetrade', 'nix',
               'dns', 'yandex', 'ozon', 'wb', 'avito')


def confirmed(row):
    check = json.loads(row.attributes).get('price_verification', {})
    return fresh(row) and (row.origin == 'feed' or check.get('status') == 'verified' and recent_check(check))


def queries_for(payload):
    profiles = platform_candidates(payload)
    queries = search_queries(payload.budget, payload.socket)
    boards = {
        'AM4': ['B450M', 'MSI B450M-A PRO MAX', 'ASRock B450M-HDV R4.0', 'MSI B550M PRO-VDH'],
        'AM5': ['MSI PRO B650M-B', 'ASRock A620M'],
        'LGA1700': [f'Gigabyte H610M K {payload.ram_type}', f'MSI PRO H610M-E {payload.ram_type}'],
    }
    queries['CPU'] = list(dict.fromkeys([query for index in range(8) for profile in profiles
        for query in search_queries(payload.budget,profile.socket)['CPU'][index:index+1]]))
    queries['motherboard'] = list(dict.fromkeys([query for index in range(4) for profile in profiles
        for query in (boards.get(profile.socket,[]) + [f'материнская плата {profile.socket} {profile.ram_type}'])[index:index+1]]))
    # Do not place every other platform before the second compatible board.
    queries['motherboard'] = list(dict.fromkeys([*boards.get(payload.socket, [])[:2], *queries['motherboard']]))
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
            if row.price_rub > payload.budget:
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
    from app.services.partial_budget import planning_reserves
    reserves = planning_reserves(pool, payload.budget)
    for category in ('CPU', 'GPU'):
        limit = payload.budget - sum(value for key, value in reserves.items() if key != category)
        pool[category] = [row for row in pool[category] if row.price_rub <= limit]
    return pool


def assemble_resilient(payload, db, search):
    browser_enabled = settings.offers_browser_enabled
    started=time.monotonic()
    deadline = started + SEARCH_SECONDS
    http_deadline = deadline - min(16, SEARCH_SECONDS / 3)
    phase_deadline=deadline
    selected = list(dict.fromkeys(payload.price_sources or LABELS))
    # The official Regard XLSX and UpgradeLab marketplace are local inventory
    # sources. When the user explicitly selects only these two, return the
    # honest preliminary draft directly instead of spending the live-search
    # deadline probing unrelated stores or rechecking the same unconfirmed data.
    if selected and set(selected).issubset({'regard', 'upgradelab'}) and not any(
            confirmed(row) for row in available_offers(db, selected)):
        local_draft = draft_build(payload, db)
        if local_draft:
            return {**local_draft, 'status': 'draft', 'purchase_ready': False,
                    'prices_confirmed': False,
                    'search_report': {'selected_sources': selected, 'searched_sources': selected,
                                      'additional_sources': [], 'rejected_offers': 0,
                                      'sources': [], 'preferred_source': None, 'elapsed_seconds': 0}}
        # With only local sources selected, missing categories are a useful
        # partial result; there is no external store search to wait for.
        deadline = started
        http_deadline = started
        phase_deadline = started
    preferred = 'avito' if 'avito' in selected else None
    # If Avito was selected, its outage must not prevent a complete search on
    # the other configured stores. The user's explicit request is to keep
    # trying alternatives when a marketplace cannot provide offers.
    allow_fallback = payload.allow_store_fallback or preferred == 'avito'
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

    def record_sources(items, method):
        for item in items:
            statuses[(item['source'], method)] = item
            if item['status'] in ('unavailable', 'timeout'):
                source = item['source']
                failure_counts[source] = failure_counts.get(source, 0) + 1
                message = item.get('message', '').lower()
                denied = any(word in message for word in ('401', '403', '429', '439', 'captcha',
                    'запрет доступа', 'ограничила доступ', 'доступ ограничен'))
                # A query with no matching products says nothing about whether
                # a different category can be read from the same store.
                if method == 'http' and (denied or item['status'] == 'timeout' and failure_counts[source] >= 2):
                    failed_http.add(source)
                if method != 'http' and denied:
                    failed_browser.add(source)

    def lookup(category, query, sources, method='http'):
        feeds = json.loads(settings.offers_feed_urls)
        sources = [source for source in sources if (method!='http' or source not in failed_http and
                   (not source_blocked(source) or source in feeds)) and (method=='http' or source not in failed_browser)]
        sources.sort(key=lambda source: (source not in feeds, STORE_ORDER.index(source)))
        limit=min(phase_deadline,http_deadline if method=='http' else deadline)
        if not sources or time.monotonic() >= limit:
            return False
        report_progress(f'Ищем {PART_LABELS[category].lower()}: {query}')
        key = category, query, tuple(sources), method
        if key in attempted:
            return False
        attempted.add(key)
        try:
            request=SearchOffers(category=category, query=query[:160], sources=sources, method=method,city_id=payload.city_id,geo_mode=payload.geo_mode,max_price=payload.max_price,limit=payload.limit)
            request._deadline=limit
            response = search(db, request)
            record_sources((response or {}).get('sources', []), method)
        except (HTTPException, RuntimeError) as error:
            for source in sources:
                statuses[(source, method)] = {'source': source, 'label': LABELS[source],
                    'status': 'unavailable', 'method': method, 'message': str(getattr(error, 'detail', error))[:250]}
        return True

    result = settle(batches=0)
    if result:
        return finish(result)

    # Keep the full request window: browser startup and an Avito challenge can
    # take longer than a direct HTTP request. Preliminary offers remain clearly
    # marked while live sources get their allotted attempt.
    # Avito has its own complete search phase before any ready retail PC can
    # short-circuit the request. Search other platforms and cheaper GPU/CPU
    # models here as well, not only replacements for a fixed shopping list.
    if preferred and payload.selected_cpu_id is None:
        # Give Chromium time to start and render at least one Avito search page,
        # while reserving the end of the request for alternative stores.
        preferred_deadline = min(deadline - 20, time.monotonic() + 6)
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
        if browser_enabled:
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
    result = settle(batches=0)
    if result:
        return finish(result)

    # Obtain a first quote for every missing category before spending the whole
    # request on retries for one CPU/GPU. Network requests are concurrent, SQL
    # writes run on this request's thread. Explicit source restrictions apply.
    if search is default_search and time.monotonic() < http_deadline - 5:
        candidates = list(dict.fromkeys([*selected, *STORE_ORDER])) if allow_fallback else selected
        fast_sources = [source for source in STORE_ORDER if source in candidates and
                        source not in failed_http and not source_blocked(source)][:2]
        if fast_sources:
            active.extend(source for source in fast_sources if source not in active)
            result = settle(batches=0)
            if result:
                return finish(result)
            pool = inventory(request_payload(), db, excluded)
            ordered = [category for category in CATEGORIES if not pool[category]]
            if not ordered:
                ordered = ['CPU', 'GPU', 'motherboard', 'memory']
            batch_deadline = min(http_deadline - 5, time.monotonic() + 22)
            jobs = []
            for category, index in [(category, index) for index in range(2) for category in ordered]:
                if index >= len(queries[category]):
                    continue
                request = SearchOffers(category=category, query=queries[category][index][:160], sources=fast_sources,city_id=payload.city_id,geo_mode=payload.geo_mode,max_price=payload.max_price,limit=payload.limit)
                request._deadline = batch_deadline
                request._source_timeout = 4
                jobs.append(request)
                attempted.add((category, request.query, tuple(fast_sources), 'http'))
            for response in batch_search_offers(db, jobs):
                record_sources(response.get('sources', []), 'http')
            report_progress('Сопоставляем найденные детали, совместимость и общий бюджет')
            result = settle()
            if result:
                return finish(result)

    # Reuse a complete, freshly confirmed fallback before waiting on a blocked
    # preferred shop again. The user's fallback setting still controls expansion.
    all_sources = list(dict.fromkeys([*selected, *STORE_ORDER]))
    if allow_fallback and len(all_sources) > len(selected):
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
    if allow_fallback and other_stores:
        stages.append(other_stores)
    for sources in stages:
        if time.monotonic() >= http_deadline:
            break
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
        if time.monotonic() >= http_deadline:
            break
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

    if allow_fallback:
        active.extend(source for source in other_stores if source not in active)
    if search is default_search and time.monotonic() < deadline-5:
        pool = inventory(request_payload(), db, excluded)
        missing = [category for category in CATEGORIES if not pool[category]]
        if missing:
            web_sources = list(dict.fromkeys((['avito'] if preferred else [])+
                [source for source in STORE_ORDER if source in active]))[:3]
            phase_deadline = min(deadline-4, time.monotonic()+10)
            lookup(missing[0], queries[missing[0]][0], web_sources, 'web')
            result = settle()
            if result:
                return finish(result)
            phase_deadline = deadline
    if browser_enabled and time.monotonic() < deadline:
        pool = inventory(request_payload(), db, excluded)
        missing = [category for category in CATEGORIES if not any(confirmed(row) for row in pool[category])]
        # Browser discovery reads product pages; search snippets are only links.
        browser_order = (['avito'] if preferred else []) + list(STORE_ORDER)
        browser_sources = list(dict.fromkeys(source for source in browser_order if source in active and source not in failed_browser))
        for index, source in enumerate(browser_sources):
            category = (missing or list(CATEGORIES))[index % len(missing or CATEGORIES)]
            lookup(category, queries[category][0], [source], 'browser')
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
    from app.services.partial_budget import partial_budget_plan
    budget_pool = {category: [row for row in pool[category] if row.id in observed_ids] for category in CATEGORIES}
    profiles = platform_candidates(payload)
    hardware = {item.id: item for item in db.scalars(select(Hardware))}
    eligibility = {}
    for rows in budget_pool.values():
        for row in rows:
            eligibility[row.id] = {index for index, profile in enumerate(profiles) if (
                hardware.get(row.hardware_id) is not None and hardware[row.hardware_id].socket == profile.socket
                if row.category == 'CPU' else board_matches(row, profile)
                if row.category == 'motherboard' else memory_matches(row, profile)
                if row.category == 'memory' else True)}
    def partial_compatible(rows, candidate):
        common = set(range(len(profiles)))
        for row in [*rows, candidate]:
            common.intersection_update(eligibility[row.id])
        if not common:
            return False
        from app.services.automatic_builds import cpu_board_matches
        combined = {row.category: row for row in [*rows, candidate]}
        if 'CPU' in combined and 'motherboard' in combined:
            if not cpu_board_matches(hardware[combined['CPU'].hardware_id], combined['motherboard']):
                return False
        if 'motherboard' in combined and 'storage' in combined:
            from app.services.storage_compatibility import nvme_board_evidence
            quality = quality_check(combined['storage'])[0]
            if quality and quality.get('interface') == 'NVMe' and not nvme_board_evidence(combined['motherboard']):
                return False
        return True
    selected_rows, budget_plan = partial_budget_plan(budget_pool, payload.budget, preferred, partial_compatible)
    found = []
    for row in selected_rows:
        quality = quality_check(row, payload.socket)[0] if row.category in ('storage', 'psu', 'cooler') else None
        found.append({**part(row, quality),**quote_evidence(row)})
    gaps = [category for category in CATEGORIES if not any(item['type'] == category for item in found)]
    from app.services.partial_budget import planning_reserves
    from app.services.search_links import web_search_links
    reserves = planning_reserves(budget_pool, payload.budget)
    allocations = {category: reserves[category] for category in gaps}
    if allocations:
        total = sum(allocations.values())
        if total > budget_plan['budget_remaining']:
            allocations = {category: value * budget_plan['budget_remaining'] // total
                           for category, value in allocations.items()}
        extra = max(0, budget_plan['budget_remaining'] - sum(allocations.values()))
        allocations['GPU' if 'GPU' in allocations else next(iter(allocations))] += extra
    budget_plan['category_budgets'] = allocations
    web_source = preferred or next(iter(active), 'avito')
    from app.services.assembly_diagnostics import missing_diagnostic
    from app.services.offer_geography import offer_scope,filter_geography,geo_details
    raw_candidates={category:[] for category in CATEGORIES}
    with offer_scope(payload.model_copy(update={'geo_mode':'all','max_price':None})):
        raw_rows=observed_rows(db,active)
    for row in raw_rows:
        if row.category in raw_candidates:raw_candidates[row.category].append(row)
    missing = [{'type': category, 'label': PART_LABELS[category], 'query': queries[category][0],
                'budget_limit': allocations.get(category),
                **missing_diagnostic(category, raw_candidates[category], budget_pool[category],
                    allocations.get(category,0),lambda row:partial_compatible(selected_rows,row),
                    board=next((r for r in selected_rows if r.category=='motherboard'),None)),
                'web_links': web_search_links(web_source, queries[category][0]),
                'links': [{'source': source, 'label': LABELS[source], 'url': search_url(source, queries[category][0])}
                          for source in active]} for category in gaps or CATEGORIES]
    for gap in missing:
        raw=raw_candidates[gap['type']]
        if payload.geo_mode!='all' and raw and not filter_geography(raw,payload):
            gap['blocking_reason']='delivery_unknown' if payload.geo_mode=='delivery' else 'availability_unknown'
            gap['geography_filtered_count']=len(raw)
    partial_report={**report(),'preferred_parts_count':sum(item['price_source']==LABELS.get(preferred) for item in found)}
    return {'scenario': 'build', 'status': 'partial', 'alternatives': [], 'parts': found,
            'budget_plan': budget_plan,
            'found_parts_count': len(found), 'missing_parts': missing, 'search_report': partial_report,
            'message': 'Площадки не дали завершить проверку цен. Ниже сохранены найденные предложения; их текущие цены и наличие требуют проверки.',
            'reason': last_reason,
            'note': 'Найденные предложения показаны отдельно. Их совместимость в составе полного ПК и итоговая стоимость ещё не подтверждены.'}

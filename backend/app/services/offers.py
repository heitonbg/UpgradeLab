import hashlib
import json
import re
import time
import requests
from pydantic import ValidationError
from app.services.network_policy import NetworkPolicyError
from app.services.source_outcomes import SourceFailure, diagnose_source, http_outcome, outcome_code, public_outcome, public_runtime_message
from urllib.parse import unquote, urlsplit
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from app.core.price_time import as_utc, db_now, iso_utc, is_fresh, current_verification, OFFER_TTL, SEARCH_TTL, OBSERVATION_SKEW
from pathlib import Path
from functools import lru_cache
from sqlalchemy import select, or_, and_
from app.core.config import settings, BACKEND_DIR
from app.db.models import Hardware, StoreOffer, OfferSearch
from app.schemas.offers import OfferInput, LABELS
from app.services.hardware_matching import match_model
from app.services.store_providers import fetch, search_public, search_url


def fresh(offer):
    return is_fresh(offer.observed_at, OFFER_TTL, inclusive=True, future_tolerance=OBSERVATION_SKEW)


@lru_cache(maxsize=32768)
def model_signatures(name, kind):
    text = name.lower()
    if kind == "CPU":
        pattern = r"(ryzen\s*[3579]\s*\d{4,5}[a-z0-9]*|i[3579][-\s]*\d{4,5}[a-z0-9]*|fx[-\s]*\d{4}[a-z0-9]*)"
    else:
        pattern = r"((?:rtx|gtx|gts|gt|rx)\s*\d{3,4}\s*(?:ti\s*super|ti|super|xtx|xt)?|(?:rx\s*)?vega\s*(?:56|64)|arc\s*[ab]\d{3})"
    return frozenset(re.sub(r"[^a-z0-9]", "", match).replace('rxvega', 'vega') for match in re.findall(pattern, text))


def signature(name, kind):
    signatures = model_signatures(name, kind)
    return next(iter(signatures)) if len(signatures) == 1 else None


def consistent_hardware_title(title, model, kind):
    stated = model_signatures(title, kind)
    canonical = model_signatures(getattr(model, 'name', ''), kind)
    if len(stated) > 1 or stated and canonical and stated != canonical:
        return False
    if kind == 'GPU':
        capacities = {int(value) for value in re.findall(r'\b(\d+)\s*(?:GB|ГБ)\b', title, re.I)}
        vram = getattr(model, 'vram', None)
        if len(capacities) > 1 or capacities and vram and capacities != {vram}:
            return False
    return True


def offer_model_signatures(row):
    path = re.sub(r'[_-]', ' ', unquote(urlsplit(getattr(row, 'url', '')).path))
    return model_signatures(row.name, row.category) | model_signatures(path, row.category)


def component_listing(name):
    # Store search often returns entire PCs, notebooks and accessories alongside
    # a GPU. Those must not acquire the GPU's performance score or price.
    return not re.search(r"компьютер|системный блок|пэвм|ноутбук|моноблок|комплект|материнск|кулер|вентилятор|водоблок|радиатор|кабель|крепление|\bbundle\b|\bwaterblock\b|\blaptop\b|\bnotebook\b|\bssd\s*\d|\bwindows\b|\bfreedos\b|\bloq\b|\bkbd\b", name, re.I)


def match_offer(hardware, row):
    if not component_listing(row.name) or len(offer_model_signatures(row)) > 1:
        return None
    candidates = [h for h in hardware if h.type == row.category]
    if row.model_name:
        sig_title, sig_model = signature(row.name, row.category), signature(row.model_name, row.category)
        if sig_title and sig_model and sig_title != sig_model:
            return None
        match = match_model(candidates, row.model_name)
        memory = re.search(r"\b(\d+)\s*(?:gb|гб)\b", row.name, re.I)
        if match and row.category == "GPU" and memory and match.vram != int(memory.group(1)):
            return None
        return match if match and consistent_hardware_title(row.name, match, row.category) else None
    exact = match_model(candidates, row.name)
    if exact:
        return exact if consistent_hardware_title(row.name, exact, row.category) else None
    sig = signature(row.name, row.category)
    if not sig:
        return None
    if row.category == "GPU" and re.search(r"laptop|mobile|max-q|ноутбук", row.name, re.I):
        return None
    matches = [h for h in candidates if signature(h.name, row.category) == sig]
    memory = re.search(r"\b(\d+)\s*(?:gb|гб)\b", row.name, re.I)
    if memory and row.category == "GPU":
        matches = [h for h in matches if h.vram == int(memory.group(1))]
    return matches[0] if len(matches) == 1 else None


@lru_cache(maxsize=16384)
def title_category(name):
    """Explicit product titles keep related goods out of the requested category."""
    patterns = (
        ('motherboard', r'^\s*(?:материнская\s+плата|motherboard)\b'),
        ('memory', r'^\s*(?:оперативная\s+память|модуль\s+памяти|память\s+(?:DIMM|DDR))\b'),
        ('storage', r'^\s*(?:накопитель|SSD\b|твердотельный\s+накопитель)'),
        ('psu', r'^\s*блок\s+питания\b'), ('case', r'^\s*(?:игровой\s+)?корпус\b'),
        ('cooler', r'^\s*(?:кулер|охлаждение\s+процессора)\b'),
        ('CPU', r'^\s*процессор\b'), ('GPU', r'^\s*видеокарта\b'),
    )
    for category, pattern in patterns:
        if re.search(pattern, name, re.I):
            return category
    cpu, gpu = model_signatures(name, 'CPU'), model_signatures(name, 'GPU')
    return 'CPU' if cpu and not gpu else 'GPU' if gpu and not cpu else None


def upsert(db, rows, origin, commit=True):
    hardware = list(db.scalars(select(Hardware)))
    count = 0
    for row in rows:
        if not isinstance(row, OfferInput):
            row = OfferInput.model_validate(row)
        category = title_category(row.name)
        if category and category != row.category:
            continue
        existing = db.scalar(select(StoreOffer).where(StoreOffer.url == row.url))
        if (existing and is_fresh(existing.observed_at, timedelta.max, inclusive=True, future_tolerance=OBSERVATION_SKEW)
                and as_utc(existing.observed_at) > as_utc(row.observed_at)):
            continue
        repairing = bool(existing and existing.category != row.category and category == row.category
            and title_category(existing.name) == row.category and existing.origin in ('public_page', 'browser_page'))
        if existing and (existing.source != row.source or existing.category != row.category and not repairing):
            continue
        if not row.available:
            if existing:
                db.delete(existing)
            continue
        incoming_page_check = origin in ('product_page', 'browser_page') and current_verification(row.attributes.get('price_verification', {})) is not None
        if existing and origin != 'feed' and not incoming_page_check and not repairing:
            from app.services.price_verification import recent_check
            verification = json.loads(existing.attributes).get('price_verification', {})
            if recent_check(verification):
                continue  # A search snippet must not overwrite a recent page check.
        matched = match_offer(hardware, row) if row.category in ("CPU", "GPU") else None
        offer = existing or StoreOffer(url=row.url)
        for key in ("source", "name", "category", "price_rub", "condition", "observed_at"):
            setattr(offer, key, getattr(row, key))
        offer.hardware_id = matched.id if matched else None
        offer.origin = origin
        offer.attributes = json.dumps(row.attributes, ensure_ascii=False)
        db.add(offer)
        count += 1
    if commit:
        db.commit()
    else:
        db.flush()
    return count


def load_offer_file(db, filename=None):
    filename = filename or settings.offers_feed_file
    if not filename:
        return 0
    path = Path(filename)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [OfferInput.model_validate(row) for row in data["offers"]]
    return upsert(db, rows, "feed")


def offer_evidence(row):
    from app.services.offer_geography import geo_details
    from app.services.catalog_freshness import catalog_price_state
    catalog = catalog_price_state(row.observed_at) if row.origin == 'catalog_import' else {}
    return {**catalog, 'seller_type':'private' if row.source=='upgradelab' else 'store',
        'offer_type':'seller' if row.source=='upgradelab' else 'catalog' if row.origin=='catalog_import' else 'store',
        'price_trust':'seller_declared' if row.source=='upgradelab' else 'catalog_import' if row.origin=='catalog_import' else 'verified' if current_verification(json.loads(row.attributes).get('price_verification',{})) and fresh(row) else 'unconfirmed',
        'geography':geo_details(row),'technical_assessment':json.loads(row.attributes).get('technical_assessment'),
        'optimizer_eligible':json.loads(row.attributes).get('optimizer_eligible',True),'listing_fingerprint':json.loads(row.attributes).get('listing_fingerprint')}


def public_offer(row):
    verification = json.loads(row.attributes).get('price_verification', {})
    checked = current_verification(verification) if fresh(row) and row.source!='upgradelab' else None
    return {"id": row.id, "catalog_product_id": json.loads(row.attributes).get("catalog_import",{}).get("product_key"), "source": row.source, "source_label": "Справочная оценка" if row.source=="reference" else LABELS[row.source], "name": row.name,
            "category": row.category, "price_rub": json.loads(row.attributes).get("_costed_goods_price",row.price_rub),
            "total_known_cost_rub":row.price_rub, **offer_evidence(row), "url": row.url, "condition": row.condition,
            "observed_at": as_utc(row.observed_at), "origin": row.origin,
            "hardware_id": row.hardware_id, "attributes": json.loads(row.attributes),
            "availability": json.loads(row.attributes).get("catalog_import", {}).get("availability", "unknown") if row.origin == "catalog_import" else "unknown",
            "availability_warning": json.loads(row.attributes).get("catalog_import", {}).get("availability_warning") if row.origin == "catalog_import" else None,
            "price_verified_at": checked,
            "price_status": "seller_declared" if row.source=="upgradelab" else "catalog_import" if row.origin == "catalog_import" else None,
            "price_note": "Цена по прайс-листу; актуальность страницы не подтверждена" if row.origin == "catalog_import" else None}


def available_offers(db, sources=None, category=None, include_unavailable=False,include_ineligible=False):
    from app.services.planning_prices import scoped_inventory
    inventory=scoped_inventory()
    if inventory is not None:
        return [r for r in inventory if (category is None or r.category==category) and (r.source=='reference' or sources is None or r.source in sources)]
    from app.services.internal_offers import sync_internal
    sync_internal(db)
    now = db_now()
    query = select(StoreOffer).where(or_(StoreOffer.observed_at >= now - OFFER_TTL,
                                         and_(StoreOffer.origin == "catalog_import", StoreOffer.source == "regard",
                                              StoreOffer.observed_at >= now - timedelta(hours=settings.catalog_preliminary_hours))),
                                     StoreOffer.observed_at <= now + OBSERVATION_SKEW)
    if category:
        query = query.where(StoreOffer.category == category)
    from app.services.offer_safety import safe_offers
    hardware = {h.id: h for h in db.scalars(select(Hardware))}
    rows = safe_offers(list(db.scalars(query.order_by(StoreOffer.price_rub, StoreOffer.id))), hardware)
    from app.services.price_verification import recent_check
    if not include_unavailable:
        rows = [row for row in rows if not (json.loads(row.attributes).get('price_verification', {}).get('status') == 'unavailable'
                and recent_check(json.loads(row.attributes).get('price_verification', {}), 10))]
    else:
        rows = [row for row in rows if not re.search(r'не соответствует выбранной|модель.*не соответствует|outofstock|soldout|нет в наличии',
                str(json.loads(row.attributes).get('price_verification', {}).get('message','')),re.I)]
    from app.services.catalog_access import filter_catalog
    from app.services.offer_geography import filter_geography,costed
    from app.services.internal_offers import live_internal
    selected=filter_catalog(db,[row for row in rows if (sources is None or row.source in sources) and live_internal(db,row)])
    if not include_ineligible:selected=[row for row in selected if json.loads(row.attributes).get('optimizer_eligible',True)]
    return sorted((costed(row) for row in filter_geography(selected)),key=lambda row:(row.price_rub,row.id))


def search_key(payload):
    return hashlib.sha256(json.dumps(['public-v3', payload.query.lower(), payload.category,
        sorted(payload.sources), payload.method, settings.offers_browser_search_engine,payload.city_id,payload.geo_mode,payload.max_price,payload.limit]).encode()).hexdigest()


@diagnose_source
def collect_source(source, payload, deadline, feeds, tokens):
    """Network work only; worker threads must never share a database session."""
    if source=='upgradelab':
        return source, [], 'internal', 'Объявления биржи получены из локальной базы', {'attempted':False,'outcome':'not_tested'}
    if source=='avito':
        return source, [], 'disabled', 'Автоматический сбор Avito отключён после отказа в доступе', {
            'attempted':False,'outcome':'access_not_permitted'}
    from app.services.source_permissions import network_allowed
    if not network_allowed(source):
        return source, [], 'disabled', 'Сетевой доступ к источнику не разрешён владельцем проекта', {'attempted':False,'outcome':'access_not_permitted'}
    if payload._catalog_only or source in payload._catalog_sources:
        return source, [], 'catalog_import', 'Используются цены по импортированному прайс-листу; онлайн-сверка не выполнялась', {
            'attempted':False,'outcome':'not_tested'}
    if time.monotonic() >= deadline:
        return source, [], 'timeout', 'Источник не проверен: общий лимит времени поиска исчерпан', {'attempted': False}
    try:
        from app.services.search_time import remaining
        remaining(deadline, 5)
        if payload.method == 'web':
            from app.services.public_discovery import discover_public_offers
            rows, details = discover_public_offers(source, payload.query, payload.category, deadline)
            return source, rows, 'product_page' if rows else 'unavailable', (
                f"HTTP-поиск: подтверждено цен {len(rows)}" if rows else details['error']), details
        if payload.method != 'http':
            from app.services.browser_offers import search_browser
            rows, details = search_browser(source, payload.query, payload.category,
                payload.method == 'discovery', deadline=deadline)
            message = details.get('error') or (f"Браузер: найдено предложений {details.get('found', len(rows))}; "
                f"подтверждено {details['verified']}; найдено ссылок {details['discovered']}")
            return source, rows, 'browser_page' if rows else 'unavailable', message, details
        if source in feeds:
            body = json.loads(fetch(feeds[source], {'query': payload.query, 'category': payload.category},
                                    tokens.get(source), deadline=deadline))
            rows = [OfferInput.model_validate(row) for row in body['offers']]
            rows = [row for row in rows if row.source == source and row.category == payload.category]
            return source, rows, 'feed', 'Выгрузка источника получена', {}
        if settings.offers_live_search:
            return source, search_public(source, payload.query, payload.category, deadline=deadline), 'public_page', 'Публичная страница получена', {}
        return source, [], 'disabled', 'Прямой поиск отключён; используются сохранённые предложения', {'attempted':False}
    except SourceFailure as error:
        return source, [], 'unavailable', str(error), {'outcome':error.outcome,
            'http_status':error.http_status,'attempted':error.attempted}
    except (json.JSONDecodeError, ValidationError, KeyError, TypeError):
        return source, [], 'unavailable', 'Источник отдал данные неверного формата; предложения не добавлены', {'outcome':'parse_error'}
    except (TimeoutError, requests.Timeout):
        return source, [], 'timeout', 'Площадка не ответила за отведённое время', {'outcome':'timeout'}
    except requests.HTTPError as error:
        code = error.response.status_code if error.response is not None else 'unknown'
        return source, [], 'unavailable', f'Площадка вернула HTTP {code}', {'outcome':http_outcome(code),'http_status':code if isinstance(code,int) else None}
    except (requests.ConnectionError, OSError):
        return source, [], 'unavailable', 'Не удалось установить соединение с источником', {'outcome':'network_error'}
    except NetworkPolicyError as error:
        return source, [], 'unavailable', str(error)[:300], {'outcome':getattr(error,'outcome','network_error')}
    except RuntimeError as error:
        return source, [], 'unavailable', public_runtime_message(error), {}
    except Exception:
        return source, [], 'unavailable', 'Источник не отдал читаемые предложения: ограничение доступа, ошибка или изменившаяся разметка', {}


def persist_search(db, payload, responses, commit=True):
    statuses = []
    checked = db_now()
    for source, rows, origin, message, details in responses:
        if rows:
            upsert(db, rows, origin, commit=False)
        statuses.append({'source': source, 'label': LABELS[source], 'status': origin,
            'attempted': details.get('attempted', True),
            'method': payload.method, 'message': message, 'checked_at': iso_utc(checked),
            'outcome': details.get('outcome') or outcome_code(origin,result_count=len(rows)),
            'elapsed_ms': details.get('elapsed_ms'), 'result_count':len(rows),
            'http_status': details.get('http_status'),
            'search_url': search_url(source, payload.query), 'discovered_urls': details.get('links', []),
            'search_engines': details.get('search_engines', [])})
    previous = db.get(OfferSearch, search_key(payload)) or OfferSearch(key=search_key(payload))
    previous.checked_at = checked
    if any(item['status'] == 'timeout' for item in statuses):
        previous.checked_at -= timedelta(minutes=9, seconds=30)
    previous.statuses = json.dumps(statuses, ensure_ascii=False)
    db.add(previous)
    if commit:
        db.commit()
    else:
        db.flush()
    return previous, statuses


def internal_outcomes(db,payload,statuses):
    if not any(item['source']=='upgradelab' for item in statuses):return statuses
    from app.services.offer_geography import offer_scope
    with offer_scope(payload):rows=available_offers(db,['upgradelab'],payload.category)
    if payload.hardware_id:rows=[r for r in rows if r.hardware_id==payload.hardware_id]
    else:
        sig=signature(payload.query,payload.category) if payload.category in ('CPU','GPU') else None
        if sig:rows=[r for r in rows if signature(r.name,payload.category)==sig]
        else:rows=[r for r in rows if all(w in r.name.casefold() for w in re.findall(r'[a-zа-я0-9]+',payload.query.casefold()))]
    for item in statuses:
        if item['source']=='upgradelab':item.update(result_count=len(rows),attempted=False,outcome='success' if rows else 'no_results')
    return statuses


def batch_search_offers(db, payloads, source_first=False, priority_queries=()):
    """Cover missing PC categories concurrently; persist all results serially."""
    feeds, tokens = json.loads(settings.offers_feed_urls), json.loads(settings.offers_feed_tokens)
    from app.services.catalog_access import restricted_catalog_sources
    restricted = restricted_catalog_sources(db)
    pending, results, jobs = {}, [], []
    for payload in payloads:
        payload._catalog_sources = restricted
        if payload.method != 'http':
            raise ValueError('Пакетный поиск поддерживает только публичные HTTP-страницы')
        key = search_key(payload)
        if key in pending:
            continue
        previous = db.get(OfferSearch, key)
        if previous and is_fresh(previous.checked_at, SEARCH_TTL, inclusive=True):
            cached_statuses=internal_outcomes(db,payload,json.loads(previous.statuses))
            results.append({'category': payload.category, 'query': payload.query, 'sources': cached_statuses,
                            'source_outcomes':[public_outcome(item,cached=True) for item in cached_statuses]})
            continue
        pending[key] = (payload, [])
        jobs.extend((key, source, payload) for source in dict.fromkeys(payload.sources))
    if source_first:
        # Cover every model on the priority stores before slower fallback stores.
        jobs.sort(key=lambda job: (job[2].query not in priority_queries, job[2].sources.index(job[1])))
    def collect(job):
        key, source, payload = job
        deadline = payload._deadline or time.monotonic()+30
        if payload._source_timeout:
            deadline = min(deadline, time.monotonic()+payload._source_timeout)
        return key, collect_source(source, payload, deadline, feeds, tokens)
    with ThreadPoolExecutor(max_workers=settings.offers_http_workers) as pool:
        for key, response in pool.map(collect, jobs):
            pending[key][1].append(response)
    for payload, responses in pending.values():
        _, statuses = persist_search(db, payload, responses, commit=False)
        statuses=internal_outcomes(db,payload,statuses)
        results.append({'category': payload.category, 'query': payload.query, 'sources': statuses,
                        'source_outcomes':[public_outcome(item) for item in statuses]})
    if pending:
        db.commit()
    return results


def search_offers(db, payload):
    from app.services.offer_geography import offer_scope
    from app.services.internal_offers import sync_internal
    if sync_internal(db):db.commit()
    with offer_scope(payload):return _search_offers(db,payload)


def _search_offers(db, payload):
    from app.services.catalog_access import restricted_catalog_sources
    payload._catalog_sources = restricted_catalog_sources(db)
    deadline = payload._deadline or time.monotonic() + 45
    feeds, tokens = json.loads(settings.offers_feed_urls), json.loads(settings.offers_feed_tokens)
    previous = db.get(OfferSearch, search_key(payload))
    statuses = json.loads(previous.statuses) if previous else []
    search_cached = previous is not None and is_fresh(previous.checked_at, SEARCH_TTL, inclusive=True)
    if not search_cached:
        with ThreadPoolExecutor(max_workers=settings.offers_http_workers) as pool:
            responses = list(pool.map(lambda source: collect_source(source, payload, deadline, feeds, tokens),
                                      dict.fromkeys(payload.sources)))
        previous, statuses = persist_search(db, payload, responses)
    rows = available_offers(db, payload.sources, payload.category,include_ineligible=True)
    if payload.category in ("CPU", "GPU"):
        rows = [row for row in rows if component_listing(row.name)]
    if payload.hardware_id:
        rows = [r for r in rows if r.hardware_id == payload.hardware_id]
    else:
        query_signature = signature(payload.query, payload.category) if payload.category in ("CPU", "GPU") else None
        if query_signature:
            rows = [row for row in rows if signature(row.name, payload.category) == query_signature]
            memory=re.search(r'\b(\d+)\s*(?:gb|гб)\b',payload.query,re.I)
            if memory and payload.category=='GPU':
                rows=[row for row in rows if re.search(r'\b'+memory[1]+r'\s*(?:gb|гб)\b',row.name,re.I)]
        else:
            words = re.findall(r"[a-zа-я0-9]+", payload.query.lower())
            rows = [r for r in rows if all(word in r.name.lower() for word in words)]
    for status in statuses:
        if status['source']=='upgradelab':
            count=sum(r.source=='upgradelab' for r in rows)
            status.update(result_count=count,outcome='success' if count else 'no_results',attempted=False)
    candidates = [{"source": status["source"], "source_label": status["label"], "name": payload.query, "url": url}
                  for status in statuses for url in status.get("discovered_urls", [])]
    unavailable = [item['source'] for item in statuses if item['status'] in ('unavailable', 'timeout', 'disabled')]
    return {"offers": [public_offer(r) for r in rows[:payload.limit]], "sources": statuses, "candidates": candidates,
            "source_outcomes": [public_outcome(item,cached=search_cached) for item in statuses],
            "search_cached": search_cached, "unavailable_sources": unavailable,
            "partial_result": bool(rows and unavailable),
            "checked_at": as_utc(previous.checked_at),
            "note": "Предложения для подбора хранятся до 24 часов с даты наблюдения; это не гарантия актуальности цены. Подтверждение страницы действительно менее 15 минут. Обмен, выкуп, неисправные товары и подозрительно низкие цены исключаются эвристическим фильтром; он не гарантирует добросовестность продавца. Условия доставки, регион и скидки проверьте на площадке."}

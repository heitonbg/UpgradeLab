"""Select the complete PC with its CPU/GPU, supply and cooler in one budget."""
import json
import re
import time
from bisect import bisect_right
from itertools import product
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models import Hardware
from app.schemas.offers import LABELS
from app.services.offers import available_offers, public_offer
from app.services.prices import price_map, public_price
from app.services.component_quality import quality_check
from app.services.storage_compatibility import nvme_board_evidence
from app.services.gaming_selection import gaming_cases, distinct_cases
from app.services.performance import estimate_fps, fps_outlook
from app.services.assembly_policy import part_limit, psu_requirement, cooling_requirement


def attrs(offer):
    return json.loads(offer.attributes)


def board_matches(board, payload):
    from app.services.builds import board_socket
    title, data = board.name.upper(), attrs(board)
    sockets = {re.sub(r'LGA|\s', '', value) for value in re.findall(
        r'\b(?:AM[45]|(?:LGA\s*)?(?:1150|1151|1155|1200|1700))\b', title)}
    socket = data.get('socket') or board_socket(title)
    ram = data.get('ram_type') or next((value for value in ('DDR4', 'DDR5') if value in title), None)
    if ram is None:
        ram = 'DDR4' if re.search(r'\bD4\b',title) else 'DDR5' if re.search(r'\bD5\b',title) else None
    if ram is None and socket in ('AM4', 'AM5', 'LGA1151', 'LGA1200'):
        ram = 'DDR5' if socket == 'AM5' else 'DDR4'
    return (len(sockets) <= 1 and socket == payload.socket and ram == payload.ram_type
            and data.get('form_factor') in (None, 'ATX', 'mATX', 'Mini-ITX'))


def memory_configuration(memory):
    title, data = memory.name.upper(), attrs(memory)
    ram = data.get('ram_type') or next((r for r in ('DDR4', 'DDR5') if r in title), None)
    if re.search(r'SO[ -]?DIMM|RDIMM|REGISTERED|ECC', title):
        return None
    kit = re.search(r'\b([12])\s*[XХ×]\s*(\d{1,2})(?:\s*(?:GB|ГБ))?\b|\b(2)\s+ПО\s+(\d{1,2})\s*(?:GB|ГБ)', title)
    if kit:
        values = [int(value) for value in kit.groups() if value]
        modules, size = values
        capacity = modules * size
        if data.get('capacity_gb') and data['capacity_gb'] != capacity or data.get('modules') and data['modules'] != modules:
            return None
    else:
        capacity = data.get('capacity_gb') or next((int(n) for n in re.findall(r'\b(\d{1,3})\s*(?:GB|ГБ)', title)), 0)
        modules = data.get('modules') or (2 if re.search(r'KIT|КОМПЛЕКТ|ДВЕ ПЛАНКИ|2\s*ШТ', title) else 1)
    speed = data.get('speed_mhz') or data.get('frequency_mhz')
    try:
        speed = int(speed) if speed else None
    except (TypeError, ValueError):
        match = re.search(r'\b(\d{4,5})\b', str(speed))
        speed = int(match.group(1)) if match else None
    if not speed:
        match = re.search(r'(?:DDR[45][ -]?)?(\d{4,5})\s*(?:MHZ|MT/S)?', title)
        speed = int(match.group(1)) if match and int(match.group(1)) >= 1600 else None
    return {'ram_type': ram, 'capacity_gb': capacity, 'modules': modules,
            'speed_mt_s': int(speed) if speed else None,
            'dual_channel_potential': bool(modules >= 2),
            'factory_kit': bool(modules >= 2 and re.search(r'\bKIT\b|КОМПЛЕКТ|\b2\s*[XХ×]\s*\d+', title)
                                and 'ДВА ОТДЕЛЬНЫХ МОДУЛЯ' not in title),
            'specification_confidence': 'declared' if data.get('capacity_gb') or data.get('modules') else 'parsed_from_title'}


def memory_shortlist(items, limit=32):
    """Keep RAM choices across capacity/module/speed/price bands, then Pareto-prune.

    A missing speed stays unknown and is never treated as a fast DIMM.
    """
    candidates = [(item, memory_configuration(item)) for item in items]
    candidates = [(item, cfg) for item, cfg in candidates if cfg]
    frontier = []
    for item, cfg in candidates:
        speed = cfg['speed_mt_s'] or 0
        dominated = any(
            other.price_rub <= item.price_rub
            and other_cfg['capacity_gb'] >= cfg['capacity_gb']
            and (other_cfg['modules'] >= cfg['modules'])
            and (other_cfg['speed_mt_s'] or 0) >= speed
            and (other.price_rub < item.price_rub
                 or other_cfg['capacity_gb'] > cfg['capacity_gb']
                 or other_cfg['modules'] > cfg['modules']
                 or (other_cfg['speed_mt_s'] or 0) > speed)
            for other, other_cfg in candidates if other.id != item.id)
        if not dominated:
            frontier.append((item, cfg))
    # Keep a few useful representatives per structural class and price region;
    # this is deliberately wider than the old six cheapest offer cutoff.
    picked = {}
    groups = {}
    for item, cfg in frontier:
        key = (cfg['capacity_gb'], cfg['modules'])
        groups.setdefault(key, []).append((item, cfg))
    for group in groups.values():
        if len(picked) >= limit:
            break
        group.sort(key=lambda pair: (pair[0].price_rub, -(pair[1]['speed_mt_s'] or 0), pair[0].id))
        for pair in (group[0], max(group, key=lambda pair: (pair[1]['speed_mt_s'] or 0, -pair[0].price_rub, -pair[0].id))):
            if len(picked) >= limit:
                break
            picked[pair[0].id] = pair[0]
    for item, _ in sorted(frontier, key=lambda pair: (pair[0].price_rub, pair[0].id)):
        if len(picked) >= limit:
            break
        picked.setdefault(item.id, item)
    return sorted(picked.values(), key=lambda item: (item.price_rub, item.id))


def cpu_gaming_percentile(cpu, total_scores, per_core_scores, socket):
    """Conservative CPU hardware proxy, not Single Thread or game FPS."""
    total = bisect_right(total_scores, cpu.raw_score) / max(1, len(total_scores))
    if socket not in ('AM4', 'AM5') or not cpu.cores or cpu.cores <= 0 or not per_core_scores:
        return {'total': total, 'per_core': None, 'effective': total}
    per_core = bisect_right(per_core_scores, cpu.raw_score / cpu.cores) / len(per_core_scores)
    return {'total': total, 'per_core': per_core, 'effective': min(total, per_core)}


def storage_shortlist(items, evidence, limit=8):
    """Keep price/capacity/interface alternatives before full-build pricing."""
    groups = {}
    for item in items:
        spec = evidence[item.id]
        key = (item.source, spec['interface'], spec['capacity_gb'])
        groups.setdefault(key, []).append(item)
    choices = []
    for group in groups.values():
        choices.append(min(group, key=lambda item: (item.price_rub, item.id)))
    choices.sort(key=lambda item: (item.price_rub, item.id))
    frontier = []
    for item in choices:
        spec = evidence[item.id]
        if any(other.id != item.id and other.source == item.source and other.price_rub <= item.price_rub
               and evidence[other.id]['capacity_gb'] >= spec['capacity_gb']
               and evidence[other.id]['interface'] == spec['interface']
               and (other.price_rub < item.price_rub or
                    evidence[other.id]['capacity_gb'] > spec['capacity_gb'])
               for other in choices):
            continue
        frontier.append(item)
    return frontier[:limit]


def memory_candidates(items):
    """Pair identical sticks only when a current catalog row confirms quantity >= 2."""
    result = list(items)
    for item in items:
        data = attrs(item)
        stock = data.get('catalog_import', {})
        cfg = memory_configuration(item)
        if (item.origin != 'catalog_import' or stock.get('availability') != 'in_stock'
                or not isinstance(stock.get('quantity'), int) or stock['quantity'] < 2
                or not cfg or cfg['modules'] != 1 or cfg['capacity_gb'] not in (4, 8, 16, 32)):
            continue
        combined = dict(data)
        combined.update({'capacity_gb': cfg['capacity_gb'] * 2, 'modules': 2,
                         'ram_type': cfg['ram_type'],
                         **({'speed_mhz': cfg['speed_mt_s']} if cfg['speed_mt_s'] else {})})
        result.append(SimpleNamespace(
            id=-item.id, source=item.source, url=item.url,
            name=f"2×{cfg['capacity_gb']} GB ({item.name}; два отдельных модуля из одной позиции)",
            category=item.category, price_rub=item.price_rub * 2, condition=item.condition,
            hardware_id=item.hardware_id, observed_at=item.observed_at, origin=item.origin,
            attributes=json.dumps(combined), bundle_offer_ids=[item.id], bundle_quantity=2))
    return result


def memory_matches(memory, payload):
    config = memory_configuration(memory)
    return bool(config and config['ram_type'] == payload.ram_type and config['capacity_gb'] >= payload.ram_capacity_gb
                and config['modules'] in (1, 2))


def memory_quality(config, requested_capacity):
    """Declared capacity/module proxy, never an FPS uplift.

    Speed remains a separate known/unknown field and is only a tie-breaker;
    an unknown rate cannot score as either slow or fast.
    """
    capacity = min(config['capacity_gb'], 32) / min(max(requested_capacity, 16), 32)
    return (max(.01, min(1.0, capacity)) * (config['modules'] / 2)) ** .5


def cpu_board_matches(cpu, board):
    if re.search(r'\b(?:A520|B550)M?\b', board.name, re.I):
        return (bool(re.search(r'Ryzen\s+[3579]\s+(?:[3-9]\d{3}|\d{5})', cpu.name, re.I))
                and not re.search(r'\b(?:3200G|3400G)\b', cpu.name, re.I))
    intel = re.search(r'\bi[3579][ -]*(\d{4,5})', cpu.name, re.I)
    if intel:
        number=int(intel[1])
        if re.search(r'\b(?:H110|H170|H270|B150|B250|Z170|Z270)(?:M|I)?\b',board.name,re.I):
            return 6000<=number<8000
        if re.search(r'\b(?:H310|H370|B360|B365|Z370|Z390)(?:M|I)?\b',board.name,re.I):
            return 8000<=number<10000
        if 11000<=number<12000 and re.search(r'\b(?:H410|B460)(?:M|I)?\b',board.name,re.I):
            return False
    return True


def part(offer, quality=None, board=None):
    if quality and quality.get('interface') == 'NVMe':
        quality = {**quality, 'board_compatibility': nvme_board_evidence(board)}
    offer_id = offer.bundle_offer_ids[0] if getattr(offer, 'bundle_offer_ids', None) else offer.id
    return {'type': offer.category, 'name': offer.name, 'price': offer.price_rub, 'offer_id': offer_id,
            **({'quantity': offer.bundle_quantity, 'purchase_note': 'Два одинаковых модуля по подтверждённому остатку одной позиции; это не заводской комплект.'} if getattr(offer, 'bundle_quantity', None) else {}),
            'price_source': 'Справочная оценка' if offer.source=='reference' else LABELS[offer.source], 'price_date': public_offer(offer)['observed_at'],
            'price_url': offer.url, 'price_market': 'used_ru' if offer.condition == 'used' else 'retail_ru',
            'price_verified_at': public_offer(offer).get('price_verified_at'),
            **({'purchase_warning': 'Б/у SSD: перед покупкой запросите SMART, объём записей и проверку полного объёма. Состояние продавца автоматически не подтверждено.'} if quality and quality.get('condition') == 'used' else {}),
            **({'quality': quality} if quality else {})}


def unique_models(offers, limit, key_fn=None):
    result, seen = [], set()
    for offer in offers:
        key = key_fn(offer) if key_fn else re.sub(r'\W', '', offer.name.lower())
        if key not in seen:
            seen.add(key)
            result.append(offer)
        if len(result) >= limit:
            break
    return result


def assemble_auto(payload, db, allowed_offer_ids=None, preferred_source=None, flexible=False, observed=False):
    from app.services.builds import build_options, desktop_gpu
    pool = {category: [] for category in ('motherboard', 'memory', 'storage', 'psu', 'cooler', 'case')}
    evidence = {}
    for offer in available_offers(db, payload.price_sources, include_unavailable=observed):
        if allowed_offer_ids is not None and offer.id not in allowed_offer_ids:
            continue
        if offer.category not in pool:
            continue
        if offer.category in ('storage', 'psu', 'cooler'):
            quality, _ = quality_check(offer, payload.socket)
            if quality is None:
                continue
            evidence[offer.id] = quality
        pool[offer.category].append(offer)
    for category in pool:
        # RAM alternatives must survive to the complete-build budget check;
        # the fixed category share used to discard kits before optimization.
        limit = payload.budget if flexible or category in ('memory', 'storage') else part_limit(category, payload.budget, flexible=False)
        pool[category] = [offer for offer in pool[category] if offer.price_rub <= limit]
        if not pool[category]:
            labels = {'storage': 'внутреннего SSD', 'psu': 'проверенного блока питания', 'cooler': 'комплектного кулера',
                      'motherboard': 'материнской платы', 'memory': 'комплекта памяти', 'case': 'корпуса'}
            raise HTTPException(400, f"Не найдено подходящих предложений {labels[category]} в пределах {limit:,} ₽ для бюджета {payload.budget:,} ₽. Расширьте площадки или измените параметры. Более дорогая деталь не подставляется за счёт видеокарты.")
    def shortlist(items, limit, key_fn=None):
        chosen=unique_models(items,limit,key_fn)
        if preferred_source:
            for item in unique_models([item for item in items if item.source==preferred_source],3,key_fn):
                if item not in chosen:chosen.append(item)
        return chosen
    boards = shortlist([item for item in pool['motherboard'] if board_matches(item, payload)], 12)
    memory = memory_shortlist([item for item in memory_candidates(pool['memory']) if memory_matches(item, payload)])
    cases = gaming_cases(pool['case'], payload.budget, payload.case_style, flexible=flexible)
    if payload.selected_case_offer_id is not None:
        cases = [item for item in cases if item.id == payload.selected_case_offer_id]
    cases = distinct_cases(cases)
    if preferred_source:
        for item in distinct_cases(gaming_cases([item for item in pool['case'] if item.source==preferred_source],payload.budget,payload.case_style,flexible=flexible))[:3]:
            if item not in cases:cases.append(item)
    if not boards or not memory or not cases:
        raise HTTPException(400, 'В найденных предложениях нет подходящей платы, настольной памяти нужного объёма или корпуса в бюджете.')
    bases = []
    for board in boards:
        from app.services.technical_evidence import storage_status
        storage = [item for item in pool['storage'] if storage_status(board,item)['status']!='incompatible' and (evidence[item.id]['interface'] != 'NVMe' or nvme_board_evidence(board))]
        if not storage:
            continue
        drives = storage_shortlist(storage, evidence)
        for ram, drive, case in product(memory, drives, shortlist(cases,3)):
            board_format = attrs(board).get('form_factor')
            if attrs(case).get('board_formats') and board_format and board_format not in attrs(case)['board_formats']:
                continue
            base = [board, ram, drive, case]
            bases.append((sum(item.price_rub for item in base), base))
    def source_count(items):
        return sum(item.source == preferred_source for item in items) if preferred_source else 0
    bases.sort(key=lambda value: (-source_count(value[1]), value[0], tuple(item.id for item in value[1])))
    if not bases:
        raise HTTPException(400, 'Не удалось подтвердить совместимость накопителя с доступными платами в бюджете. Для NVMe нужен M.2 2280 PCIe; также можно выбрать внутренний SATA SSD.')
    # Automatic builds use found store offers, including when sources omitted.
    prices = price_map(db, payload.price_sources or list(LABELS), allowed_offer_ids=allowed_offer_ids, preferred_source=preferred_source, observed=observed)
    hardware = list(db.scalars(select(Hardware)))
    cpus = [item for item in hardware if item.type == 'CPU' and item.raw_score>0 and item.socket == payload.socket and item.id in prices]
    gpus = [item for item in hardware if item.type == 'GPU' and item.raw_score>0 and item.id in prices and desktop_gpu(item.name)]
    cpus=[h for h in cpus if payload.selected_cpu_id is None or h.id==payload.selected_cpu_id]
    gpus=[h for h in gpus if payload.selected_gpu_id is None or h.id==payload.selected_gpu_id]
    from app.core.config import settings
    def bounded(items,limit):
        if len(items)<=limit:return items
        # Union of affordable, fast, and efficient candidates, then deterministic cap.
        affordable=sorted(items,key=lambda h:(prices[h.id].price_rub,-h.raw_score,h.id))
        fast=sorted(items,key=lambda h:(-h.raw_score,prices[h.id].price_rub,h.id))
        efficient=sorted(items,key=lambda h:(-h.raw_score/max(1,prices[h.id].price_rub),h.id))
        chosen={}
        for group in zip(affordable,fast,efficient):
            for item in group:
                chosen.setdefault(item.id,item)
                if len(chosen)==limit:return list(chosen.values())
    original_counts=(len(cpus),len(gpus))
    # Empirical rank percentiles are stable across price-source scopes and
    # prevent CPU Mark's multi-core scale from being treated as FPS ratios.
    cpu_scores=sorted(item.raw_score for item in hardware if item.type=='CPU'
                      and item.socket==payload.socket and item.raw_score>0)
    per_core_scores=sorted(item.raw_score/item.cores for item in hardware if item.type=='CPU'
                           and item.socket==payload.socket and item.raw_score>0 and item.cores and item.cores>0)
    gpu_scores=sorted(item.raw_score for item in hardware if item.type=='GPU'
                      and item.raw_score>0 and desktop_gpu(item.name))
    cpus=bounded(cpus,settings.builder_max_cpu_candidates);gpus=bounded(gpus,settings.builder_max_gpu_candidates)
    deadline=time.monotonic()+settings.builder_seconds_per_profile
    timed_out=False;examined=0
    options, compositions = [], {}
    # Board/CPU compatibility does not depend on the GPU. Do not repeat its
    # regex and attribute checks for every RAM/SSD/case combination of every GPU.
    cpu_bases={}
    for cpu, gpu in product(cpus, gpus):
        if time.monotonic()>deadline:
            timed_out=True;break
        examined+=1
        if cpu.id not in cpu_bases:
            compatible_boards={board.id for board in boards if cpu_board_matches(cpu,board)}
            compatible=sorted(((cost,base) for cost,base in bases if base[0].id in compatible_boards),
                              key=lambda row:(row[0],-source_count(row[1])))
            costs=[row[0] for row in compatible]
            cpu_bases[cpu.id]=(compatible,costs,costs[0] if costs else payload.budget+1)
        compatible,costs,minimum_base=cpu_bases[cpu.id]
        watts, cooling = psu_requirement(cpu, gpu), cooling_requirement(cpu)
        from app.services.technical_evidence import psu_status
        supplies = [item for item in pool['psu'] if evidence[item.id]['watts'] >= watts and psu_status(item,cpu,gpu)['status']!='incompatible']
        coolers = [item for item in pool['cooler'] if evidence[item.id]['cooling_class'] >= cooling]
        if not supplies or not coolers:
            continue
        supply, cooler = min(supplies, key=lambda item:item.price_rub), min(coolers, key=lambda item:item.price_rub)
        pair_cost = prices[cpu.id].price_rub + prices[gpu.id].price_rub
        base_limit=payload.budget-pair_cost-supply.price_rub-cooler.price_rub
        if minimum_base>base_limit:
            continue
        viable = compatible[:bisect_right(costs,base_limit)]
        if not viable:
            continue
        # Prefer a verified 1 TB NVMe at a modest full-build premium.
        # The CPU/GPU pair and all eight component prices are already feasible.
        cheapest_cost = min(row[0] for row in viable)
        cheapest = min(viable, key=lambda row: row[0])
        cheap_drive = cheapest[1][2]
        cheap_spec = evidence[cheap_drive.id]
        cheap_price_per_gb = cheap_drive.price_rub / cheap_spec['capacity_gb']
        def acceptable_drive(row):
            if preferred_source:
                return True
            drive = row[1][2]
            capacity = evidence[drive.id]['capacity_gb']
            if drive.price_rub / capacity > cheap_price_per_gb * 1.10:
                return False
            # 2 TB is optional; use it when the additional complete-build cost
            # is modest and capacity is actually priced from this offer.
            return capacity < 2000 or row[0] - cheapest_cost <= payload.budget * .05
        suitable = [row for row in viable if acceptable_drive(row)] or [cheapest]
        def drive_rank(row):
            drive = evidence[row[1][2].id]
            capacity = drive['capacity_gb']
            return (source_count(row[1]) if preferred_source else 0,
                    capacity >= 1000 if payload.budget >= 80000 else capacity >= 500,
                    drive['interface'] == 'NVMe',
                    min(capacity, 2000), -row[0])
        cost, base = max(suitable, key=drive_rank)
        # Compare RAM options for this same board/SSD/case composition. The
        # optimization uses declared capacity/modules/speed, never an FPS bonus.
        same_support = [(candidate_cost, candidate) for candidate_cost, candidate in viable
                        if candidate[0].id == base[0].id and candidate[2].id == base[2].id
                        and candidate[3].id == base[3].id]
        if same_support:
            def ram_rank(row):
                candidate_cost, candidate = row
                cfg = memory_configuration(candidate[1])
                q = memory_quality(cfg, payload.ram_capacity_gb)
                speed=cfg.get('speed_mt_s') or 0
                kit=bool(cfg.get('factory_kit'))
                if payload.objective == 'economy':
                    return (candidate_cost, -q, -speed)
                if payload.objective == 'balanced':
                    return (-q, -kit, candidate_cost, -speed)
                return (-q, -kit, candidate_cost, -speed)
            cost, base = min(same_support, key=ram_rank)
        base_cost = pair_cost + cost
        if preferred_source:
            preferred_supplies = [item for item in supplies if item.source == preferred_source
                                  and base_cost + item.price_rub + cooler.price_rub <= payload.budget]
            supply = min(preferred_supplies,key=lambda item:item.price_rub) if preferred_supplies else supply
            preferred_coolers = [item for item in coolers if item.source == preferred_source
                                and base_cost + supply.price_rub + item.price_rub <= payload.budget]
            cooler = min(preferred_coolers,key=lambda item:item.price_rub) if preferred_coolers else cooler
        # Optional comfort/efficiency upgrades must preserve this CPU/GPU pair.
        if payload.budget >= 70000:
            towers = [item for item in coolers if evidence[item.id]['cooling_class'] >= 2
                      and (cooler.source != preferred_source or item.source == preferred_source)
                      and item.price_rub <= cooler.price_rub + 1500
                      and base_cost + supply.price_rub + item.price_rub <= payload.budget]
            cooler = towers[0] if towers else cooler
        if payload.budget >= 100000:
            gold = [item for item in supplies if 'Gold' in evidence[item.id]['label']
                    and (supply.source != preferred_source or item.source == preferred_source)
                    and item.price_rub <= supply.price_rub + 1000
                    and base_cost + item.price_rub + cooler.price_rub <= payload.budget]
            supply = gold[0] if gold else supply
        from app.services.physical_fit import physical_fit
        from app.db.models import StoreOffer
        gpu_offer=db.get(StoreOffer,getattr(prices[gpu.id],'offer_id',None)) if getattr(prices[gpu.id],'offer_id',None) else None
        if physical_fit(base[0],gpu_offer,base[3],supply,cooler)['status']=='incompatible':
            replacements=[]
            for candidate_cost,candidate_base in viable:
                for candidate_supply,candidate_cooler in product(shortlist(supplies,4),shortlist(coolers,4)):
                    total=pair_cost+candidate_cost+candidate_supply.price_rub+candidate_cooler.price_rub
                    if total<=payload.budget and physical_fit(candidate_base[0],gpu_offer,candidate_base[3],candidate_supply,candidate_cooler)['status']!='incompatible':
                        replacements.append((total,candidate_cost,candidate_base,candidate_supply,candidate_cooler))
            if not replacements:continue
            _,cost,base,supply,cooler=min(replacements,key=lambda item:item[0])
        components = [*base, supply, cooler]
        cost = prices[cpu.id].price_rub + prices[gpu.id].price_rub + sum(item.price_rub for item in components)
        if cost > payload.budget:
            continue
        memory_info = memory_configuration(base[1])
        # Keep legacy FPS independent of uncalibrated RAM/channel heuristics.
        fps = estimate_fps(cpu.raw_score, gpu.raw_score, gpu.name, payload.game, payload.mode, 1.0, cpu.name)
        # Equal-weight geometric mean of normalized CPU Mark, GPU G3D Mark,
        # and declared RAM quality. This is a hardware proxy, not calibrated FPS.
        ram_score=memory_quality(memory_info,payload.ram_capacity_gb)
        cpu_norm=cpu_gaming_percentile(cpu,cpu_scores,per_core_scores,payload.socket)['effective']
        gpu_norm=bisect_right(gpu_scores,gpu.raw_score)/max(1,len(gpu_scores))
        hw_score=(cpu_norm*gpu_norm*ram_score)**(1/3)
        balance_score=min(cpu_norm,gpu_norm,ram_score)
        # Only a hardware proxy: CPU Mark is used as a floor, never an FPS ratio.
        # Competitive 1080p Low breaks ties toward CPU; higher presets toward GPU.
        scenario_tie = cpu_norm if payload.game.value == 'CS2' and payload.mode.value == '1080p_low' else gpu_norm
        option = (cpu, gpu, cost, fps, hw_score, balance_score, scenario_tie)
        options.append(option)
        compositions[(cpu.id, gpu.id)] = components
    options = [o for o in options if (payload.selected_cpu_id is None or o[0].id == payload.selected_cpu_id)
               and (payload.selected_gpu_id is None or o[1].id == payload.selected_gpu_id)]
    if not options:
        raise HTTPException(400, 'Полная сбалансированная сборка с подходящим питанием и охлаждением не найдена в бюджете. Проверьте доступность предложений, измените платформу или расширьте площадки.')
    if preferred_source and payload.selected_cpu_id is None:
        counts = {(cpu.id,gpu.id):source_count(compositions[(cpu.id,gpu.id)]) + (prices[cpu.id].source==preferred_source) +
                  (prices[gpu.id].source==preferred_source) for cpu,gpu,*_ in options}
        most = max(counts.values())
        options = [option for option in options if counts[(option[0].id,option[1].id)] == most]
    variants = build_options(options, payload.target_fps, payload.game, payload.mode, payload.workload, payload.objective,
                             hardware_score=(lambda option: option[4]) if payload.workload=='gaming' else None,
                             hardware_rank=(lambda option: (option[5],option[6],option[4],-option[2]))
                             if payload.workload=='gaming' and payload.objective in ('balanced','performance') else None)

    def render(option, key='recommended', title='Рекомендуемая', summary='Сбалансированная игровая конфигурация в вашем бюджете.'):
        cpu, gpu, _, fps = option[:4]
        if key == 'recommended' and payload.workload == 'gaming' and payload.objective == 'performance':
            title = 'Максимальная игровая производительность'
            summary = ('Сильнейшая доступная по аппаратному балансу CPU/GPU/RAM сборка в бюджете. '
                       'Реальный FPS для этой полной конфигурации не измерен.')
        supporting = list(compositions[(cpu.id, gpu.id)])
        board = supporting[0]
        if payload.selected_case_offer_id is None:
            index = {'recommended': 0, 'value': 1, 'performance': 2}[key]
            base_cost = sum(item.price_rub for item in supporting) - supporting[3].price_rub
            board_format = attrs(board).get('form_factor')
            alternatives = [case for case in cases if (not attrs(case).get('board_formats') or not board_format or board_format in attrs(case)['board_formats'])
                            and prices[cpu.id].price_rub + prices[gpu.id].price_rub + base_cost + case.price_rub <= payload.budget]
            if alternatives:
                preferred_cases = [case for case in alternatives if not preferred_source or
                                   supporting[3].source != preferred_source or case.source == preferred_source]
                if preferred_cases:
                    supporting[3] = preferred_cases[min(index, len(preferred_cases) - 1)]
        parts = [{'type': item.type, 'id': item.id, 'name': item.name, 'price': prices[item.id].price_rub,
                  **public_price(prices[item.id])} for item in (cpu, gpu)]
        parts += [part(item, evidence.get(item.id), board) for item in supporting]
        total = sum(item['price'] for item in parts)
        gaming_metrics = payload.workload != 'cpu_work'
        outlook = fps_outlook(fps, gpu.name, payload.game, payload.mode) if gaming_metrics else None
        memory_info = memory_configuration(supporting[1])
        hardware_metrics = None if payload.workload=='cpu_work' else {
            'cpu_passmark': cpu.raw_score, 'gpu_g3d_mark': gpu.raw_score,
            'cpu_catalog_percentile': bisect_right(cpu_scores,cpu.raw_score)/max(1,len(cpu_scores)),
            'cpu_per_core_percentile': cpu_gaming_percentile(cpu,cpu_scores,per_core_scores,payload.socket)['per_core'],
            'cpu_gaming_proxy_percentile': cpu_gaming_percentile(cpu,cpu_scores,per_core_scores,payload.socket)['effective'],
            'gpu_catalog_percentile': bisect_right(gpu_scores,gpu.raw_score)/max(1,len(gpu_scores)),
            'ram_capacity_gb': memory_info['capacity_gb'], 'ram_modules': memory_info['modules'],
            'ram_speed_mt_s': memory_info.get('speed_mt_s'), 'ram_dual_channel_potential': memory_info['dual_channel_potential'],
            'ram_factory_kit': memory_info['factory_kit'],
            'ram_quality_proxy': memory_quality(memory_info,payload.ram_capacity_gb),
            'storage_capacity_gb': evidence[supporting[2].id]['capacity_gb'],
            'storage_interface': evidence[supporting[2].id]['interface'],
            'balanced_floor_proxy': option[5], 'scenario_tiebreak_proxy': option[6],
        }
        return {'solver_diagnostics':{'method':'bounded joint search','cpu_candidates':len(cpus),'gpu_candidates':len(gpus),'original_cpu_candidates':original_counts[0],'original_gpu_candidates':original_counts[1],'pairs_examined':examined,'time_limit_reached':timed_out,'global_optimum_proven':False},'workload':payload.workload,'objective':payload.objective, 'selection_score':cpu.raw_score if payload.workload=='cpu_work' else option[5], 'selection_basis':'cpu_mark' if payload.workload=='cpu_work' else 'weakest_normalized_cpu_gpu_ram_hardware_dimension', 'hardware_quality_score':None if payload.workload=='cpu_work' else option[4], 'hardware_quality_basis':None if payload.workload=='cpu_work' else 'conservative_cpu_mark_total_and_per_core_percentile_gpu_g3d_and_declared_ram_proxy', 'hardware_metrics':hardware_metrics, 'scenario': 'build', 'game': payload.game.value, 'mode': payload.mode.value, 'variant_key': key, 'title': title, 'summary': summary,
                'actual_config': {'socket':payload.socket,'ram_type':payload.ram_type,'ram_capacity_gb':payload.ram_capacity_gb},
                'budget_reallocated': flexible or supporting[2].price_rub > part_limit('storage', payload.budget), 'memory_configuration': memory_info,
                'preferred_parts_count': sum(item.get('price_source') == LABELS.get(preferred_source) for item in parts),
                'parts': parts, 'total_price': total, 'remaining_budget': payload.budget - total,
                'fps': fps if gaming_metrics else None,
                'fps_outlook': outlook,
                # No current benchmark validates this complete CPU/GPU/RAM
                # configuration; a legacy interval cannot certify the goal.
                'target_reached': None,
                'recommendation': summary,
                'compatibility_notes': [f'Плата выбрана под {payload.socket} и {payload.ram_type}; поддержка CPU в BIOS требует отдельной проверки.',
                    (f"Память: {memory_info['modules']} модуля; конфигурация поддерживает двухканальный режим при поддержке платы. Это аппаратная характеристика, не FPS-бонус." if memory_info['modules']==2 else
                     'Память: один модуль; двухканальный режим не подтверждён. FPS-бонус за память не применяется.'),
                    (f"Паспортная скорость RAM {memory_info['speed_mt_s']} MT/s указана в предложении; фактическая частота, XMP/EXPO и число слотов платы не подтверждены." if memory_info.get('speed_mt_s') else
                     'Скорость RAM и поддержка профиля памяти не подтверждены; число слотов платы проверьте отдельно.'),
                    f'Минимальная мощность БП по консервативному правилу подбора этой пары: {psu_requirement(cpu, gpu)} Вт. Разъёмы и требования конкретной версии GPU проверьте отдельно.',
                    'Кулер выбран с учётом класса тепловой нагрузки CPU. Проверьте его высоту, комплект креплений и зазоры корпуса.',
                    f'Первоначальная доля SSD — {part_limit("storage", payload.budget):,} ₽; возможно перераспределение в пределах всей суммы ПК. NVMe требует подтверждённого слота.',
                    'Длина GPU, высота кулера и все физические зазоры автоматически подтверждены только при наличии характеристик предложений; перед покупкой сверьте размеры.',
                    ('FPS — оценочный диапазон по модели; стоимость доставки включается только при наличии явных данных; персональные скидки не учтены.'
                     if gaming_metrics else 'Рабочий профиль ранжирован по CPU Mark; FPS и скорость приложений не оценивались.') ]}
    alternatives = [render(option, key, title, summary) for key, title, summary, option in variants]
    result = alternatives[0]
    return {**result, 'alternatives': alternatives}

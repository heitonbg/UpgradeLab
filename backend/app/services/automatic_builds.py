"""Select the complete PC with its CPU/GPU, supply and cooler in one budget."""
import json
import re
from itertools import product
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
from app.services.assembly_policy import part_limit, psu_requirement, cooling_requirement, balanced_options


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
    return {'ram_type': ram, 'capacity_gb': capacity, 'modules': modules}


def memory_matches(memory, payload):
    config = memory_configuration(memory)
    return bool(config and config['ram_type'] == payload.ram_type and config['capacity_gb'] >= payload.ram_capacity_gb
                and config['modules'] in (1, 2))


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
    return {'type': offer.category, 'name': offer.name, 'price': offer.price_rub, 'offer_id': offer.id,
            'price_source': LABELS[offer.source], 'price_date': public_offer(offer)['observed_at'],
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
        limit = part_limit(category, payload.budget, flexible=flexible)
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
    memory = shortlist([item for item in pool['memory'] if memory_matches(item, payload)], 6)
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
        storage = [item for item in pool['storage'] if evidence[item.id]['interface'] != 'NVMe' or nvme_board_evidence(board)]
        if not storage:
            continue
        drives = shortlist(storage, 3, lambda item: (evidence[item.id]['model'], evidence[item.id]['capacity_gb']))
        # Keep affordable capacity/interface alternatives for the joint solver.
        for extra in [next((item for item in storage if evidence[item.id]['capacity_gb'] >= 1000 and evidence[item.id]['interface'] == 'NVMe'), None),
                      next((item for item in storage if evidence[item.id]['capacity_gb'] >= 1000 and evidence[item.id]['interface'] == 'SATA'), None),
                      next((item for item in storage if evidence[item.id]['interface'] == 'NVMe'), None)]:
            if extra is not None and extra not in drives:
                drives.append(extra)
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
    cpus = [item for item in hardware if item.type == 'CPU' and item.socket == payload.socket and item.id in prices]
    gpus = [item for item in hardware if item.type == 'GPU' and item.id in prices and desktop_gpu(item.name)]
    options, compositions = [], {}
    # Board/CPU compatibility does not depend on the GPU. Do not repeat its
    # regex and attribute checks for every RAM/SSD/case combination of every GPU.
    cpu_bases={}
    for cpu, gpu in product(cpus, gpus):
        if cpu.id not in cpu_bases:
            compatible_boards={board.id for board in boards if cpu_board_matches(cpu,board)}
            compatible=[(cost,base) for cost,base in bases if base[0].id in compatible_boards]
            cpu_bases[cpu.id]=(compatible,min((cost for cost,_ in compatible),default=payload.budget+1))
        compatible,minimum_base=cpu_bases[cpu.id]
        watts, cooling = psu_requirement(cpu, gpu), cooling_requirement(cpu)
        supplies = [item for item in pool['psu'] if evidence[item.id]['watts'] >= watts]
        coolers = [item for item in pool['cooler'] if evidence[item.id]['cooling_class'] >= cooling]
        if not supplies or not coolers:
            continue
        supply, cooler = min(supplies, key=lambda item:item.price_rub), min(coolers, key=lambda item:item.price_rub)
        pair_cost = prices[cpu.id].price_rub + prices[gpu.id].price_rub
        base_limit=payload.budget-pair_cost-supply.price_rub-cooler.price_rub
        if minimum_base>base_limit:
            continue
        viable = [(cost, base) for cost, base in compatible if cost<=base_limit]
        if not viable:
            continue
        cost, base = viable[0]
        nvme = [(candidate_cost, candidate) for candidate_cost, candidate in viable
                if evidence[candidate[2].id]['interface'] == 'NVMe'
                and candidate_cost <= cost + max(500, base[2].price_rub * .15,
                                                 payload.budget * .04 if payload.budget >= 80000 else 0)]
        if nvme:
            preferred_nvme = [item for item in nvme if source_count(item[1]) >= source_count(base)]
            if preferred_nvme:
                cost, base = preferred_nvme[0]
        if payload.budget >= 80000:
            larger = [(candidate_cost, candidate) for candidate_cost, candidate in viable
                      if evidence[candidate[2].id]['capacity_gb'] >= 1000
                      and evidence[candidate[2].id]['interface'] == evidence[base[2].id]['interface']
                      and candidate_cost <= cost + base[2].price_rub * .4]
            if larger:
                preferred_larger = [item for item in larger if source_count(item[1]) >= source_count(base)]
                if preferred_larger:
                    cost, base = preferred_larger[0]
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
        components = [*base, supply, cooler]
        cost = prices[cpu.id].price_rub + prices[gpu.id].price_rub + sum(item.price_rub for item in components)
        if cost > payload.budget:
            continue
        memory_info = memory_configuration(base[1])
        ram_factor = (1.16 if payload.ram_type == 'DDR5' else 1.07) if memory_info['modules'] == 2 else 1.0
        fps = estimate_fps(cpu.raw_score, gpu.raw_score, gpu.name, payload.game, payload.mode, ram_factor)
        option = (cpu, gpu, cost, fps)
        options.append(option)
        compositions[(cpu.id, gpu.id)] = components
    if not options:
        raise HTTPException(400, 'Полная сбалансированная сборка с подходящим питанием и охлаждением не найдена в бюджете. Проверьте доступность предложений, измените платформу или расширьте площадки.')
    if preferred_source and payload.selected_cpu_id is None:
        counts = {(cpu.id,gpu.id):source_count(compositions[(cpu.id,gpu.id)]) + (prices[cpu.id].source==preferred_source) +
                  (prices[gpu.id].source==preferred_source) for cpu,gpu,_,_ in options}
        most = max(counts.values())
        options = [option for option in options if counts[(option[0].id,option[1].id)] == most]
    variants = build_options(balanced_options(options, payload.mode), payload.target_fps, payload.game, payload.mode)

    def render(option, key='recommended', title='Рекомендуемая', summary='Сбалансированная игровая конфигурация в вашем бюджете.'):
        cpu, gpu, _, fps = option
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
        outlook = fps_outlook(fps, gpu.name, payload.game, payload.mode)
        memory_info = memory_configuration(supporting[1])
        return {'scenario': 'build', 'variant_key': key, 'title': title, 'summary': summary,
                'actual_config': {'socket':payload.socket,'ram_type':payload.ram_type,'ram_capacity_gb':payload.ram_capacity_gb},
                'budget_reallocated': flexible, 'memory_configuration': memory_info,
                'preferred_parts_count': sum(item.get('price_source') == LABELS.get(preferred_source) for item in parts),
                'parts': parts, 'total_price': total, 'remaining_budget': payload.budget - total, 'fps': fps,
                'fps_outlook': outlook, 'target_reached': outlook['minimum'] >= payload.target_fps,
                'recommendation': summary,
                'compatibility_notes': [f'Плата выбрана под {payload.socket} и {payload.ram_type}; поддержка CPU в BIOS требует отдельной проверки.',
                    ('Память: два модуля; учтён двухканальный режим.' if memory_info['modules']==2 else
                     'Память: один модуль. В прогноз не включена прибавка от двухканального режима; второй модуль можно добавить позже.'),
                    f'Минимальная мощность БП по консервативному правилу подбора этой пары: {psu_requirement(cpu, gpu)} Вт. Разъёмы и требования конкретной версии GPU проверьте отдельно.',
                    'Кулер выбран с учётом класса тепловой нагрузки CPU. Проверьте его высоту, комплект креплений и зазоры корпуса.',
                    f'На SSD отведено до {part_limit("storage", payload.budget,flexible=flexible):,} ₽. NVMe предпочитается при подтверждённом слоте и небольшой доплате.',
                    'Длина GPU, высота кулера и все физические зазоры автоматически подтверждены только при наличии характеристик предложений; перед покупкой сверьте размеры.',
                    'FPS — оценочный диапазон по модели; стоимость доставки и персональные скидки не учтены.']}
    alternatives = [render(option, key, title, summary) for key, title, summary, option in variants]
    result = alternatives[0]
    if payload.selected_cpu_id is not None:
        selected = next((option for option in options if option[0].id == payload.selected_cpu_id and option[1].id == payload.selected_gpu_id), None)
        if selected is None:
            raise HTTPException(400, 'Выбранная пара CPU/GPU больше не помещается в бюджет с подходящими остальными деталями. Выполните подбор заново.')
        result = render(selected)
    return {**result, 'alternatives': alternatives}

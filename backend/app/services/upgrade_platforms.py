"""Price a platform change as a complete CPU/board/RAM/cooler package."""
from types import SimpleNamespace
from datetime import datetime, timedelta
import json
import re

from app.services.automatic_builds import board_matches, memory_matches, memory_configuration, cpu_board_matches, part
from app.services.assembly_policy import cooling_requirement
from app.services.component_quality import quality_check
from app.services.calculator import meaningful_upgrade
from app.services.performance import estimate_fps, fps_outlook
from app.services.prices import public_price
from app.services.upgrade_prices import upgrade_market_rows


def platform_choices(payload, db, hardware, prices, current_cpu, gpu, current_fps, total_budget):
    selected = payload.selected_platform.model_dump() if payload.selected_platform else None
    rows = upgrade_market_rows(db, payload.price_sources)
    capacity = payload.ram_manual.capacity_gb if payload.ram_manual else None
    if payload.ram_id:
        ram = next((item for item in hardware if item.id == payload.ram_id), None)
        capacity = ram.ram_capacity_gb if ram else None
    capacity = max(8, capacity or 8)
    profiles = {'AM4': 'DDR4', 'LGA1200': 'DDR4', 'LGA1700': 'DDR4', 'AM5': 'DDR5'}
    results = []
    for cpu in hardware:
        if cpu.type != 'CPU' or cpu.socket not in profiles or cpu.socket == current_cpu.socket or cpu.id not in prices:
            continue
        if cpu.socket == 'AM4' and not re.search(r'Ryzen\s+[3579]\s+[3-9]\d{3}',cpu.name,re.I):
            continue
        if selected and cpu.id != selected['cpu_id']:
            continue
        # Every included price must be observed; no synthetic supporting costs.
        quote = prices[cpu.id]
        if quote.market == 'retail_us_converted' or quote.observed_at < datetime.utcnow()-timedelta(days=7):
            continue
        profile = SimpleNamespace(socket=cpu.socket, ram_type=profiles[cpu.socket], ram_capacity_gb=capacity)
        boards = [row for row in rows if row.category == 'motherboard' and board_matches(row, profile)
                  and cpu_board_matches(cpu, row) and (not selected or row.id == selected['motherboard_offer_id'])]
        memories = [row for row in rows if row.category == 'memory' and memory_matches(row, profile)
                    and (not selected or row.id == selected['memory_offer_id'])]
        coolers = []
        for row in rows:
            if row.category != 'cooler' or selected and row.id != selected['cooler_offer_id']:
                continue
            quality, _ = quality_check(row, cpu.socket)
            if quality and quality['cooling_class'] >= cooling_requirement(cpu):
                coolers.append(row)
        if not boards or not memories or not coolers:
            continue
        def historical(row):
            data = json.loads(row.attributes)
            return row.origin in ('feed','product_page') or bool(data.get('last_verified_price')) or data.get('price_verification',{}).get('status') == 'verified'
        # A cheap raw search price must not replace known page observations of
        # complete coolers (the earlier 846-ruble search mismatch, for example).
        reliable_coolers = [row for row in coolers if historical(row)]
        if reliable_coolers:
            coolers = reliable_coolers
        board, memory, cooler = (min(pool, key=lambda row: (row.price_rub, row.id))
                                 for pool in (boards, memories, coolers))
        memory_info = memory_configuration(memory)
        ram_factor = (1 if memory_info['modules'] == 2 else .93) if payload.game.value == 'CS2' else (
            1.07 if memory_info['modules'] == 2 else 1)
        fps = estimate_fps(cpu.raw_score, gpu.raw_score, gpu.name, payload.game, payload.mode, ram_factor, cpu.name)
        if not meaningful_upgrade(current_fps, fps):
            continue
        cpu_part = {'type': 'CPU', 'name': cpu.name, 'price': quote.price_rub,
                    **{key: value for key, value in public_price(quote).items() if key != 'avg_price'}}
        parts = [cpu_part, part(board), part(memory), part(cooler)]
        for item in parts:
            item['price_verified_at'] = None
            item['price_status'] = 'unconfirmed'
        price = sum(item['price'] for item in parts)
        selection = {'cpu_id': cpu.id, 'motherboard_offer_id': board.id,
                     'memory_offer_id': memory.id, 'cooler_offer_id': cooler.id}
        key = 'platform:' + ':'.join(str(value) for value in selection.values())
        shortfall = max(0, price-total_budget) if payload.budget is not None or payload.sell_mode == 'budget_plus_sell' else 0
        results.append({'key': key, 'id': cpu.id, 'kind': 'platform', 'component': 'CPU',
                        'name': cpu.name, 'price': price, 'fps': fps, 'gain': fps-current_fps,
                        'target_reached': fps >= payload.target_fps,
                        'fps_outlook': fps_outlook(fps, gpu.name, payload.game, payload.mode),
                        'parts': parts, 'platform_selection': selection,
                        'socket': cpu.socket, 'ram_type': profile.ram_type,
                        'ram_capacity_gb': memory_info['capacity_gb'],
                        'budget_shortfall': shortfall, 'selection_allowed': shortfall == 0,
                        'compatibility_notes': [
                            f'Переход с {current_cpu.socket or "неизвестного сокета"} на {cpu.socket}: в стоимость включены CPU, плата, RAM и новый кулер.',
                            f'Существующая видеокарта {gpu.name} остаётся. Накопитель, БП и корпус не заменяются; проверьте их разъёмы, мощность и форм-фактор.',
                            'Сокет, тип и объём RAM, поколение CPU и крепление кулера проверены по доступным данным. Версию BIOS и габариты проверьте перед покупкой.',
                            'Цены — предварительная оценка по наблюдениям за 7 дней, не подтверждение текущего наличия.']})
    if selected:
        return results
    if not results:
        return []
    affordable = [item for item in results if item['selection_allowed']]
    reached = [item for item in affordable if item['target_reached']]
    primary = min(reached, key=lambda item: (item['price'], -item['fps'])) if reached else (
        max(affordable, key=lambda item: (item['fps'], -item['price'])) if affordable else min(results, key=lambda item: item['price']))
    ordered = [primary, *sorted(results, key=lambda item: (item['budget_shortfall'], item['price'], -item['fps']))]
    choices, seen = [], set()
    for item in ordered:
        if item['id'] not in seen:
            choices.append(item)
            seen.add(item['id'])
        if len(choices) == 3:
            break
    return choices

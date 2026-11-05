from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from app.api.deps import DBSession
from app.crud import hardware as hw_crud
from app.db.models import Hardware
from app.schemas.calculate import CalculateRequest, CalculateResponse
from app.services import calculator
from app.services.prices import public_price
from app.services.performance import fps_outlook, CS2_CPU_SOURCE
from app.services.upgrade_prices import upgrade_price_map, avito_price_estimates, refresh_upgrade_prices, upgrade_search_summary
from app.services.upgrade_platforms import platform_choices
from dataclasses import replace

router = APIRouter(prefix="/api", tags=["calculator"])

from app.services.builds import BuildRequest, assemble


@router.post("/assemble")
def post_assemble(payload: BuildRequest, db: DBSession):
    return assemble(payload, db)


@router.post("/calculate", response_model=CalculateResponse)
def post_calculate(payload: CalculateRequest, db: DBSession):
    if payload.selected_upgrade_id and payload.selected_platform:
        raise HTTPException(422, 'Выберите один вариант: замену детали или смену платформы.')
    cpu = hw_crud.get_by_id(db, payload.cpu_id)
    gpu = hw_crud.get_by_id(db, payload.gpu_id)

    if cpu is None or cpu.type != "CPU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CPU не найдена")
    if gpu is None or gpu.type != "GPU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "GPU не найдена")

    # Получаем все CPU и GPU для поиска апгрейда в рамках бюджета
    all_hw = list(db.scalars(select(Hardware)))
    ram_type, ram_channels = None, None
    if payload.ram_id:
        ram = db.get(Hardware, payload.ram_id)
        if not ram or ram.type != 'RAM':
            raise HTTPException(status.HTTP_400_BAD_REQUEST, 'RAM не найдена')
        ram_type, ram_channels = ram.ram_type, ram.ram_channels
    elif payload.ram_manual:
        ram_type, ram_channels = payload.ram_manual.type, payload.ram_manual.channels
    from datetime import datetime
    search_started = datetime.utcnow()
    statuses = []
    if payload.refresh_avito_prices:
        import time
        from app.services.offers import search_offers
        single_offer_fallback = payload.sell_mode == 'budget_plus_sell' and payload.expected_sale_price is None
        statuses = refresh_upgrade_prices(
            db, all_hw, cpu, gpu, time.monotonic() + 45, search_offers,
            payload.price_sources, payload.game, payload.mode, resale_fallback=single_offer_fallback,
            target_fps=payload.target_fps, ram_type=ram_type, ram_channels=ram_channels, focus_id=payload.price_lookup_id)
    prices = upgrade_price_map(db, payload.price_sources)
    resale_quotes = avito_price_estimates(db) if payload.sell_mode == 'budget_plus_sell' else {}
    def sale_value(hardware_id):
        if payload.sell_mode != 'budget_plus_sell':
            return 0
        if payload.expected_sale_price is not None:
            return payload.expected_sale_price
        return resale_quotes[hardware_id].price_rub if hardware_id in resale_quotes else 0
    all_cpus = [
        {"id": h.id, "name": h.name, "raw_score": h.raw_score, "avg_price": prices[h.id].price_rub if h.id in prices else None, "socket": h.socket}
        for h in all_hw if h.type == "CPU"
    ]
    all_gpus = [
        {"id": h.id, "name": h.name, "raw_score": h.raw_score, "avg_price": prices[h.id].price_rub if h.id in prices else None, "vram": h.vram}
        for h in all_hw if h.type == "GPU"
    ]
    all_rams = [
        {"id": h.id, "name": h.name, "raw_score": h.raw_score, "ram_type": h.ram_type, "ram_capacity_gb": h.ram_capacity_gb, "ram_channels": h.ram_channels}
        for h in all_hw if h.type == "RAM"
    ]

    # Получаем VRAM и сокет текущей GPU/CPU
    gpu_vram = gpu.vram
    cpu_socket = cpu.socket
    
    result = calculator.calculate(
        cpu_raw=cpu.raw_score,
        gpu_raw=gpu.raw_score,
        game=payload.game,
        mode=payload.mode,
        budget=payload.budget,
        cpu_price=sale_value(cpu.id),
        gpu_price=sale_value(gpu.id),
        cpu_socket=cpu_socket,
        cpu_name=cpu.name,
        gpu_name=gpu.name,
        gpu_vram=gpu_vram,
        ram_type=ram_type,
        ram_channels=ram_channels,
        all_cpus=all_cpus,
        all_gpus=all_gpus,
        all_rams=all_rams,
        ai_mode=payload.ai_mode,
        sell_mode=payload.sell_mode,
        target_fps=payload.target_fps,
        selected_upgrade_id=payload.selected_upgrade_id,
    )

    resale_hardware = cpu if result.bottleneck.value == 'CPU' else gpu
    resale_status = ('disabled' if payload.sell_mode != 'budget_plus_sell' else
                     'manual' if payload.expected_sale_price is not None else
                     'estimated' if resale_hardware.id in resale_quotes else 'unavailable')
    resale_notice = None
    if resale_status == 'unavailable':
        resale_notice = (f'Автоматическая цена продажи {resale_hardware.name} на Avito не получена. '
                         f'{payload.budget or 0:,} ₽ — только ваши деньги; общая сумма после продажи пока неизвестна. '
                         'Повторите автоматический поиск или укажите ожидаемую цену продажи в форме.')
        result = replace(result, recommendation=result.recommendation.replace(
            'после учёта продажи доступно', 'без оценки продажи доступно'))

    platforms, chosen_platform, platform_note = [], None, None
    legacy = cpu.socket not in ('AM4', 'AM5', 'LGA1200', 'LGA1700')
    if result.bottleneck.value == 'CPU' and (legacy or not result.upgrade_id or payload.selected_platform):
        platforms = platform_choices(payload, db, all_hw, prices, cpu, gpu, result.current_fps, result.total_budget)
        affordable = [item for item in platforms if item['selection_allowed']]
        if payload.selected_platform:
            if not affordable:
                if resale_status == 'unavailable':
                    raise HTTPException(400, 'Цена продажи старого CPU не получена: бюджет для этого комплекта пока не подтверждён. Повторите поиск или укажите ожидаемую цену продажи.')
                raise HTTPException(400, 'Выбранный комплект платформы устарел, несовместим или больше не помещается в бюджет. Повторите расчёт.')
            chosen_platform = affordable[0]
        elif affordable and not payload.selected_upgrade_id and result.current_fps < payload.target_fps:
            reached = [item for item in affordable if item['target_reached']]
            candidate = min(reached, key=lambda item: item['price']) if reached else max(affordable, key=lambda item: (item['fps'], -item['price']))
            if (not result.upgrade_id or candidate['target_reached'] and not result.upgraded_fps >= payload.target_fps
                    or candidate['target_reached'] and candidate['price'] < result.avg_price
                    or not result.upgraded_fps >= payload.target_fps and candidate['fps'] > result.upgraded_fps):
                chosen_platform = candidate
        if platforms:
            cheapest = min(platforms, key=lambda item: item['price'])
            platform_note = ('Проверены комплекты смены платформы: CPU, материнская плата, RAM и кулер. '
                             'Видеокарта остаётся. Автоматическая оценка продажи учитывает только старый CPU.')
            if not affordable:
                if resale_status == 'unavailable':
                    platform_note += f" Минимальный найденный комплект — {cheapest['price']:,} ₽. Его доступность по бюджету зависит от ещё неизвестной цены продажи старого CPU."
                else:
                    platform_note += f" Минимальный найденный комплект — {cheapest['price']:,} ₽; сверх общего бюджета нужно ещё {cheapest['budget_shortfall']:,} ₽."
        elif legacy:
            platform_note = ('Для старой платформы стоит сравнить замену CPU вместе с платой, RAM и кулером. '
                             'Полный совместимый комплект с известными ценами пока не найден; стоимость недостающих деталей не подставляется.')
    elif payload.selected_platform:
        raise HTTPException(400, 'Смена CPU-платформы не соответствует текущему сценарию ограничения производительности.')

    if chosen_platform:
        choice = chosen_platform
        explanation = (f"Рассмотрена смена платформы {cpu.socket} → {choice['socket']}: {choice['name']}, плата, RAM и кулер. "
                       f"Сумма комплекта {choice['price']:,} ₽; прогноз {choice['fps']} FPS вместо {result.current_fps} FPS. ")
        explanation += (f'Цель {payload.target_fps} FPS достигнута по модели.' if choice['target_reached'] else
                        f'Цель {payload.target_fps} FPS не достигнута; дальнейший результат ограничен оставшейся видеокартой и моделью расчёта.')
        result = replace(result, upgraded_fps=choice['fps'], recommendation=explanation,
                         avg_price=choice['price'], upgrade_id=choice['id'], upgrade_name=choice['name'],
                         upgrade_component=f"Смена платформы: {choice['name']} + плата + RAM + кулер",
                         within_budget=payload.budget is not None or payload.sell_mode == 'budget_plus_sell', is_maxed_out=False)

    def outlook(fps, gpu_name):
        data = fps_outlook(fps, gpu_name, payload.game, payload.mode)
        data.update(target_basis='central_estimate', central_estimate=fps)
        if payload.game.value == 'CS2':
            data['context_sources'].append({'title': 'ComputerBase: сравнение CPU в CS2, 720p, RTX 4090 (2023)', 'url': CS2_CPU_SOURCE})
            data['note'] += ' Для части CPU используются относительные результаты отдельного теста CS2; похожие и отсутствующие CPU оцениваются моделью. Это не измерение вашей связки.'
        return data

    alternatives = []
    for variant in result.alternatives:
        if legacy and not variant.get('price'):
            continue
        item = dict(variant)
        item.update(kind='single', key=f"single:{item['id']}")
        item['price_quote'] = public_price(prices.get(item['id']))
        item['fps_outlook'] = outlook(item['fps'], item['name'] if item['component'] == 'GPU' else gpu.name)
        alternatives.append(item)
    for item in platforms:
        item['resale_value'] = result.current_component_price
        item['net_cost'] = max(0, item['price']-result.current_component_price)
        item['price_quote'] = {'avg_price': item['price'], 'price_source': 'Сумма комплектующих', 'price_origin': 'platform_total'}
        item['fps_outlook'] = outlook(item['fps'], gpu.name)
    if platforms:
        combined = [*platforms, *alternatives] if chosen_platform or legacy else [*alternatives, *platforms]
        if chosen_platform:
            combined.sort(key=lambda item: item['key'] != chosen_platform['key'])
        alternatives = combined[:3]
    for item in alternatives:
        item['resale_status'] = resale_status
        if resale_status == 'unavailable':
            item['resale_value'] = None
            item['net_cost'] = None
            if item.get('budget_shortfall', 0) > 0:
                item['cash_shortfall'] = item['budget_shortfall']
                item['budget_shortfall'] = None
                item['selection_block_reason'] = 'resale_price_unavailable'
    resale_price = None
    if payload.sell_mode == 'budget_plus_sell':
        if payload.expected_sale_price is not None:
            resale_price = {'avg_price': payload.expected_sale_price, 'price_source': 'Ожидаемая цена пользователя',
                            'price_origin': 'manual', 'price_date': None, 'price_url': None}
        else:
            resale_price = public_price(resale_quotes.get(cpu.id if result.bottleneck.value == 'CPU' else gpu.id))
    
    return CalculateResponse(
        bottleneck=result.bottleneck,
        current_fps=result.current_fps,
        upgraded_fps=result.upgraded_fps,
        recommendation=result.recommendation,
        avg_price=result.avg_price,
        within_budget=result.within_budget,
        upgrade_component=result.upgrade_component,
        ai_warning=result.ai_warning,
        current_component_price=result.current_component_price,
        total_budget=result.total_budget,
        mode=result.mode,
        is_maxed_out=result.is_maxed_out,
        upgrade_price=({'avg_price':result.avg_price, 'price_source':'Сумма комплектующих', 'price_origin':'platform_total'}
                       if chosen_platform else public_price(prices.get(result.upgrade_id))),
        upgrade_name=result.upgrade_name,
        upgrade_id=result.upgrade_id,
        target_fps=payload.target_fps,
        current_fps_outlook=outlook(result.current_fps, gpu.name),
        upgraded_fps_outlook=outlook(result.upgraded_fps, result.upgrade_name if result.upgrade_id and result.bottleneck.value == 'GPU' else gpu.name),
        target_reached=result.upgraded_fps >= payload.target_fps,
        compatibility_notes=chosen_platform['compatibility_notes'] if chosen_platform else (
            ["Совпадение сокета проверено. Поддержку CPU, BIOS, тип RAM и питание проверьте по модели материнской платы."]
            if result.upgrade_id and result.bottleneck.value == "CPU" else
            ["Проверьте мощность и разъёмы БП, длину видеокарты и свободное место в корпусе."]
            if result.upgrade_id else []
        ),
        alternatives=alternatives,
        limiting_explanation=result.limiting_explanation,
        price_search_status=statuses,
        price_search_summary=upgrade_search_summary(statuses, prices, resale_quotes,
            payload.price_sources, search_started, {h.id: h.name for h in all_hw}) if payload.refresh_avito_prices else [],
        resale_price=resale_price,
        cash_budget=payload.budget or 0,
        net_upgrade_cost=max(0, result.avg_price-result.current_component_price) if result.avg_price and resale_status != 'unavailable' else None,
        upgrade_kind='platform' if chosen_platform else 'single' if result.upgrade_id else None,
        upgrade_parts=chosen_platform['parts'] if chosen_platform else [],
        platform_upgrade_note=platform_note,
        resale_status=resale_status,
        resale_notice=resale_notice,
    )

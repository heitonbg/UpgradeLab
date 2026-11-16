from app.services.steam_storage import with_requirements
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from app.api.deps import DBSession
from app.crud import hardware as hw_crud
from app.db.models import Hardware
from app.schemas.calculate import CalculateRequest, CalculateResponse
from app.services import calculator
from app.services.performance import fps_outlook, CS2_CPU_SOURCE
from app.services.fps_engine_v4 import comparable_pair_measurements
from app.services.prices import public_price
from app.services.upgrade_prices import upgrade_price_map, internal_resale_estimates, refresh_upgrade_prices, upgrade_search_summary
from app.services.upgrade_platforms import platform_choices
from dataclasses import replace

router = APIRouter(prefix="/api", tags=["calculator"])

from app.services.builds import BuildRequest, assemble, desktop_gpu


@router.post("/assemble")
def post_assemble(payload: BuildRequest, db: DBSession):
    return assemble(payload, db)


@router.post("/calculate", response_model=CalculateResponse)
def post_calculate(payload: CalculateRequest, db: DBSession):
    from app.services.offer_geography import offer_scope
    from app.services.internal_offers import sync_internal
    if sync_internal(db):db.commit()
    with offer_scope(payload):
        return _post_calculate(payload,db)


@with_requirements
def _post_calculate(payload: CalculateRequest, db: DBSession):
    if payload.selected_upgrade_id and payload.selected_platform:
        raise HTTPException(422, 'Выберите один вариант: замену детали или смену платформы.')
    cpu = hw_crud.get_by_id(db, payload.cpu_id)
    gpu = hw_crud.get_by_id(db, payload.gpu_id)

    if cpu is None or cpu.type != "CPU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CPU не найдена")
    if gpu is None or gpu.type != "GPU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "GPU не найдена")

    if cpu.raw_score<=0 or gpu.raw_score<=0:
        raise HTTPException(400,'Недостаточно достоверных аппаратных показателей для оценки FPS.')

    ram_type, ram_channels = None, None
    ram_capacity_gb = None
    if payload.ram_id:
        ram = db.get(Hardware, payload.ram_id)
        if not ram or ram.type != 'RAM':
            raise HTTPException(status.HTTP_400_BAD_REQUEST, 'RAM не найдена')
        ram_type, ram_channels = ram.ram_type, ram.ram_channels
        ram_capacity_gb = ram.ram_capacity_gb
    elif payload.ram_manual:
        ram_type, ram_channels = payload.ram_manual.type, payload.ram_manual.channels
        ram_capacity_gb = payload.ram_manual.capacity_gb

    # The current optimizer has calibrated recommendation logic only for its
    # legacy profiles. Let every catalog game reach the API, but abstain from
    # upgrades when that title has no defensible workload model.
    from app.core.constants import GAME_PROFILES
    from app.services.adaptive_fps import predict_adaptive_fps, compare_adaptive_results
    if payload.game not in GAME_PROFILES:
        resolution, preset = payload.mode.value.rsplit('_', 1)
        if resolution == '4k':
            resolution = '4K'
        cpu_catalog = list(db.scalars(select(Hardware).where(Hardware.type == "CPU", Hardware.raw_score > 0)))
        gpu_catalog = list(db.scalars(select(Hardware).where(Hardware.type == "GPU", Hardware.raw_score > 0)))
        adaptive_settings = {"resolution": resolution, "preset": preset,
                             "ram_type": ram_type, "ram_channels": ram_channels,
                             "ram_capacity_gb": ram_capacity_gb}
        current_adaptive = predict_adaptive_fps(cpu, gpu, payload.game, adaptive_settings, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
        evidence = current_adaptive["technical_details"]
        after_adaptive = None
        after_evidence = None
        candidate = None
        if payload.selected_upgrade_id:
            candidate = db.get(Hardware, payload.selected_upgrade_id)
            if candidate is None or candidate.type not in {"CPU", "GPU"}:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Вариант апгрейда не найден")
            if candidate.type == 'CPU' and (not cpu.socket or candidate.socket != cpu.socket):
                raise HTTPException(400, 'Для другого сокета выберите полный комплект смены платформы.')
            next_cpu = candidate if candidate.type == "CPU" else cpu
            next_gpu = candidate if candidate.type == "GPU" else gpu
            after_adaptive = predict_adaptive_fps(next_cpu, next_gpu, payload.game,
                                                  adaptive_settings, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
            after_evidence = after_adaptive["technical_details"]
        universal_options = []
        quotes = upgrade_price_map(db, payload.price_sources)
        if candidate is None and current_adaptive.get("average_fps") is not None:
            # CPU replacement stays on the current platform; unknown sockets cannot be assumed compatible.
            eligible = [h for h in [*cpu_catalog, *gpu_catalog]
                        if h.id not in (cpu.id, gpu.id) and (
                            h.type == "GPU" and desktop_gpu(h.name) and h.raw_score > gpu.raw_score or
                            h.type == "CPU" and cpu.socket and h.socket == cpu.socket
                            and h.raw_score > cpu.raw_score)]
            eligible = sorted(eligible, key=lambda h: (
                0 if h.id in quotes else 1, h.raw_score, h.id))[:40]
            scored = []
            for h in eligible:
                quote = quotes.get(h.id)
                if quote and payload.budget is not None and quote.price_rub > payload.budget:
                    continue
                predicted = predict_adaptive_fps(h if h.type == "CPU" else cpu,
                    h if h.type == "GPU" else gpu, payload.game, adaptive_settings,
                    cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
                value = predicted.get("average_fps")
                if value is None or not calculator.meaningful_upgrade(current_adaptive["average_fps"], value):
                    continue
                scored.append((h, predicted, quote))
            scored.sort(key=lambda item: (item[1]["average_fps"] >= payload.target_fps,
                item[2] is not None, item[1]["average_fps"]), reverse=True)
            for h, predicted, quote in scored[:3]:
                universal_options.append({"id": h.id, "name": h.name, "type": h.type,
                    "fps": round(predicted["average_fps"]),
                    "gain_fps": round(predicted["average_fps"] - current_adaptive["average_fps"], 2),
                    "avg_price": quote.price_rub if quote else None,
                    "within_budget": bool(quote and (payload.budget is None or quote.price_rub <= payload.budget)),
                    "upgrade_price": public_price(quote), "component": h.type, "fps_result": {"current": current_adaptive, "after": predicted,
                        **compare_adaptive_results(current_adaptive, predicted)}})
            if scored:
                candidate, after_adaptive, selected_quote = scored[0]
                after_evidence = after_adaptive["technical_details"]
        # Platform proceeds are available only when selling the old CPU/board/RAM,
        # never to a single-component replacement which still needs those parts.
        platform_sale = payload.expected_platform_sale_price or 0
        platform_budget = (payload.budget or 0) + platform_sale
        platforms = []
        chosen_platform = None
        if current_adaptive.get("average_fps") is not None:
            platforms = platform_choices(payload, db, cpu_catalog + gpu_catalog, quotes, cpu, gpu,
                current_adaptive["average_fps"], platform_budget,
                predictor=lambda new_cpu: predict_adaptive_fps(new_cpu, gpu, payload.game,
                    adaptive_settings, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog))
            for option in platforms:
                option["fps_result"] = {"current": current_adaptive, "after": option["prediction"],
                    **compare_adaptive_results(current_adaptive, option["prediction"])}
            universal_options.extend(platforms)
            if platforms and len(universal_options) > 3:
                universal_options = universal_options[:2] + [platforms[0]]
            if platforms and len(universal_options) > 3:
                universal_options = universal_options[:2] + [platforms[0]]
            if payload.selected_platform:
                chosen_platform = next((item for item in platforms if item["selection_allowed"]), None)
                if chosen_platform is None:
                    raise HTTPException(400, "Комплект платформы недоступен, несовместим или превышает бюджет. Повторите расчёт.")
                candidate = db.get(Hardware, chosen_platform["id"])
                after_adaptive = chosen_platform["fps_result"]["after"]
                after_evidence = after_adaptive["technical_details"]
        comparison = compare_adaptive_results(current_adaptive, after_adaptive)
        fps_value = current_adaptive.get('average_fps')
        after_fps_value = (after_adaptive or {}).get('average_fps')
        comparable_system = comparison.get('gain_type') is not None
        system_gain = comparison.get('gain_fps')
        gpu_oriented_fps = current_adaptive.get('gpu_oriented_fps')
        gpu_oriented_gain = comparison.get('gpu_oriented_gain_fps')
        def requirement_index(item):
            adequacy = item.get('cpu_adequacy') or {}
            comparison = adequacy.get('recommended') or adequacy.get('minimum') or {}
            return comparison.get('index_vs_reference_percent')
        cpu_adequacy_change = None
        if after_evidence and payload.selected_upgrade_id and candidate.type == "CPU":
            before_index = requirement_index(evidence)
            after_index = requirement_index(after_evidence)
            if before_index is not None and after_index is not None:
                cpu_adequacy_change = {"before_index": before_index, "after_index": after_index,
                                       "change_points": round(after_index - before_index, 1)}
        if gpu_oriented_fps is not None and fps_value is None:
            recommendation = ('Есть только приблизительная оценка видеокарты для 1080p High. Это не FPS всей системы; '
                              'CPU может ограничить результат. Подбор апгрейда и прирост не рассчитаны.')
            compatibility_note = ('Внешний GPU-ориентир: около %s FPS для 1080p High; полный FPS и CPU-ограничение неизвестны.'
                                  % gpu_oriented_fps)
        elif fps_value is not None:
            recommendation = 'Для этой игры найдена опора FPS, но алгоритм апгрейда не калиброван для неё; автоматическую замену не предлагаю.'
            compatibility_note = 'Доступна опора FPS; автоматический подбор апгрейда для этой игры не калиброван.'
        else:
            recommendation = 'Для этой игры пока нет игровой опоры. FPS всей системы и узкое место не рассчитаны; каталог PassMark сам по себе игровой FPS не определяет.'
            compatibility_note = 'Для выбранной игры и настроек пока нет численной FPS-опоры; каталог PassMark сам по себе игровой FPS не определяет.'
        if fps_value is not None:
            recommendation = ("Расчёт выполнен. Сравните FPS текущей системы и выбранного апгрейда."
                              if candidate else "Расчёт выполнен. Подходящая замена с приростом FPS не найдена.")
            compatibility_note = ("Для замены CPU сохранён сокет текущей платформы; поддержку BIOS проверьте отдельно."
                                  if candidate and candidate.type == "CPU" else
                                  "Для замены видеокарты проверьте питание и размеры корпуса.")
        return CalculateResponse(
            bottleneck=current_adaptive.get("limiting_component"),
            upgrade_id=candidate.id if candidate else None,
            upgrade_name=candidate.name if candidate else None,
            current_fps=round(fps_value) if fps_value is not None else None,
            upgraded_fps=round(after_fps_value) if comparable_system and after_fps_value is not None else None,
            recommendation=recommendation,
            upgrade_price={"avg_price":chosen_platform["price"],"price_origin":"platform_total","price_source":"Сумма комплектующих"} if chosen_platform else public_price(quotes.get(candidate.id)) if candidate else None,
            avg_price=chosen_platform["price"] if chosen_platform else quotes[candidate.id].price_rub if candidate and candidate.id in quotes else 0,
            upgrade_kind="platform" if chosen_platform else "single" if candidate else None,
            upgrade_parts=chosen_platform["parts"] if chosen_platform else [],
            platform_upgrade_note="Комплект CPU, платы, RAM и кулера; видеокарта сохраняется. Выручка от комплекта учитывается только для смены платформы.",
            cash_budget=payload.budget or 0,
            total_budget=platform_budget if chosen_platform else (payload.budget or 0),
            current_component_price=platform_sale if chosen_platform else 0,
            mode=payload.sell_mode,
            within_budget=bool(chosen_platform and chosen_platform['selection_allowed']) or bool(candidate and not chosen_platform and candidate.id in quotes
                               and public_price(quotes[candidate.id]).get("is_purchase_quote")
                               and (payload.budget is None or quotes[candidate.id].price_rub <= payload.budget)),
            is_maxed_out=False,
            target_fps=payload.target_fps,
            target_reached=(after_fps_value >= payload.target_fps) if comparable_system and after_fps_value is not None else None,
            fps_result={'current': current_adaptive, 'after': after_adaptive, **comparison},
            fps_v4_evidence={'current': evidence, 'after': after_evidence, 'gain_fps': system_gain,
                             'gpu_oriented_gain_fps': gpu_oriented_gain,
                             'cpu_adequacy_change': cpu_adequacy_change,
                             'note': 'Апгрейд не ранжируется без калиброванной нагрузки. GPU-ориентированная разница не является FPS всей системы; CPU Adequacy — ориентир требований, не прогноз игрового прироста.'},
            compatibility_notes=[compatibility_note],
            alternatives=universal_options,
        )

    # Получаем все CPU и GPU для поиска апгрейда в рамках бюджета
    all_hw = [h for h in db.scalars(select(Hardware)) if h.type not in ("CPU","GPU") or h.raw_score>0]
    cpu_catalog = [h for h in all_hw if h.type == "CPU" and h.raw_score > 0]
    gpu_catalog = [h for h in all_hw if h.type == "GPU" and h.raw_score > 0]
    from app.core.price_time import db_now
    search_started = db_now()
    statuses = []
    if payload.refresh_avito_prices:
        import time
        from app.services.offers import search_offers
        single_offer_fallback = False
        statuses = refresh_upgrade_prices(
            db, all_hw, cpu, gpu, time.monotonic() + 45, search_offers,
            payload.price_sources, payload.game, payload.mode, resale_fallback=single_offer_fallback,
            target_fps=payload.target_fps, ram_type=ram_type, ram_channels=ram_channels, focus_id=payload.price_lookup_id)
    prices = upgrade_price_map(db, payload.price_sources)
    market_resale_quotes = internal_resale_estimates(db)
    resale_quotes = market_resale_quotes if payload.sell_mode == 'budget_plus_sell' else {}
    def sale_value(hardware_id):
        if payload.sell_mode != 'budget_plus_sell':
            return 0
        if payload.expected_sale_price is not None:
            return payload.expected_sale_price
        return resale_quotes[hardware_id].price_rub if hardware_id in resale_quotes else 0
    all_cpus = [
        {"id": h.id, "name": h.name, "raw_score": h.raw_score, "avg_price": prices[h.id].price_rub if h.id in prices else None,
         "price_is_reference": h.id in prices and getattr(prices[h.id], 'reference_only', False), "socket": h.socket}
        for h in all_hw if h.type == "CPU" and h.raw_score>0 and not h.name.casefold().startswith('apple m')
    ]
    all_gpus = [
        {"id": h.id, "name": h.name, "raw_score": h.raw_score, "avg_price": prices[h.id].price_rub if h.id in prices else None,
         "price_is_reference": h.id in prices and getattr(prices[h.id], 'reference_only', False), "vram": h.vram}
        for h in all_hw if h.type == "GPU" and h.raw_score>0
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
        resale_notice = (f'Для {resale_hardware.name} пока нет трёх свежих объявлений той же модели на бирже UpgradeLab. '
                         f'{payload.budget or 0:,} ₽ — ваши деньги; выручка от продажи пока неизвестна. '
                         'Укажите свою ожидаемую цену продажи в форме, если хотите учесть её в бюджете.')
        result = replace(result, recommendation=result.recommendation.replace(
            'после учёта продажи доступно', 'без оценки продажи доступно'))

    platforms, chosen_platform, platform_note = [], None, None
    legacy = cpu.socket not in ('AM4', 'AM5', 'LGA1200', 'LGA1700')
    if result.bottleneck.value == 'CPU' or payload.selected_platform:
        platform_budget = (payload.budget or 0) + (payload.expected_platform_sale_price or 0) if payload.expected_platform_sale_price is not None else result.total_budget
        platforms = platform_choices(payload, db, all_hw, prices, cpu, gpu, result.current_fps, platform_budget)
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
                             'Видеокарта остаётся. Ожидаемую выручку за старые CPU, плату и RAM можно указать отдельно; она действует только для смены платформы.')
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
        if payload.expected_platform_sale_price is not None:
            result = replace(result, total_budget=platform_budget, current_component_price=payload.expected_platform_sale_price)
            resale_status = 'manual'
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

    # Keep the proven legacy estimate as production baseline. The measured-data
    # candidate is an additional evidence panel and abstains outside its coverage.
    from app.services.benchmark_model_v2 import predict_pair
    resolution, preset = payload.mode.value.rsplit('_', 1)
    if resolution == '4k':
        resolution = '4K'
    fps_v2_evidence = predict_pair(cpu.name, gpu.name, payload.game.value,
        resolution, preset, ram_type=ram_type, ram_channels=ram_channels,
        ram_capacity_gb=ram_capacity_gb)

    # v3 remains available as an abstaining diagnostic until workload anchors are calibrated.
    from app.services.adaptive_fps import predict_adaptive_fps, compare_adaptive_results
    current_v3 = {'average_fps': None, 'cpu_frame_time_ms': None, 'gpu_frame_time_ms': None,
        'bottleneck': None, 'method': 'abstain', 'model_version': '3.0',
        'confidence': 'insufficient_data',
        'missing_data': ['No calibrated per-game CPU/GPU workload anchors.']}
    adaptive_settings = {"resolution": resolution, "preset": preset,
                         "ram_type": ram_type, "ram_channels": ram_channels,
                         "ram_capacity_gb": ram_capacity_gb}
    current_adaptive = predict_adaptive_fps(cpu, gpu, payload.game.value,
                                            adaptive_settings, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
    current_v4 = current_adaptive["technical_details"]
    after_adaptive = None
    after_v4 = None
    after_v3 = None
    delta_percent = gain_per_ruble = None
    replacement = db.get(Hardware, result.upgrade_id) if result.upgrade_id else None
    if replacement and chosen_platform:
        next_cpu, next_gpu = replacement, gpu
        platform_fps_settings = {**adaptive_settings,
            "ram_type": chosen_platform.get("ram_type", ram_type),
            "ram_channels": 2,
            "ram_capacity_gb": chosen_platform.get("ram_capacity_gb", ram_capacity_gb)}
        after_adaptive = predict_adaptive_fps(next_cpu, next_gpu, payload.game.value,
                                              platform_fps_settings, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
        after_v4 = after_adaptive["technical_details"]
    elif replacement:
        next_cpu = replacement if result.bottleneck.value == 'CPU' else cpu
        next_gpu = replacement if result.bottleneck.value == 'GPU' else gpu
        after_adaptive = predict_adaptive_fps(next_cpu, next_gpu, payload.game.value,
                                              adaptive_settings, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
        after_v4 = after_adaptive["technical_details"]
        after_v3 = {'average_fps': None, 'cpu_frame_time_ms': None, 'gpu_frame_time_ms': None,
            'bottleneck': None, 'method': 'abstain', 'model_version': '3.0',
            'confidence': 'insufficient_data',
            'missing_data': ['No calibrated per-game CPU/GPU workload anchors.']}
    delta_percent = gain_per_ruble = None
    fps_v3_evidence = {'current': current_v3, 'after': after_v3,
        'gain_percent': None, 'gain_fps_per_ruble': None,
        'method': 'abstain', 'confidence': 'insufficient_data',
        'note': 'FPS Engine v3 has no calibrated game-specific CPU/GPU workload anchors; component frame times and upgrade gain are unavailable.'}
    adaptive_comparison = compare_adaptive_results(current_adaptive, after_adaptive)
    gpu_oriented_gain = adaptive_comparison.get('gpu_oriented_gain_fps')
    adequacy_before = current_v4.get('cpu_adequacy') or {}
    adequacy_after = (after_v4 or {}).get('cpu_adequacy') or {}
    def adequacy_index(item):
        comparison = item.get('recommended') or item.get('minimum') or {}
        return comparison.get('index_vs_reference_percent')
    before_index, after_index = adequacy_index(adequacy_before), adequacy_index(adequacy_after)
    fps_v4_evidence = {'current': current_v4, 'after': after_v4,
        'gain_fps': (round(after_v4['average_fps'] - current_v4['average_fps'], 2)
                     if comparable_pair_measurements(current_v4, after_v4)
                     and current_v4.get('average_fps') is not None and after_v4.get('average_fps') is not None else None),
        'gpu_oriented_gain_fps': gpu_oriented_gain,
        'cpu_adequacy_change': ({'before_index': before_index, 'after_index': after_index,
                                 'change_points': round(after_index - before_index, 1)}
                                if before_index is not None and after_index is not None
                                and replacement is not None and replacement.type == 'CPU' else None),
        'note': 'Единый v4 использует точные измерения, если они есть. GPU-ориентированный прирост не является FPS всей системы; CPU Adequacy — ориентир требований по суммарному PassMark CPU Mark, не FPS.'}

    def attach_adaptive_result(item):
        candidate_row = db.get(Hardware, item.get('id')) if item.get('id') else None
        if candidate_row is None or candidate_row.type not in {'CPU', 'GPU'}:
            return
        next_cpu = candidate_row if candidate_row.type == 'CPU' else cpu
        next_gpu = candidate_row if candidate_row.type == 'GPU' else gpu
        candidate_settings = adaptive_settings
        if item.get('kind') == 'platform':
            candidate_settings = {**adaptive_settings,
                "ram_type": item.get('ram_type', ram_type),
                "ram_channels": 2,
                "ram_capacity_gb": item.get('ram_capacity_gb', ram_capacity_gb)}
        after_result = predict_adaptive_fps(next_cpu, next_gpu, payload.game.value,
                                            candidate_settings, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
        comparison = compare_adaptive_results(current_adaptive, after_result)
        item['fps_result'] = {'current': current_adaptive, 'after': after_result, **comparison}
        if after_result.get('average_fps') is not None:
            item['fps'] = round(after_result['average_fps'])
            if comparison.get('gain_fps') is not None:
                item['gain'] = round(comparison['gain_fps'])

    alternatives = []
    for variant in result.alternatives:
        if legacy and not variant.get('price'):
            continue
        item = dict(variant)
        item.update(kind='single', key=f"single:{item['id']}")
        item['price_quote'] = public_price(prices.get(item['id']))
        item['fps_outlook'] = outlook(item['fps'], item['name'] if item['component'] == 'GPU' else gpu.name)
        attach_adaptive_result(item)
        alternatives.append(item)
    for item in platforms:
        item['resale_value'] = result.current_component_price
        item['net_cost'] = max(0, item['price']-result.current_component_price)
        item['price_quote'] = {'avg_price': item['price'], 'price_source': 'Сумма комплектующих', 'price_origin': 'platform_total'}
        item['fps_outlook'] = outlook(item['fps'], gpu.name)
        attach_adaptive_result(item)
    if platforms:
        combined = [*platforms, *alternatives] if chosen_platform or legacy else [*alternatives, *platforms]
        if chosen_platform:
            combined.sort(key=lambda item: item['key'] != chosen_platform['key'])
        alternatives = combined[:3]
        if not chosen_platform and platforms and not any(item.get('kind') == 'platform' for item in alternatives):
            alternatives = alternatives[:2] + [platforms[0]]
        if not chosen_platform and platforms and not any(item.get('kind') == 'platform' for item in alternatives):
            alternatives = alternatives[:2] + [platforms[0]]
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
    else:
        resale_price = public_price(market_resale_quotes.get(resale_hardware.id))
        if resale_price.get('avg_price') is None:
            resale_price = None
    
    return CalculateResponse(
        bottleneck=result.bottleneck,
        current_fps=(round(current_adaptive['average_fps'])
                     if current_adaptive.get('average_fps') is not None else None),
        upgraded_fps=(round(after_adaptive['average_fps'])
                      if after_adaptive and after_adaptive.get('average_fps') is not None
                      else None),
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
        fps_v2_evidence=fps_v2_evidence,
        fps_v3_evidence=fps_v3_evidence,
        fps_v4_evidence=fps_v4_evidence,
        fps_result={'current': current_adaptive, 'after': after_adaptive, **adaptive_comparison},
        target_reached=(after_adaptive.get('average_fps') >= payload.target_fps
                        if after_adaptive and after_adaptive.get('average_fps') is not None else None),
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

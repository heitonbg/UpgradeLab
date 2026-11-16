from app.services.steam_storage import with_requirements
from app.services.selection_cache import selection_scope
"""Budgeted CPU/GPU selection with explicitly priced supporting parts."""
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from app.db.models import Hardware
from app.schemas.calculate import GameName, CalcMode
from app.services.prices import price_map, public_price
from app.schemas.offers import Source, LABELS, SearchOffers
from app.db.models import StoreOffer
from app.services.offers import available_offers, fresh, public_offer, search_offers
from app.services.gaming_selection import gaming_options
from app.services.performance import estimate_fps, fps_outlook
from app.services.component_quality import QUALITY_SEARCHES, quality_check, invalid_manual_part
from app.services.storage_compatibility import nvme_board_evidence
import re
import json

SOCKET_MEMORY = {"AM4": {"DDR4"}, "AM5": {"DDR5"}, "LGA1151": {"DDR4"},
                 "LGA1200": {"DDR4"}, "LGA1700": {"DDR4", "DDR5"}}


def board_socket(title):
    title = title.upper()
    explicit = re.search(r"\b(?:AM[45]|LGA\s*(?:1151|1200|1700))\b", title)
    if explicit:
        return explicit.group().replace(" ", "")
    chipsets = {
        "AM4": r"(?:A320|A520|B350|B450|B550|X370|X470|X570)",
        "AM5": r"(?:A620|B650|B840|B850|X670|X870)",
        "LGA1151": r"(?:H110|H170|H270|H310|H370|B150|B250|B360|B365|Z170|Z270|Z370|Z390)",
        "LGA1200": r"(?:H410|H470|H510|H570|B460|B560|Z490|Z590)",
        "LGA1700": r"(?:H610|H670|H770|B660|B760|Z690|Z790)",
    }
    return next((socket for socket, pattern in chipsets.items()
                 if re.search(r"\b" + pattern + r"(?:M|I|E)?\b", title)), None)


def desktop_gpu(name):
    return not re.search(r"laptop|mobile|notebook|max-q|quadro|tesla|radeon\s+pro|rtx\s+(?:a\d|pro)|\b(?:GTX|RTX)\s*\d+M\b", name, re.I)


class Part(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    price: int = Field(ge=0, le=10000000)
    offer_id: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def nonempty(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Укажите модель")
        return value.strip()


from app.schemas.geography import GeoQuery

class BuildRequest(GeoQuery):
    scenario: Literal["build"]
    budget: int = Field(gt=0, le=10000000)
    target_fps: int = Field(default=60, ge=1, le=1000)
    game: GameName | str
    mode: CalcMode

    @field_validator('game', mode='before')
    @classmethod
    def normalize_known_game(cls, value):
        if isinstance(value, GameName):
            return value
        try:
            return GameName(str(value).strip())
        except ValueError:
            return str(value).strip()
    socket: Literal["AUTO", "AM4", "AM5", "LGA1151", "LGA1200", "LGA1700"]
    ram_type: Literal["AUTO", "DDR4", "DDR5"]
    ram_capacity_gb: int = Field(ge=8, le=512)
    price_sources: list[Source] | None = Field(default=None, min_length=1, max_length=13)
    pricing_mode: Literal["offers", "reference", "hybrid"] | None = None
    condition: Literal["any", "new", "used"] = "any"
    workload: Literal["gaming", "cpu_work"] = "gaming"
    objective: Literal["balanced", "performance", "economy"] = "balanced"
    selection_policy: Literal['hardware_proxy','target_fps'] = 'hardware_proxy'
    include_stretch: bool = True
    auto_parts: bool = False
    allow_store_fallback: bool = True
    allow_platform_change: bool = True
    case_style: Literal["gaming", "minimal", "budget"] = "gaming"
    selected_cpu_id: int | None = Field(default=None, gt=0)
    selected_gpu_id: int | None = Field(default=None, gt=0)
    selected_case_offer_id: int | None = Field(default=None, gt=0)
    motherboard: Part | None = None
    memory: Part | None = None
    storage: Part | None = None
    psu: Part | None = None
    case: Part | None = None
    cooler: Part | None = None



def nondominated_options(options,score):
    """Price/declared-objective frontier within already compatible full PCs."""
    frontier=[];best=None
    for option in sorted(options,key=lambda o:(o[2],-score(o),o[0].id,o[1].id)):
        value=score(option)
        if best is None or value>best:
            frontier.append(option);best=value
    return frontier


def build_options(options, target_fps, game=None, mode=None, workload="gaming", objective="balanced", hardware_score=None, hardware_rank=None):
    """Up to three distinct, actually priced CPU/GPU pairs from one search."""
    if workload=='cpu_work' or objective!='balanced' or hardware_score is not None:
        score=lambda o:o[0].raw_score if workload=='cpu_work' else (hardware_score(o) if hardware_score else o[3])
        if hardware_rank is None:
            options=nondominated_options(options,score)
        ranked=(sorted(options,key=hardware_rank,reverse=True) if hardware_rank is not None else
                sorted(options,key=lambda o:(score(o),-o[2],-o[0].id,-o[1].id),reverse=True))
        if objective=='economy':
            if hardware_score is not None:
                # Uncalibrated FPS estimates cannot certify an auto-build goal.
                first=min(options,key=lambda o:(o[2],-score(o)))
            else:
                eligible=[o for o in options if workload=='cpu_work' or fps_outlook(o[3],o[1].name,game,mode)['minimum']>=target_fps]
                first=min(eligible or options,key=lambda o:(o[2],-score(o)))
        elif workload=='cpu_work' and objective=='balanced':
            first=max(options,key=lambda o:(score(o)/max(1,o[2]),score(o),-o[2]))
        elif objective=='balanced':
            first=max(options,key=hardware_rank) if hardware_rank else max(options,key=lambda o:(score(o)/max(1,o[2]),score(o),-o[2]))
        elif hardware_rank is not None:
            first=max(options,key=hardware_rank)
        else:first=ranked[0]
        candidates=[first,*ranked,min(options,key=lambda o:(o[2],-score(o)))]
        result=[];seen=set()
        for option in candidates:
            identity=(option[0].id,option[1].id)
            if identity in seen:continue
            seen.add(identity);index=len(result)
            result.append((['recommended','performance','value'][index],['Рекомендуемая','Производительность','Другая конфигурация'][index],
                           'Рабочий CPU-профиль по CPU Mark; скорость приложений не измерена.' if workload=='cpu_work' else 'Ранжирование по аппаратному proxy score, не по измеренному FPS.',option))
            if len(result)==3:break
        return result
    options = gaming_options(options)
    reached = [option for option in options if (fps_outlook(option[3], option[1].name, game, mode)['minimum']
               if game is not None else option[3]) >= target_fps]
    recommended = (min(reached, key=lambda o: (o[2], -o[3], o[0].id, o[1].id)) if reached
                   else max(options, key=lambda o: (o[3], -o[2], -o[0].id, -o[1].id)))
    chosen = [("recommended", "Рекомендуемая", "Игровая конфигурация с запасом по оценочному диапазону FPS." if reached else "Игровая конфигурация с лучшим доступным прогнозом FPS; достижение цели не гарантировано.", recommended)]
    remaining = [o for o in options if (o[0].id, o[1].id) != (recommended[0].id, recommended[1].id)]
    if remaining:
        performance = max(remaining, key=lambda o: (o[3], -o[2], -o[0].id, -o[1].id))
        remaining = [o for o in remaining if (o[0].id, o[1].id) != (performance[0].id, performance[1].id)]
        if remaining:
            value = max(remaining, key=lambda o: (o[3] / max(1, o[2]), o[3], -o[2], -o[0].id, -o[1].id))
            chosen.append(("value", "Цена и производительность", "Альтернативная пара с высоким FPS на рубль среди оставшихся вариантов.", value))
        chosen.append(("performance", "Больше FPS" if performance[3] > recommended[3] else "Другая конфигурация",
                       "Максимальный прогноз FPS среди остальных доступных пар.", performance))
    return chosen


@selection_scope
@with_requirements
def assemble(payload: BuildRequest, db):
    from app.services.offer_geography import offer_scope,financial_evidence
    from app.services.internal_offers import sync_internal
    if sync_internal(db):db.commit()
    from app.services.planning_prices import price_mode_scope
    with offer_scope(payload),price_mode_scope(payload.pricing_mode):
        result=financial_evidence(_assemble(payload,db),db,payload)
        from app.services.adaptive_fps import predict_adaptive_fps
        from app.services.fps_engine_v4 import relative_pair_proxy
        hardware_rows = list(db.scalars(select(Hardware)).all())
        cpu_catalog = [row for row in hardware_rows if row.type == 'CPU' and row.raw_score > 0]
        gpu_catalog = [row for row in hardware_rows if row.type == 'GPU' and row.raw_score > 0]
        cpu_scores = [row.raw_score for row in cpu_catalog]
        gpu_scores = [row.raw_score for row in hardware_rows if row.type == 'GPU' and row.raw_score > 0]
        for variant in [result,*result.get('alternatives',[])]:
            cpu_part = next((part for part in variant.get('parts',[]) if part.get('type') == 'CPU'), None)
            gpu_part = next((part for part in variant.get('parts',[]) if part.get('type') == 'GPU'), None)
            cpu = db.get(Hardware, cpu_part.get('id')) if cpu_part and cpu_part.get('id') else None
            gpu = db.get(Hardware, gpu_part.get('id')) if gpu_part and gpu_part.get('id') else None
            if cpu is not None and gpu is not None:
                game_name = payload.game.value if hasattr(payload.game, 'value') else str(payload.game)
                resolution, preset = payload.mode.value.rsplit('_', 1)
                if resolution == '4k': resolution = '4K'
                if payload.workload == 'gaming':
                    memory_info = variant.get('memory_configuration') or {}
                    actual_config = variant.get('actual_config') or {}
                    ram_type = memory_info.get('ram_type') or actual_config.get('ram_type') or payload.ram_type
                    ram_modules = memory_info.get('modules')
                    fps_result = predict_adaptive_fps(
                        cpu, gpu, game_name,
                        {"resolution": resolution, "preset": preset,
                         "ram_type": ram_type,
                         "ram_channels": 2 if ram_modules is None or ram_modules >= 2 else 1,
                         "ram_capacity_gb": memory_info.get('capacity_gb')
                            or actual_config.get('ram_capacity_gb') or payload.ram_capacity_gb},
                        cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog,
                    )
                    fps_result['relative_hardware'] = relative_pair_proxy(
                        cpu.raw_score, gpu.raw_score, cpu_scores, gpu_scores)
                    variant['fps_result'] = fps_result
                    variant['fps'] = (round(fps_result['average_fps'])
                                      if fps_result.get('average_fps') is not None else None)
                    variant['fps_outlook'] = None
                    average = fps_result.get('average_fps')
                    # A system forecast does not validate the complete
                    # selected build. Keep confirmation unset and expose the
                    # model-only comparison separately.
                    variant['target_reached_by_model'] = (average >= payload.target_fps
                                                          if average is not None else None)
                    if fps_result['result_type'] == 'measured_system_fps':
                        variant['recommendation'] = ('Сборка выбрана с учётом опубликованного теста этой связки CPU/GPU. '
                            'Результат относится к условиям источника и не является тестом собранного ПК.')
                    elif fps_result['result_type'] == 'estimated_system_fps':
                        variant['recommendation'] = ('FPS показан как расчётный прогноз по игровой модели. '
                            'Он не является замером; проверьте совместимость, цены и наличие перед покупкой.')
                    elif fps_result['result_type'] == 'gpu_reference_only':
                        variant['recommendation'] = ('Вариант ранжирован по аппаратным характеристикам. '
                            'Доступен только отдельный ориентир видеокарты, FPS всей системы не рассчитан.')
                    else:
                        variant['recommendation'] = ('Вариант ранжирован по аппаратным характеристикам. '
                            'Игровой FPS для этой конфигурации обоснованно не рассчитан.')
        for variant in [result,*result.get('alternatives',[])]:
            catalog_parts=False
            from app.db.models import StoreOffer
            from app.services.assembly_draft import quote_evidence
            for item in variant.get('parts',[]):
                row=db.get(StoreOffer,item['offer_id']) if item.get('offer_id') else None
                if row is not None and row.origin=='catalog_import':
                    item.update(quote_evidence(row));catalog_parts=True
            if catalog_parts:
                variant.update(purchase_ready=False,prices_confirmed=False)
                if variant.get('status')!='partial':variant['status']='draft'
            if any(p.get('price_basis')=='reference' for p in variant.get('parts',[])):
                variant['price_note']='Есть справочные цены из прошлых наблюдений; текущая стоимость, наличие и доставка этих позиций не подтверждены. '+variant.get('price_note','')
                variant.update(purchase_ready=False,prices_confirmed=False,status='draft')
        if payload.include_stretch and payload.auto_parts and payload.workload=='gaming' and payload.selection_policy=='target_fps' and (result.get('fps') or 0)<payload.target_fps:
            from app.services.assembly_draft import draft_build
            cap=min(10000000,round(payload.budget*1.5))
            stretch=draft_build(payload.model_copy(update={'budget':cap}),db)
            if stretch and stretch.get('fps',0)>=payload.target_fps and stretch['total_price']>payload.budget:
                variants=[{k:v for k,v in stretch.items() if k!='alternatives'}]
                for variant in variants:
                    variant.update(over_budget=True,budget_shortfall=variant['total_price']-payload.budget,
                        requested_budget=payload.budget,remaining_budget=payload.budget-variant['total_price'],
                        title='Целевой прогноз с увеличенным бюджетом',
                        summary='Отдельный вариант дороже вашего бюджета. FPS, цены и доступность требуют проверки.')
                result['stretch_alternatives']=variants
            result['stretch_search_budget_cap']=cap
        return result


def _assemble(payload: BuildRequest, db):
    from app.services.fps_engine_v4 import supported_profile, relative_hardware_index
    game_profile = supported_profile(payload.game)
    automatic_platform = (payload.auto_parts and payload.selection_policy == "target_fps"
                          and payload.socket == "AUTO")
    if not automatic_platform:
        if payload.ram_type == "AUTO":
            raise HTTPException(422, "Automatic memory type requires automatic gaming platform selection")
        if payload.ram_type not in SOCKET_MEMORY[payload.socket]:
            raise HTTPException(422, "Memory type is not compatible with the selected platform")
    parts = []
    selected_board = None
    # Refresh required categories automatically so a user does not have to
    # visit and search each marketplace before asking for a complete build.
    if payload.pricing_mode in ('reference','hybrid'):
        if not payload.auto_parts:raise HTTPException(422,'Справочный и гибридный режимы требуют автоматического подбора.')
        from app.services.planning_prices import planning_build
        return planning_build(payload,db)
    if payload.auto_parts:
        from app.services.assembly_search import assemble_resilient
        return assemble_resilient(payload, db, search_offers)
    for key in ("motherboard", "memory", "storage", "psu", "case", "cooler"):
        manual = getattr(payload, key)
        offer = None
        if manual and manual.offer_id:
            offer = db.get(StoreOffer, manual.offer_id)
            from app.services.offer_geography import filter_geography,costed
            if offer is not None:
                offer=costed(offer) if filter_geography([offer]) else None
            from app.services.catalog_access import filter_catalog
            if offer is not None and not filter_catalog(db, [offer]):
                offer = None
            if offer and json.loads(offer.attributes).get('optimizer_eligible') is False:
                raise HTTPException(400,'Недостаточно данных для проверки совместимости объявления')
            from app.services.catalog_freshness import observation_usable
            if not offer or not observation_usable(offer) or offer.category != key or (payload.price_sources is not None and offer.source not in payload.price_sources):
                raise HTTPException(400, "Выбранное предложение устарело или не соответствует категории/площадкам")
            from app.services.offer_safety import safe_offers
            if not safe_offers([offer], {}):
                raise HTTPException(400, 'Объявление описывает неисправную деталь, восстановление или другое неподходящее предложение.')
            attrs = json.loads(offer.attributes)
            if key in QUALITY_SEARCHES:
                evidence, reason = quality_check(offer, payload.socket)
                if evidence is None:
                    raise HTTPException(400, reason)
                if key == 'storage' and evidence.get('interface') == 'NVMe' and not nvme_board_evidence(selected_board):
                    raise HTTPException(400, 'Для этого NVMe SSD не подтверждён слот M.2 2280 PCIe на выбранной плате. Укажите характеристики платы или выберите SATA SSD.')
            if key == "motherboard" and ((attrs.get("socket") and attrs["socket"] != payload.socket) or
                                          (attrs.get("ram_type") and attrs["ram_type"] != payload.ram_type)):
                raise HTTPException(400, "Выбранная плата не подходит сокету или памяти")
            if key == "memory":
                from types import SimpleNamespace
                from app.services.automatic_builds import memory_configuration
                memory_info = memory_configuration(SimpleNamespace(
                    name=offer.name if offer else manual.name,
                    attributes=json.dumps(attrs if offer else {})))
                if (not memory_info or memory_info['ram_type'] != payload.ram_type
                        or memory_info['capacity_gb'] < payload.ram_capacity_gb
                        or memory_info['modules'] != 2):
                    raise HTTPException(400, "Для полной сборки выберите совместимый комплект RAM из двух модулей нужного объёма")
            if key == "cooler" and attrs.get("sockets") and payload.socket not in attrs["sockets"]:
                raise HTTPException(400, "Кулер не поддерживает сокет сборки")
        elif not manual:
            raise HTTPException(422, f"Укажите деталь {key} или включите автоматический подбор")
        elif invalid_manual_part(manual.name, key):
            raise HTTPException(422, "Для сборки нужны комплектные детали: внешние накопители, крепления и аксессуары не подходят.")
        if key == "motherboard":
            inferred_socket = board_socket(offer.name if offer else manual.name)
            if inferred_socket and inferred_socket != payload.socket:
                raise HTTPException(400, "Сокет платы из названия не соответствует выбранной платформе")
        if offer:
            if key == "motherboard":
                selected_board = offer
            public = public_offer(offer)
            quality = quality_check(offer, payload.socket)[0] if key in QUALITY_SEARCHES else None
            if quality and key == 'storage' and quality.get('interface') == 'NVMe':
                quality = {**quality, 'board_compatibility': nvme_board_evidence(selected_board)}
            parts.append({"type": key, "name": offer.name, "price": offer.price_rub, "offer_id": offer.id,
                          "price_source": LABELS[offer.source], "price_date": public["observed_at"],
                          "price_url": offer.url, "price_market": "used_ru" if offer.condition == "used" else "retail_ru",
                          **({"quality": quality} if quality else {})})
        else:
            parts.append({"type": key, **manual.model_dump(), "price_source": "Введено пользователем"})
    remaining = payload.budget - sum(part["price"] for part in parts)
    prices = price_map(db, payload.price_sources)
    hardware = list(db.scalars(select(Hardware)))
    cpu_catalog = [h for h in hardware if h.type == "CPU" and h.raw_score > 0]
    gpu_catalog = [h for h in hardware if h.type == "GPU" and h.raw_score > 0]
    cpus = [h for h in hardware if h.type == "CPU" and h.raw_score>0 and h.socket == payload.socket and h.id in prices]
    # The same socket can span incompatible CPU generations. Apply the
    # automatic solver's existing chipset rules to offers and manual titles.
    from app.services.automatic_builds import cpu_board_matches
    board = selected_board or payload.motherboard
    cpus = [h for h in cpus if cpu_board_matches(h, board)]
    gpus = [h for h in hardware if h.type == "GPU" and h.raw_score>0 and h.id in prices and desktop_gpu(h.name)]
    options = []
    for cpu in cpus:
        for gpu in gpus:
            cost = prices[cpu.id].price_rub + prices[gpu.id].price_rub
            if cost <= remaining:
                fps = (estimate_fps(cpu.raw_score, gpu.raw_score, gpu.name, game_profile, payload.mode, 1.0, cpu.name)
                       if game_profile is not None else None)
                options.append((cpu, gpu, cost, fps))
    options = [o for o in options if (payload.selected_cpu_id is None or o[0].id == payload.selected_cpu_id)
               and (payload.selected_gpu_id is None or o[1].id == payload.selected_gpu_id)]
    if options and payload.workload == 'gaming':
        # The existing legacy score already matches the adaptive legacy method.
        # Replace it with stronger published pair evidence where such a cohort
        # exists; don't scan benchmark rows for every CPU/GPU Cartesian pair.
        from app.services.benchmark_model_v2 import has_native_pair_measurement
        from app.services.adaptive_fps import predict_adaptive_fps
        resolution, preset = payload.mode.value.rsplit('_', 1)
        if resolution == '4k':
            resolution = '4K'
        game_name = payload.game.value if hasattr(payload.game, 'value') else str(payload.game)
        for index, option in enumerate(options):
            option_cpu, option_gpu = option[0], option[1]
            if game_profile is not None and not has_native_pair_measurement(option_cpu.name, option_gpu.name, game_name, preset):
                continue
            evidence = predict_adaptive_fps(option_cpu, option_gpu, game_name, {
                'resolution': resolution, 'preset': preset,
                'ram_type': payload.ram_type,
                'ram_channels': 2,
                'ram_capacity_gb': payload.ram_capacity_gb,
            }, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
            if (evidence.get('average_fps') is not None
                    and evidence.get('technical_details', {}).get('status')
                    in {'measured_reference', 'estimated_interpolation', 'universal_fallback_estimate'}):
                options[index] = (*option[:3], evidence['average_fps'], *option[4:])
    if not options:
        raise HTTPException(400, f"После подбора остальных деталей осталось {max(0, remaining):,} ₽ на CPU и GPU. Совместимая пара с доступными ценами не найдена. Увеличьте бюджет или смените платформу; требования к БП, SSD и комплектности охлаждения сохраняются.")
    if game_profile is None and payload.workload == 'gaming':
        cpu_scores = [row.raw_score for row in hardware if row.type == 'CPU' and row.raw_score > 0]
        gpu_scores = [row.raw_score for row in hardware if row.type == 'GPU' and row.raw_score > 0]
        def pair_rank(option):
            cpu_index = relative_hardware_index(option[0].raw_score, cpu_scores)['percentile']
            gpu_index = relative_hardware_index(option[1].raw_score, gpu_scores)['percentile']
            if cpu_index is None or gpu_index is None:
                return 0.0
            return (max(cpu_index, 0.1) * max(gpu_index, 0.1)) ** 0.5
        variants = build_options(options, payload.target_fps, None, None, payload.workload,
                                 payload.objective, hardware_score=lambda option: option[3])
    else:
        variants = build_options(options, payload.target_fps, payload.game, payload.mode, payload.workload, payload.objective)
    cpu, gpu, cost, fps = variants[0][3]
    selected = [{"type": h.type, "id": h.id, "name": h.name, "price": prices[h.id].price_rub,
                 **public_price(prices[h.id])} for h in (cpu, gpu)]
    total = payload.budget - remaining + cost
    result = {"scenario": "build", "parts": selected + parts, "total_price": total,
            "remaining_budget": payload.budget - total, "fps": fps,
            "fps_outlook": fps_outlook(fps, gpu.name, game_profile, payload.mode) if game_profile is not None else None,
            "target_reached": None,
            "recommendation": ("Подобрана игровая конфигурация по бюджету. FPS указан оценочным диапазоном; проверьте игровые тесты перед покупкой." if game_profile is not None else "Игра выбрана из каталога. FPS и узкое место не рассчитаны; CPU/GPU ранжированы по отдельным аппаратным процентилям."),
            "compatibility_notes": [
                f"CPU подобран под сокет {payload.socket}; платформа поддерживает {payload.ram_type}.",
                "Для расчёта принят двухканальный комплект памяти. Проверьте, что выбраны два модуля.",
                ("Детали найдены автоматическим поиском по выбранным магазинам. Сокет и память проверены по характеристикам или названию. Если магазин не опубликовал все параметры, совместимость корпуса, накопителя и кулера требует проверки в карточке товара. Поддержку CPU в BIOS проверьте отдельно."
                 if payload.auto_parts else "Остальные детали выбраны вручную или из предложений. При отсутствии характеристик совместимость не подтверждена; проверьте поддержку CPU в BIOS и тип RAM платы."),
                "Проверьте мощность и разъёмы БП, форм-фактор платы и корпуса, длину GPU, крепление и высоту кулера.",
                "FPS — модель по синтетическим баллам; совместимость конкретных моделей платы, БП и корпуса автоматически не подтверждена."]}
    alternatives = []
    for key, title, summary, (variant_cpu, variant_gpu, variant_cost, variant_fps) in variants:
        variant_total = payload.budget - remaining + variant_cost
        variant_parts = [{"type": h.type, "id": h.id, "name": h.name, "price": prices[h.id].price_rub,
                          **public_price(prices[h.id])} for h in (variant_cpu, variant_gpu)] + parts
        alternatives.append({**result, "variant_key": key, "title": title, "summary": summary,
                             "parts": variant_parts, "total_price": variant_total,
                             "remaining_budget": payload.budget - variant_total, "fps": variant_fps,
                             "fps_outlook": fps_outlook(variant_fps, variant_gpu.name, game_profile, payload.mode) if game_profile is not None else None,
                             "target_reached": None,
                             "recommendation": summary})
    return {**result, "alternatives": alternatives}

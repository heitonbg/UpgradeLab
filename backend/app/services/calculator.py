from dataclasses import dataclass, field
from app.core.constants import GAME_PROFILES
from app.schemas.calculate import AIOption, Bottleneck, CalcMode, GameName
from app.services.performance import cpu_capacity, gpu_capacity, estimate_fps, fps_outlook, cs2_cpu_basis


def meaningful_upgrade(current_fps, after_fps):
    """Do not recommend spending money for rounding noise or tiny sidegrades."""
    return after_fps-current_fps >= max(5, current_fps*.05)


@dataclass(frozen=True)
class CalculateResult:
    bottleneck: Bottleneck
    current_fps: int
    upgraded_fps: int
    recommendation: str
    avg_price: int
    within_budget: bool = False
    upgrade_component: str | None = None
    ai_warning: str | None = None
    current_component_price: int = 0
    total_budget: int = 0
    mode: str = "budget_only"
    is_maxed_out: bool = False
    upgrade_id: int | None = None
    upgrade_name: str | None = None
    alternatives: list[dict] = field(default_factory=list)
    limiting_explanation: str = ''


def calculate(
    *,
    cpu_raw: int,
    gpu_raw: int,
    game: GameName,
    mode: CalcMode,
    budget: int | None = None,
    cpu_price: int = 0,
    gpu_price: int = 0,
    cpu_socket: str | None = None,
    cpu_name: str = "",
    gpu_name: str = "",
    gpu_vram: int | None = None,
    ram_type: str | None = None,
    ram_channels: int | None = None,
    all_cpus: list[dict] | None = None,
    all_gpus: list[dict] | None = None,
    all_rams: list[dict] | None = None,
    ai_mode: AIOption = AIOption.OFF,
    sell_mode: str = "budget_only",
    target_fps: int = 60,
    selected_upgrade_id: int | None = None,
) -> CalculateResult:
    profile = GAME_PROFILES[game][mode]

    # 2.5. Учитываем влияние RAM на производительность
    ram_boost = 1.0
    if ram_type and ram_channels:
        if ram_channels == 2:
            ram_boost += 0.05  # Двухканальный режим даёт +5%
        if ram_type == "DDR5":
            ram_boost += 0.08  # DDR5 быстрее DDR4
            if ram_channels == 2:
                ram_boost += 0.03  # DDR5 + dual channel = ещё +3%
        elif ram_type == "DDR4":
            if ram_channels == 2:
                ram_boost += 0.02  # DDR4 dual даёт небольшой бонус
        elif ram_type == "DDR3":
            ram_boost -= 0.05  # DDR3 замедляет современные системы
    # CS2 CPU references already use dual-channel memory. Do not add a second
    # dual-channel/DDR5 bonus to their measured relative ranking.
    if game == GameName.CS2 and cpu_name:
        ram_boost = .93 if ram_channels == 1 else 1.0
    
    # Memory affects CPU throughput; it must not increase a GPU-limited result.
    cpu_cap = cpu_capacity(cpu_raw, cpu_name, game, mode, ram_boost)
    gpu_cap = gpu_capacity(gpu_raw, gpu_name, game, mode)
    bottleneck = Bottleneck.CPU if cpu_cap < gpu_cap else Bottleneck.GPU
    current_fps = estimate_fps(cpu_raw, gpu_raw, gpu_name, game, mode, ram_boost, cpu_name)
    cpu_gain = round((min(cpu_cap * 1.25, gpu_cap) - min(cpu_cap, gpu_cap)) * profile['overhead'])
    gpu_gain = round((min(cpu_cap, gpu_cap * 1.25) - min(cpu_cap, gpu_cap)) * profile['overhead'])
    close = max(cpu_cap, gpu_cap) / max(1, min(cpu_cap, gpu_cap)) < 1.15
    limiting_explanation = (('Возможности CPU и GPU близки: ограничение может меняться по сценам. ' if close else '') +
        f'По модели увеличение возможности CPU на 25% даст около +{cpu_gain} FPS, GPU — около +{gpu_gain} FPS. '
        'Это сравнение сценариев, а не измерение загрузки или оценка качества сборки.')

    # 2.6. Расчёт общего бюджета (продажа + бюджет)
    effective_budget = budget or 0
    current_component_price = 0
    total_budget = 0
    
    if sell_mode == "budget_plus_sell":
        # Определяем цену ограничивающего компонента
        if bottleneck is Bottleneck.CPU:
            current_component_price = cpu_price or 0
        else:
            current_component_price = gpu_price or 0
        total_budget = effective_budget + current_component_price
    else:
        total_budget = effective_budget

    compatible_cpus = [c for c in (all_cpus or []) if cpu_socket and "BGA" not in cpu_socket.upper()
                       and c.get("socket") == cpu_socket and cpu_capacity(c.get('raw_score', 0), c.get('name', ''), game, mode, ram_boost) > cpu_cap]
    from app.services.builds import desktop_gpu
    better_gpus = [g for g in (all_gpus or []) if desktop_gpu(g.get("name", "")) and
                   gpu_capacity(g.get('raw_score', 0), g.get('name', ''), game, mode) > gpu_cap]
    is_maxed_out = not compatible_cpus and not better_gpus
    upgraded_fps = current_fps

    # 4. Формируем умные рекомендации
    if is_maxed_out:
        rec = (
            f"Для игры {game.value} ({mode.value}) в текущем каталоге нет более быстрых "
            f"комплектующих, подходящих для этой сборки."
        )
    elif bottleneck is Bottleneck.CPU:
        rec = (
            f"По ориентировочной модели в режиме «{mode.value}» для игры {game.value} "
            "производительность ограничивает CPU. Проверьте игровые тесты и загрузку компонентов перед заменой."
        )
    else:
        rec = (
            f"По ориентировочной модели в режиме «{mode.value}» для игры {game.value} "
            "производительность ограничивает GPU. Сначала сравните игровые тесты и снижение графических настроек."
        )

    # 5. Проверка VRAM для нейросетей
    ai_warning = None
    if ai_mode != AIOption.OFF and gpu_vram is not None:
        if ai_mode is AIOption.HEAVY:
            # Training, большие LLM, ComfyUI с большими моделями
            if gpu_vram < 8:
                ai_warning = (
                    "Для тяжёлых ИИ-задач (training, большие LLM, ComfyUI) "
                    f"требуется минимум 8 ГБ VRAM. У вас {gpu_vram} ГБ — "
                    "ожидайте ошибки 'Out of memory' на моделях крупнее 3B параметров. "
                    "Рекомендуется GPU с 12+ ГБ."
                )
            elif gpu_vram < 12:
                ai_warning = (
                    "Для тяжёлых ИИ-задач ваш GPU с {vram} ГБ VRAM "
                    "может быть ограничен. Модели крупнее 7B параметров "
                    "не поместятся в память. Для Stable Diffusion XL и локальных LLM "
                    "рекомендуется 12+ ГБ."
                ).format(vram=gpu_vram)
            else:
                ai_warning = (
                    f"Ваш GPU с {gpu_vram} ГБ VRAM подходит для большинства "
                    "ИИ-задач: Stable Diffusion, локальные LLM до 13B параметров. "
                    "Для training и моделей крупнее 30B рекомендуется 24+ ГБ."
                )
        else:  # LIGHT
            if gpu_vram < 4:
                ai_warning = (
                    "Для работы с нейросетями (Stable Diffusion, локальные LLM) "
                    f"требуется минимум 4 ГБ VRAM. У вас {gpu_vram} ГБ — "
                    "будут ограничения по размеру моделей. "
                    "Рекомендуется GPU с 6+ ГБ VRAM."
                )
            elif gpu_vram < 6:
                ai_warning = (
                    f"Ваш GPU с {gpu_vram} ГБ VRAM — минимальный порог "
                    "для нейросетей. Stable Diffusion запустится, "
                    "но только с базовыми настройками и малым разрешением. "
                    "Для комфортной работы нужно 8+ ГБ."
                )
            elif gpu_vram < 8:
                ai_warning = (
                    f"Ваш GPU с {gpu_vram} ГБ VRAM подходит для лёгких ИИ-задач: "
                    "Stable Diffusion 1.5, малые LLM (до 3B). "
                    "Для SDXL и моделей крупнее — рекомендуется 8+ ГБ."
                )
            else:
                ai_warning = (
                    f"Ваш GPU с {gpu_vram} ГБ VRAM подходит для нейросетей: "
                    "Stable Diffusion 1.5 и XL, локальные LLM до 7B параметров."
                )

    # Evaluate actual replacement outcomes, then apply the cash + resale budget.
    has_budget_limit = budget is not None or sell_mode == "budget_plus_sell"
    search_budget = total_budget

    def fps_for(item):
        if bottleneck is Bottleneck.CPU:
            return estimate_fps(item['raw_score'], gpu_raw, gpu_name, game, mode, ram_boost, item.get('name', ''))
        return estimate_fps(cpu_raw, item['raw_score'], item['name'], game, mode, ram_boost, cpu_name)

    candidates = [item for item in (compatible_cpus if bottleneck is Bottleneck.CPU else better_gpus)
                  if meaningful_upgrade(current_fps, fps_for(item))]
    if game == GameName.CS2 and bottleneck is Bottleneck.CPU and cs2_cpu_basis(cpu_name):
        based = [item for item in candidates if cs2_cpu_basis(item.get('name', ''))]
        candidates = based or candidates

    affordable = [item for item in candidates if item.get('avg_price') and
                  (not has_budget_limit or item['avg_price'] <= search_budget)]
    unknown = [item for item in candidates if not item.get('avg_price') and
               (not has_budget_limit or search_budget > 0)]
    stretch = [item for item in candidates if item.get('avg_price') and
               has_budget_limit and item['avg_price'] > search_budget]
    eligible = affordable or unknown

    def choose(items):
        reached = [item for item in items if fps_for(item) >= target_fps and item.get('avg_price')]
        if reached:
            return min(reached, key=lambda item: (item['avg_price'], -fps_for(item), item['raw_score']))
        return max(items, key=lambda item: (fps_for(item), -(item.get('avg_price') or float('inf')),
                                            -item['raw_score']))

    # Unknown-price cards can be explored, but cannot be an automatic budgeted
    # purchase recommendation.
    recommended = choose(affordable) if affordable else choose(unknown) if unknown and not has_budget_limit else None
    chosen = recommended
    if selected_upgrade_id:
        chosen = next((item for item in eligible if item.get('id') == selected_upgrade_id), None)
        if chosen is None:
            from fastapi import HTTPException
            raise HTTPException(400, 'Выбранный вариант апгрейда больше не доступен в текущем бюджете. Повторите расчёт.')

    already_reached = current_fps >= target_fps
    if already_reached and not selected_upgrade_id:
        chosen = None
        rec = f'Текущий прогноз {current_fps} FPS достигает цели {target_fps} FPS. Покупка для этой цели по модели не требуется.'
    elif chosen:
        amount = chosen.get('avg_price')
        label = f" ({amount:,} ₽)" if amount else " (цена неизвестна)"
        rec += f" {'Выбранный' if selected_upgrade_id else 'Рекомендуемый'} апгрейд: {chosen['name']}{label}."
        if has_budget_limit and not amount:
            rec += ' Цена неизвестна: соответствие бюджету не подтверждено.'
        after = fps_for(chosen)
        rec += (f' По центральному прогнозу {after} FPS цель {target_fps} FPS достигнута.'
                if after >= target_fps else
                f' Цель {target_fps} FPS не достигнута: прогноз {after} FPS. Показан доступный прирост, а не обещание целевого FPS.')
    else:
        rec += f' Центральный прогноз {current_fps} FPS; цель {target_fps} FPS не достигнута.'
        if stretch:
            cheapest = min(item['avg_price'] for item in stretch)
            rec += f' Известные цены подходящих замен начинаются от {cheapest:,} ₽; после учёта продажи доступно {search_budget:,} ₽.'
        else:
            rec += ' Существенная замена с известной ценой в бюджете не найдена.'
            if unknown:
                rec += ' Для вариантов без цены соответствие бюджету не подтверждено.'

    if ram_type and ram_channels == 1:
        rec += ' Проверьте возможность двухканального режима RAM на вашей плате.'
    if ram_type == 'DDR3':
        rec += ' Замена памяти на DDR4/DDR5 может потребовать новую материнскую плату.'

    # Retain one useful priced option outside the budget, clearly labelled and
    # disabled for selection. Do not make a higher-budget purchase look affordable.
    best = choose(eligible) if eligible else None
    if eligible:
        best = max(eligible, key=lambda item: (fps_for(item), -(item.get('avg_price') or float('inf'))))
    extra = choose(stretch) if stretch else None
    ordered = [recommended, extra, best, *sorted(eligible, key=lambda item: (
        item.get('avg_price') or float('inf'), -fps_for(item)))]
    alternatives, seen = [], set()
    for item in ordered:
        if item is None:
            continue
        identity = item.get('id') or item['name']
        if identity in seen:
            continue
        seen.add(identity)
        fps = fps_for(item)
        amount = item.get('avg_price')
        shortfall = max(0, amount - search_budget) if amount and has_budget_limit else 0
        card_gpu = item['name'] if bottleneck is Bottleneck.GPU else gpu_name
        alternatives.append({
            'id': item.get('id'), 'name': item['name'], 'component': bottleneck.value,
            'price': amount, 'fps': fps, 'fps_outlook': fps_outlook(fps, card_gpu, game, mode),
            'gain': fps-current_fps, 'target_reached': fps >= target_fps,
            'resale_value': current_component_price,
            'net_cost': max(0, amount-current_component_price) if amount else None,
            'budget_shortfall': shortfall,
            'selection_allowed': not bool(shortfall),
        })
        if len(alternatives) == 3:
            break

    upgraded_fps = fps_for(chosen) if chosen else current_fps
    return CalculateResult(
        bottleneck=bottleneck, current_fps=current_fps, upgraded_fps=upgraded_fps,
        recommendation=rec, avg_price=(chosen.get('avg_price') or 0) if chosen else 0,
        within_budget=bool(chosen and chosen.get('avg_price') and has_budget_limit),
        upgrade_component=(chosen['name'] + (f" ({chosen['avg_price']:,} ₽)" if chosen.get('avg_price')
                           else ' (цена неизвестна)')) if chosen else None,
        ai_warning=ai_warning, current_component_price=current_component_price,
        total_budget=total_budget, mode=sell_mode, is_maxed_out=is_maxed_out,
        upgrade_id=chosen.get('id') if chosen else None,
        upgrade_name=chosen['name'] if chosen else None,
        alternatives=alternatives, limiting_explanation=limiting_explanation,
    )

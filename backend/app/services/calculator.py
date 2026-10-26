from dataclasses import dataclass
from app.core.constants import GAME_PROFILES
from app.schemas.calculate import AIOption, Bottleneck, CalcMode, GameName


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
    
    # Memory affects CPU throughput; it must not increase a GPU-limited result.
    cpu_cap = cpu_raw * profile["cpu"] * ram_boost
    gpu_cap = gpu_raw * profile["gpu"]
    bottleneck = Bottleneck.CPU if cpu_cap < gpu_cap else Bottleneck.GPU
    current_fps = max(1, round(min(cpu_cap, gpu_cap) * profile["overhead"]))

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

    compatible_cpus = [c for c in (all_cpus or []) if c.get("raw_score", 0) > cpu_raw
                       and cpu_socket and "BGA" not in cpu_socket.upper() and c.get("socket") == cpu_socket]
    better_gpus = [g for g in (all_gpus or []) if g.get("raw_score", 0) > gpu_raw]
    is_maxed_out = not compatible_cpus and not better_gpus
    upgraded_fps = current_fps

    # 4. Формируем умные рекомендации
    if is_maxed_out:
        rec = (
            f"Для игры {game.value} ({mode.value}) в текущем каталоге нет более быстрых "
            f"комплектующих, подходящих для этой сборки."
        )
    elif bottleneck is Bottleneck.CPU:
        diff = round((gpu_cap - cpu_cap) / max(gpu_cap, 1) * 100)
        rec = (
            f"В режиме «{mode.value}» для игры {game.value} процессор ограничивает "
            f"видеокарту на {diff}%. Чтобы поднять FPS, обновите CPU."
        )
    else:
        diff = round((cpu_cap - gpu_cap) / max(cpu_cap, 1) * 100)
        rec = (
            f"В режиме «{mode.value}» для игры {game.value} видеокарта упирается в свой потолок "
            f"(отставание от CPU: {diff}%). Апгрейд GPU даст больший прирост."
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

    # 6. Поиск апгрейда в рамках бюджета
    within_budget = False
    upgrade_component = None
    upgrade_id = None
    
    # Используем total_budget если sell_mode = budget_plus_sell
    search_budget = total_budget if sell_mode == "budget_plus_sell" else effective_budget
    has_budget_limit = budget is not None or sell_mode == "budget_plus_sell"
    
    if not is_maxed_out:
        if bottleneck is Bottleneck.CPU and all_cpus:
            candidates = compatible_cpus
            if has_budget_limit:
                candidates = [c for c in candidates if c.get("avg_price") and c["avg_price"] <= search_budget]
            def cpu_fps(item):
                return round(min(item["raw_score"] * profile["cpu"] * ram_boost, gpu_cap) * profile["overhead"])
            candidates = [c for c in candidates if cpu_fps(c) > current_fps]
            if candidates:
                chosen = max(candidates, key=lambda c: (cpu_fps(c), -(c.get("avg_price") or float("inf")), -c["raw_score"]))
                upgrade_id = chosen.get("id")
                upgraded_fps = max(current_fps, round(min(chosen["raw_score"] * profile["cpu"] * ram_boost, gpu_cap) * profile["overhead"]))
                upgrade_component = chosen['name'] + (f" ({chosen['avg_price']:,} ₽)" if chosen.get('avg_price') else " (цена неизвестна)")
                within_budget = has_budget_limit
        elif bottleneck is Bottleneck.GPU and all_gpus:
            candidates = better_gpus
            if has_budget_limit:
                candidates = [g for g in candidates if g.get("avg_price") and g["avg_price"] <= search_budget]
            def gpu_fps(item):
                return round(min(cpu_cap, item["raw_score"] * profile["gpu"]) * profile["overhead"])
            candidates = [g for g in candidates if gpu_fps(g) > current_fps]
            if candidates:
                chosen = max(candidates, key=lambda g: (gpu_fps(g), -(g.get("avg_price") or float("inf")), -g["raw_score"]))
                upgrade_id = chosen.get("id")
                upgraded_fps = max(current_fps, round(min(cpu_cap, chosen["raw_score"] * profile["gpu"]) * profile["overhead"]))
                upgrade_component = chosen['name'] + (f" ({chosen['avg_price']:,} ₽)" if chosen.get('avg_price') else " (цена неизвестна)")
                within_budget = has_budget_limit
        
        if upgrade_component:
            rec += f" Рекомендуемый апгрейд: {upgrade_component}."
        elif has_budget_limit:
            if bottleneck is Bottleneck.CPU:
                priced = [c["avg_price"] for c in compatible_cpus if c.get("avg_price")]
                if priced:
                    min_price = min(priced)
                    rec += f" Рекомендуемые CPU начинаются от ~{min_price:,} ₽. Ваш бюджет нужно увеличить."
                else:
                    rec += " Нет совместимого CPU с подтверждённой ценой в этом бюджете."
            else:
                priced = [g["avg_price"] for g in better_gpus if g.get("avg_price")]
                if priced:
                    min_price = min(priced)
                    rec += f" Рекомендуемые GPU начинаются от ~{min_price:,} ₽. Ваш бюджет нужно увеличить."
                else:
                    rec += " Нет более быстрой GPU с подтверждённой ценой в этом бюджете."
        
        # Рекомендация по RAM
        if ram_type and ram_channels == 1:
            rec += " Проверьте возможность двухканального режима RAM на вашей плате."
        if ram_type == "DDR3":
            rec += " Замена памяти на DDR4/DDR5 может потребовать новую материнскую плату."

    return CalculateResult(
        bottleneck=bottleneck,
        current_fps=current_fps,
        upgraded_fps=upgraded_fps,
        recommendation=rec,
        avg_price=(min((c.get("avg_price") for c in (compatible_cpus if bottleneck is Bottleneck.CPU else better_gpus) if c.get("avg_price")), default=0)),
        within_budget=within_budget,
        upgrade_component=upgrade_component,
        ai_warning=ai_warning,
        current_component_price=current_component_price,
        total_budget=total_budget,
        mode=sell_mode,
        is_maxed_out=is_maxed_out,
        upgrade_id=upgrade_id,
    )

from dataclasses import dataclass
from app.core.constants import GAME_PROFILES, MOCK_AVG_PRICE_RUB
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

    # 1. Считаем потолок FPS для каждого компонента
    cpu_cap = cpu_raw * profile["cpu"]
    gpu_cap = gpu_raw * profile["gpu"]

    # 2. Определяем ограничитель
    bottleneck = Bottleneck.CPU if cpu_cap < gpu_cap else Bottleneck.GPU
    limiting = min(cpu_cap, gpu_cap)

    current_fps = max(1, round(limiting * profile["overhead"]))

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
    
    current_fps = round(current_fps * ram_boost)

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

    # 3. Проверка на "топовое железо" по сырым баллам PassMark
    # Топовый игровой CPU (9950X3D) ~ 70 000; Топовая GPU (5090) ~ 45 000
    is_cpu_maxed = cpu_raw > 45000
    is_gpu_maxed = gpu_raw > 35000
    
    is_maxed_out = is_cpu_maxed and is_gpu_maxed
    
    if is_maxed_out:
        upgrade_gain = 1.05  # Прирост будет минимальным
    else:
        upgrade_gain = 1.35  # Стандартный прирост 35%

    upgraded_fps = max(current_fps + 1, round(current_fps * upgrade_gain))

    # 4. Формируем умные рекомендации
    if is_maxed_out:
        rec = (
            f"У вас установлены топовые комплектующие. В игре {game.value} ({mode.value}) "
            f"система упирается в программные ограничения движка. "
            f"Дальнейший апгрейд железа не даст ощутимого прироста FPS."
        )
    elif bottleneck is Bottleneck.CPU:
        diff = round((gpu_cap - cpu_cap) / gpu_cap * 100)
        rec = (
            f"В режиме «{mode.value}» для игры {game.value} процессор ограничивает "
            f"видеокарту на {diff}%. Чтобы поднять FPS, обновите CPU."
        )
    else:
        diff = round((cpu_cap - gpu_cap) / cpu_cap * 100)
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
    upgrade_socket_mismatch = False
    
    # Используем total_budget если sell_mode = budget_plus_sell
    search_budget = total_budget if sell_mode == "budget_plus_sell" else effective_budget
    
    if search_budget and search_budget > 0 and not is_maxed_out:
        if bottleneck is Bottleneck.CPU and all_cpus:
            # Ищем CPU с лучшим баллом, который вписывается в бюджет И совместим по сокету
            for cpu in all_cpus:
                if cpu["raw_score"] <= cpu_raw:
                    continue
                price = cpu.get("avg_price", 0) or 0
                if price <= search_budget:
                    # Проверяем совместимость сокета
                    if cpu_socket and cpu.get("socket") and cpu["socket"] != cpu_socket:
                        upgrade_socket_mismatch = True
                    upgrade_component = f"{cpu['name']} ({price:,} ₽)"
                    within_budget = True
                    break
        elif bottleneck is Bottleneck.GPU and all_gpus:
            for gpu in all_gpus:
                if gpu["raw_score"] <= gpu_raw:
                    continue
                price = gpu.get("avg_price", 0) or 0
                if price <= search_budget:
                    upgrade_component = f"{gpu['name']} ({price:,} ₽)"
                    within_budget = True
                    break
        
        if upgrade_component:
            if bottleneck is Bottleneck.CPU:
                rec += f" Рекомендуемый апгрейд: {upgrade_component}."
                if upgrade_socket_mismatch:
                    rec += " ⚠️ Внимание: новый CPU требует другую материнскую плату (несовместимый сокет)!"
            else:
                rec += f" Рекомендуемый апгрейд: {upgrade_component}."
        else:
            if bottleneck is Bottleneck.CPU:
                better_cpus = [c for c in all_cpus if c.get('raw_score', 0) > cpu_raw]
                if better_cpus:
                    min_price = min((c.get('avg_price', 0) or 99999) for c in better_cpus)
                    rec += f" Рекомендуемые CPU начинаются от ~{min_price:,} ₽. Ваш бюджет нужно увеличить."
                else:
                    rec += " Все улучшенные CPU дороже вашего бюджета."
            else:
                better_gpus = [g for g in all_gpus if g.get('raw_score', 0) > gpu_raw]
                if better_gpus:
                    min_price = min((g.get('avg_price', 0) or 99999) for g in better_gpus)
                    rec += f" Рекомендуемые GPU начинаются от ~{min_price:,} ₽. Ваш бюджет нужно увеличить."
                else:
                    rec += " Все улучшенные GPU дороже вашего бюджета."
        
        # Рекомендация по RAM
        if ram_type and ram_type != "DDR5" and ram_channels == 1:
            rec += " 💡 Переход на DDR5 + двухканальный режим может дать +10-15% FPS в играх."
        elif ram_type and ram_type == "DDR3":
            rec += " 💡 DDR3 сильно ограничивает современные CPU. Рекомендуется DDR4/DDR5."

    return CalculateResult(
        bottleneck=bottleneck,
        current_fps=current_fps,
        upgraded_fps=upgraded_fps,
        recommendation=rec,
        avg_price=MOCK_AVG_PRICE_RUB,
        within_budget=within_budget,
        upgrade_component=upgrade_component,
        ai_warning=ai_warning,
        current_component_price=current_component_price,
        total_budget=total_budget,
        mode=sell_mode,
        is_maxed_out=is_maxed_out,
    )
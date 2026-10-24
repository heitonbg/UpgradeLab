from dataclasses import dataclass
from app.core.constants import GAME_PROFILES, MOCK_AVG_PRICE_RUB
from app.schemas.calculate import Bottleneck, CalcMode, GameName


@dataclass(frozen=True)
class CalculateResult:
    bottleneck: Bottleneck
    current_fps: int
    upgraded_fps: int
    recommendation: str
    avg_price: int


def calculate(*, cpu_raw: int, gpu_raw: int, game: GameName, mode: CalcMode) -> CalculateResult:
    profile = GAME_PROFILES[game][mode]

    # 1. Считаем потолок FPS для каждого компонента
    cpu_cap = cpu_raw * profile["cpu"]
    gpu_cap = gpu_raw * profile["gpu"]

    # 2. Определяем ограничитель
    bottleneck = Bottleneck.CPU if cpu_cap < gpu_cap else Bottleneck.GPU
    limiting = min(cpu_cap, gpu_cap)

    current_fps = max(1, round(limiting * profile["overhead"]))

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

    return CalculateResult(
        bottleneck=bottleneck,
        current_fps=current_fps,
        upgraded_fps=upgraded_fps,
        recommendation=rec,
        avg_price=MOCK_AVG_PRICE_RUB,
    )
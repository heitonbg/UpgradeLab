"""Approximate FPS with explicit provenance and non-statistical uncertainty.

Reference observations describe a GPU on the reviewer's test system, not a
measured result for the user's CPU/GPU pair. Never label them as pair tests.
"""
import math
import re
from app.core.constants import GAME_PROFILES, ESTIMATED_GAME_PROFILES
from app.schemas.calculate import GameName, CalcMode
from app.services.benchmark_estimates import benchmark_reference, catalog_scores
from functools import lru_cache


RDR2_2060_SUPER = [
    {"title": "The FPS Review: RTX 2060 SUPER, 1440p custom High", "fps": 53.2,
     "url": "https://www.thefpsreview.com/2020/03/09/nvidia-geforce-rtx-2060-super-fe-overclocking/4/"},
    {"title": "the比較: RDR2, RTX 2060 SUPER, 1440p High", "fps": 66,
     "url": "https://thehikaku.net/pc/game/19rdr2.html"},
]

# Published averages are shown separately: Ultra/maximum is NOT our High preset.
# No cross-preset conversion or interpolation is presented as a measurement.
COMPARISON_TESTS = {
    (GameName.BG3, CalcMode.MODE_1440P_HIGH): (
        "ComputerBase: Baldur's Gate 3 (2023)",
        'https://www.computerbase.de/artikel/gaming/baldurs-gate-3-benchmark-test.85071/seite-3',
        '2560×1440, Ultra, нативное разрешение, без RT/генерации кадров',
        {'rtx4060': 52.8, 'rtx3060': 44.6, 'rtx3060ti': 61.0, 'rx6600': 44.2}),
    (GameName.HOGWARTS, CalcMode.MODE_1080P_HIGH): (
        'ComputerBase: Hogwarts Legacy (2023)',
        'https://www.computerbase.de/artikel/gaming/hogwarts-legacy-benchmark-test.83313/',
        '1920×1080, максимальная графика, без RT/апскейлинга/генерации кадров',
        {'rtx3060': 39.1, 'rtx3060ti': 50.4, 'rx6700xt': 54.0}),
    (GameName.FORZA5, CalcMode.MODE_1440P_HIGH): (
        'ComputerBase: Forza Horizon 5 (2021)',
        'https://www.computerbase.de/artikel/gaming/forza-horizon-5-benchmark-test.78538/seite-2',
        '2560×1440, максимальная графика на тестовой системе издания',
        {'rtx3060': 47.8, 'rtx3060ti': 63.3, 'rx6700xt': 66.7}),
}


def comparison_tests(gpu_name, game, mode):
    entry = COMPARISON_TESTS.get((game, mode))
    if not entry:
        return []
    from app.services.offers import signature
    key = signature(gpu_name, 'GPU')
    # The reviews' RTX 3060 is the 12GB desktop model. Avoid assigning it to
    # a separately labelled 8GB/mobile variant.
    if re.search(r'laptop|mobile|\b8\s*(?:GB|ГБ)\b', gpu_name, re.I) and key == 'rtx3060':
        return []
    title, url, settings, values = entry
    if key not in values or re.search(r'laptop|mobile|max-q', gpu_name, re.I):
        return []
    return [{'title': title, 'url': url, 'settings': settings, 'fps': values[key]}]


def references(gpu_name, game, mode):
    if game == GameName.RDR2 and mode == CalcMode.MODE_1440P_HIGH and re.search(r"\bRTX\s*2060\s*SUPER\b", gpu_name, re.I):
        return RDR2_2060_SUPER
    return []


CS2_GPU_MEDIUM_SOURCE = 'https://www.computerbase.de/artikel/gaming/counter-strike-2-benchmark-test.87904/'
# Published 1080p Medium results, NOT Low measurements. Using these as a
# conservative Low reference avoids the old arbitrary 420-FPS synthetic ceiling.
CS2_GPU_MEDIUM = {'rtx4060': 433.9, 'rtx3060': 338.0, 'rtx3050': 253.3,
                  'gtx1660super': 261.1, 'rx6650xt': 409.1, 'rx7600xt': 381.4,
                  'rx7600': 380.8, 'rx6600': 342.5, 'arca750': 300.5,
                  'rx6500xt': 225.0, 'gtx1650super': 205.6, 'arca380': 135.9}


@lru_cache(maxsize=1024)
def cs2_gpu_reference(name, raw_score=None):
    from app.services.offers import signature
    from app.services.hardware_matching import model_key
    key = signature(name, 'GPU')
    if not key or re.search(r'laptop|mobile|max-q', name, re.I):
        return None
    if key == 'rtx3060' and re.search(r'\b8\s*(?:GB|ГБ)\b', name, re.I) or key == 'rtx3050' and re.search(r'\b6\s*(?:GB|ГБ)\b', name, re.I):
        return None
    scores = catalog_scores()
    score = raw_score or scores.get(model_key(name))
    if key in CS2_GPU_MEDIUM:
        reference, fps = key, CS2_GPU_MEDIUM[key]
    else:
        if not score:
            return None
        vendor = 'nvidia' if key.startswith(('rtx','gtx','gt')) else 'amd' if key.startswith(('rx','vega')) else 'intel'
        pool = [item for item in CS2_GPU_MEDIUM if item in scores and (
            item.startswith(('rtx','gtx')) if vendor == 'nvidia' else item.startswith('rx') if vendor == 'amd' else item.startswith('arc'))]
        if not pool:
            return None
        reference = min(pool, key=lambda item: abs(math.log(score/scores[item])))
        fps = CS2_GPU_MEDIUM[reference] * (score/scores[reference]) ** .8
    return {'fps': fps, 'sources': [{'title': f'ComputerBase (2024) · {reference.upper()}',
            'url': CS2_GPU_MEDIUM_SOURCE, 'fps': CS2_GPU_MEDIUM[reference],
            'settings': '1920×1080 Medium; исходный пресет отличается от выбранного Low'}],
            'interpolated': key != reference}


def gpu_capacity(raw_score, name, game, mode):
    profile = GAME_PROFILES[game][mode]
    cs2 = cs2_gpu_reference(name, raw_score) if game == GameName.CS2 and mode == CalcMode.MODE_1080P_LOW else None
    if cs2:
        return cs2['fps']/profile['overhead']
    samples = references(name, game, mode)
    if samples:
        # Convert back to the pre-overhead scale used by the shared CPU/GPU model.
        return sum(row['fps'] for row in samples) / len(samples) / profile['overhead']
    benchmark = benchmark_reference(name, game.value, mode.value, raw_score)
    if benchmark:
        return benchmark['fps'] / profile['overhead']
    return raw_score * profile['gpu']


CS2_CPU_TEST = {
    # Relative ordering only: ComputerBase used a 2023 CS2 scene, RTX 4090 and
    # 720p. These figures are not the user's 1080p FPS.
    'ryzen55600': 655.3, 'ryzen75800x': 712.4, 'ryzen75800x3d': 788.8,
    'ryzen95950x': 614.9, 'ryzen53600': 397.8, 'ryzen73800x': 402.0,
    'ryzen72700x': 286.9, 'i910900k': 498.1, 'i911900k': 491.3,
    'i511600k': 444.7,
    'i313100f': 403.6, 'i510600k': 379.6, 'i510400f': 355.4,
    'i512600k': 512.4, 'i712700k': 592.6, 'i912900k': 635.1,
    'i513600k': 670.9, 'i714700k': 756.2, 'i713700k': 750.1,
    'i914900k': 823.8, 'i913900k': 792.2, 'i514600k': 710.9,
    'ryzen57600x': 864.4, 'ryzen77700x': 940.6, 'ryzen77800x3d': 941.1,
    'ryzen97950x3d': 1006.4,
}
CS2_CPU_SOURCE = 'https://www.computerbase.de/artikel/prozessoren/cpu-gaming-benchmarks-amd-ryzen-vs-intel-core.85869/'
CS2_CPU_ALIASES = {'ryzen55600x': ('ryzen55600', 1.01),
                   'ryzen75700x': ('ryzen75800x', .98),
                   'ryzen75700x3d': ('ryzen75800x3d', .95),
                   'ryzen55600x3d': ('ryzen75800x3d', .94),
                   'ryzen95900x': ('ryzen95950x', 1.0)}


def cs2_cpu_basis(name):
    from app.services.offers import signature
    key = signature(name, 'CPU')
    base, factor = CS2_CPU_ALIASES.get(key, (key, 1.0))
    measured = CS2_CPU_TEST.get(base)
    return measured * factor if measured else None


def cpu_capacity(raw_score, name, game, mode, ram_factor=1):
    profile = GAME_PROFILES[game][mode]
    if game != GameName.CS2 or not name:
        return raw_score * profile['cpu'] * ram_factor
    # Closely related models are estimates, not measured rows. 5700X3D is
    # modelled conservatively relative to 5800X3D rather than by core count.
    measured = cs2_cpu_basis(name)
    # For CPUs outside the benchmark do not equate multi-core PassMark with
    # gaming FPS. A softened curve is still an explicitly uncertain estimate.
    raw_ratio = max(raw_score, 1) / 21819
    # The high-end multi-core correction must not boost old, low-score CPUs.
    ratio = measured / CS2_CPU_TEST['ryzen55600'] if measured else min(raw_ratio, raw_ratio ** .6)
    return 21819 * profile['cpu'] * ratio * ram_factor


def ram_performance_factor(game, cpu_name='', ram_type=None, ram_channels=None):
    if game == GameName.CS2 and cpu_name:
        return .93 if ram_channels == 1 else 1.0
    factor = 1.0
    if ram_type and ram_channels:
        if ram_channels == 2:
            factor += .05
        if ram_type == 'DDR5':
            factor += .08 + (.03 if ram_channels == 2 else 0)
        elif ram_type == 'DDR4' and ram_channels == 2:
            factor += .02
        elif ram_type == 'DDR3':
            factor -= .05
    return factor


def estimate_fps(cpu_raw, gpu_raw, gpu_name, game, mode, ram_factor=1, cpu_name=''):
    profile = GAME_PROFILES[game][mode]
    return max(1, round(min(cpu_capacity(cpu_raw, cpu_name, game, mode, ram_factor),
                            gpu_capacity(gpu_raw, gpu_name, game, mode)) * profile['overhead']))


def fps_outlook(estimate, gpu_name, game, mode):
    samples = references(gpu_name, game, mode)
    benchmark = benchmark_reference(gpu_name, game.value, mode.value) if not samples else None
    cs2 = cs2_gpu_reference(gpu_name) if game == GameName.CS2 and mode == CalcMode.MODE_1080P_LOW else None
    model_only = not samples and not benchmark and not cs2
    spread = (.40 if cs2['interpolated'] else .35) if cs2 else benchmark['spread'] if benchmark else .45 if game in ESTIMATED_GAME_PROFILES else .30
    low, high = estimate * (1-spread), estimate * (1+spread)
    if samples:
        low = min(estimate * .8, min(row['fps'] for row in samples) * .9)
        high = min(estimate * 1.2, max(row['fps'] for row in samples))
    return {
        "minimum": max(1, int(math.floor(low / 5) * 5)),
        "maximum": max(1, int(math.ceil(high / 5) * 5)),
        "method": "benchmark_settings_estimate" if cs2 else "gpu_reference_cpu_estimate" if samples else "benchmark_interpolation" if benchmark and benchmark['interpolated'] else "benchmark_settings_estimate" if benchmark and benchmark['derived'] else "gpu_reference_cpu_estimate" if benchmark else "synthetic_estimate",
        "data_quality": "estimated_from_tests" if cs2 else "model_only" if model_only else "estimated_from_tests" if benchmark and (benchmark['derived'] or benchmark['interpolated']) else "gpu_tests",
        "sources": cs2['sources'] if cs2 else samples or (benchmark['sources'] if benchmark else []),
        "comparison_tests": comparison_tests(gpu_name, game, mode),
        "note": ("Для CS2 Low используется консервативная опора на тесты GPU при 1080p Medium (ComputerBase, 2024). Это другой пресет; для отсутствующей GPU выполнен перенос по синтетическому баллу. Это не прямой тест Low или вашей связки."
                 if cs2 else "Есть тесты этой GPU на High/custom High в 2560×1440. CPU, версия игры и настройки тестовых систем отличаются. Это не тест вашей связки."
                 if samples else benchmark['note'] if benchmark else "Для этой GPU и настроек не хватает игровых измерений: используется расчёт по синтетическим баллам с широким диапазоном. Реальный FPS может выйти за его границы."),
        "context_sources": ([{"title": "Мир танков: актуальные требования разработчика (это не замер FPS)",
                              "url": "https://tanki.su/ru/content/docs/download/"}] if game == GameName.MIR_TANKOV else []),
        "settings": "Без DLSS/FSR, генерации кадров и трассировки лучей; разрешение рендера соответствует выбранному.",
        "uncertainty": "Границы — эвристическая оценка разброса, не измерение и не статистический доверительный интервал.",
    }

"""Published desktop GPU samples plus explicitly labelled interpolation.

High at QHD is derived from a measured FHD High and a resolution ratio at the
same reference preset. That is an estimate, never a measured QHD High result.
"""
import json
import math
import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def datasets():
    return json.loads((Path(__file__).resolve().parents[1] / 'data/game_benchmarks.json').read_text(encoding='utf-8'))['games']


@lru_cache(maxsize=1)
def catalog_scores():
    from app.services.hardware_matching import model_key
    seed = json.loads((Path(__file__).resolve().parents[2] / 'seed_data.json').read_text(encoding='utf-8'))
    return {model_key(row['name']): row['score'] for row in seed['gpus'] if row.get('category') == 'Desktop'}


@lru_cache(maxsize=1)
def fpshq_top50_rows():
    path = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "fpshq_model_top50_raw.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    meta = document.get("meta", {})
    if meta.get("license") != "CC BY 4.0" or meta.get("url") != "https://fpshq.com/en/data/fps-model-top50/":
        raise RuntimeError("Unexpected FPSHQ top-50 dataset provenance")
    return document["rows"]


def fpshq_gpu_reference(gpu_name, game, mode, score_hint=None):
    """GPU-only FPSHQ reference; never represents a tested CPU/GPU pair."""
    resolution = {"1080p_high": "1080p", "1440p_high": "1440p", "4k_high": "4K"}.get(mode)
    if not resolution:
        return None
    aliases = {
        "gtav": "grandtheftautov",
        "thewitcher3nextgen": "thewitcher3wildhunt",
        "pubg": "pubgbattlegrounds",
        "cs2": "counterstrike2",
    }
    canonical = re.sub(r"[^a-z0-9]", "", str(game).casefold())
    wanted = aliases.get(canonical, canonical)
    rows = [row for row in fpshq_top50_rows()
            if re.sub(r"[^a-z0-9]", "", row.get("game", "").casefold()) == wanted
            and row.get("resolution") == resolution and row.get("preset", "").casefold() == "high"]
    if not rows:
        return None
    from app.services.offers import signature
    from app.services.hardware_matching import model_key
    candidate_key = signature(gpu_name, "GPU")
    if not candidate_key:
        return None
    exact = next((row for row in rows if signature(row.get("gpu", ""), "GPU") == candidate_key), None)
    family_proxy = bool(re.search(r"\b(?:RTX\s*5090\s*D|RTX\s*4090\s*D)\b", gpu_name, re.I))
    if exact:
        value = float(exact["fps"])
        chosen = [exact]
        interpolated = family_proxy
    else:
        score = score_hint or catalog_scores().get(model_key(gpu_name))
        if not score:
            return None
        pool = []
        for row in rows:
            row_score = catalog_scores().get(model_key(row.get("gpu", "")))
            if row_score and row.get("fps"):
                pool.append((row, row_score))
        if not pool:
            return None
        same_vendor = [item for item in pool if vendor(signature(item[0].get("gpu", ""), "GPU")) ==
                       vendor(candidate_key)]
        if same_vendor:
            pool = same_vendor
        lower = max((item for item in pool if item[1] <= score), key=lambda item: item[1], default=None)
        upper = min((item for item in pool if item[1] >= score), key=lambda item: item[1], default=None)
        if lower and upper and lower[1] != upper[1]:
            fraction = math.log(score / lower[1]) / math.log(upper[1] / lower[1])
            value = float(lower[0]["fps"]) * (float(upper[0]["fps"]) / float(lower[0]["fps"])) ** fraction
            chosen = [lower[0], upper[0]]
        else:
            nearest = min(pool, key=lambda item: abs(math.log(score / item[1])))
            value = float(nearest[0]["fps"]) * (score / nearest[1]) ** .8
            chosen = [nearest[0]]
        interpolated = True
    source_url = "https://fpshq.com/en/data/fps-model-top50/"
    source = {"title": f"FPSHQ · {chosen[0].get('gpu')} · {game} · {resolution} High",
              "url": chosen[0].get("url") or source_url, "fps": round(value),
              "settings": f"{resolution} High · GPU reference", "gpu": chosen[0].get("gpu")}
    provenance = chosen[0].get("source", "model")
    spread = .50 if family_proxy else .40 if interpolated or provenance == "model" else .30
    note = ("FPSHQ GPU reference, not a CPU/GPU system test. CPU performance is estimated separately. " +
            ("The D model uses a same-family reference; its own measured result was not found. " if family_proxy else "") +
            ("GPU performance is transferred by synthetic score. " if interpolated else ""))
    return {"fps": value, "sources": [source], "interpolated": interpolated,
            "derived": provenance == "model", "spread": spread, "note": note,
            "year": 2026, "measurement_type": provenance, "gpu_reference": True,
            "exact_gpu": not interpolated}


def vendor(key):
    return 'nvidia' if key.startswith(('rtx', 'gtx', 'gt')) else 'amd' if key.startswith(('rx', 'vega')) else 'other'


def sample_estimate(sample, data, mode):
    if mode in ('1080p_low', '1080p_high'):
        return sample.get(mode), False
    if mode == '4k_high':
        direct = sample.get('4k_high') or sample.get('4k_ultra')
        if direct:
            return direct, mode == '4k_high' and not sample.get('4k_high')
        qhd, derived = sample_estimate(sample, data, '1440p_high')
        return (qhd * .60, True) if qhd else (None, True)
    if sample.get('1440p_high'):
        return sample['1440p_high'], bool(data.get('high_is_reference_only'))
    high, full, qhd = sample.get('1080p_high'), sample.get('1080p_ultra'), sample.get('1440p_ultra')
    if high and full and qhd:
        return high * min(1, qhd / full), True
    if high and full and sample.get('4k_ultra'):
        ratio = (sample['4k_ultra'] / full) ** (math.log(2560 * 1440 / (1920 * 1080)) / math.log(4))
        return high * min(1, ratio), True
    # No reference resolution without RT exists for RE4: use a deliberately
    # labelled pixel-load model, not its Max/RT measurements.
    if high:
        return high * (1920 * 1080 / (2560 * 1440)) ** .6, True
    return None, True


def source_points(sample, data, mode):
    keys = ['1080p_low'] if mode == '1080p_low' else ['1080p_high']
    if mode == '4k_high':
        keys = ['4k_high'] if sample.get('4k_high') else ['4k_ultra'] if sample.get('4k_ultra') else ['1440p_high', '1080p_high']
    elif mode == '1440p_high':
        keys = (['1440p_high'] if sample.get('1440p_high') else
                ['1080p_high', '1080p_ultra', '1440p_ultra'] if sample.get('1440p_ultra') else
                ['1080p_high', '1080p_ultra', '4k_ultra'] if sample.get('4k_ultra') else ['1080p_high'])
    labels = {'1080p_low': '1920×1080 Low', '1080p_high': '1920×1080 ' + data['high_preset'],
              '1080p_ultra': '1920×1080 ' + str(data.get('reference_preset')),
              '1440p_ultra': '2560×1440 ' + str(data.get('reference_preset')),
              '1440p_high': '2560×1440 ' + data['high_preset'],
              '4k_ultra': '3840×2160 ' + str(data.get('reference_preset'))}
    return [{'title': f"{data['publisher']} ({data['year']}) · {sample['gpu']}", 'url': data['source'],
             'fps': sample[key], 'settings': labels[key], 'gpu': sample['gpu']}
            for key in keys if sample.get(key)]


@lru_cache(maxsize=4096)
def benchmark_reference(gpu_name, game, mode, score_hint=None):
    from app.services.offers import signature
    from app.services.hardware_matching import model_key
    data = datasets().get(game)
    if not data:
        return fpshq_gpu_reference(gpu_name, game, mode, score_hint)
    if not data or re.search(r'laptop|mobile|max-q|(?:RTX|GTX|RX)\s*\d+M\b', gpu_name, re.I):
        return None
    key = signature(gpu_name, 'GPU')
    if not key:
        return None
    pool = [(sample, *sample_estimate(sample, data, mode)) for sample in data['samples']]
    pool = [item for item in pool if item[1] is not None]
    exact = next((item for item in pool if item[0]['key'] == key), None)
    if key == 'rtx3060' and re.search(r'\b8\s*(?:GB|ГБ)\b', gpu_name, re.I):
        exact = None
        pool = [item for item in pool if item[0]['key'] != key]
    if not pool:
        return fpshq_gpu_reference(gpu_name, game, mode, score_hint)
    interpolated = exact is None
    if exact:
        chosen = [exact]
        fps = exact[1]
    else:
        score = score_hint or catalog_scores().get(model_key(gpu_name))
        if not score:
            return None
        same_vendor = [item for item in pool if vendor(item[0]['key']) == vendor(key)]
        if same_vendor:
            pool = same_vendor
        lower = max((item for item in pool if item[0]['score'] <= score), key=lambda item: item[0]['score'], default=None)
        upper = min((item for item in pool if item[0]['score'] >= score), key=lambda item: item[0]['score'], default=None)
        if lower and upper and lower[0]['score'] != upper[0]['score']:
            fraction = math.log(score / lower[0]['score']) / math.log(upper[0]['score'] / lower[0]['score'])
            fps = lower[1] * (upper[1] / lower[1]) ** fraction
            chosen = [lower, upper]
        else:
            nearest = min(pool, key=lambda item: abs(math.log(score / item[0]['score'])))
            fps = nearest[1] * (score / nearest[0]['score']) ** .8
            chosen = [nearest]
    derived = any(item[2] for item in chosen) or bool(data.get('high_is_reference_only'))
    sources = [source for item in chosen for source in source_points(item[0], data, mode)]
    notes = ['Опора на опубликованные игровые измерения GPU; CPU вашей сборки оценивается отдельно.']
    if interpolated:
        notes.append('Эта GPU не измерена в наборе: производительность перенесена с ближайших GPU по синтетическому баллу, с учётом производителя при наличии данных.')
    if derived:
        notes.append('Для выбранного разрешения/пресета выполнен пересчёт по исходным тестам. Это расчёт, а не прямой замер на этих настройках.')
    if data.get('archive'):
        notes.append('Архивная версия игры; текущие обновления могут заметно изменить FPS.')
    return {'fps': fps, 'sources': sources, 'interpolated': interpolated, 'derived': derived,
            'spread': .45 if data.get('archive') else .40 if interpolated else .35 if derived else .30,
            'note': ' '.join(notes), 'year': data['year']}

"""Evidence-gated frame-time model built only from licensed native runs.

The model can return an exact measured configuration or interpolate *between*
two measured resolutions for the same CPU/GPU/game/settings cohort. It never
extrapolates hardware performance from PassMark. Such a transfer needs more
independent test series and remains unavailable until that evidence exists.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.services.benchmark_aggregation import aggregate
from app.services.benchmark_data import native_cohort
from app.services.offers import signature

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "measurements.json"
PIXELS = {"720p": 1280 * 720, "1080p": 1920 * 1080,
          "1440p": 2560 * 1440, "4k": 3840 * 2160}
RESOLUTION_ALIASES = {"4k": "4K", "2160p": "4K", "3840x2160": "4K",
                      "1440p": "1440p", "2560x1440": "1440p",
                      "1080p": "1080p", "1920x1080": "1080p",
                      "720p": "720p", "1280x720": "720p"}
CANONICAL_RESOLUTION = {"4K": "4k", "1440p": "1440p", "1080p": "1080p", "720p": "720p"}
DISPLAY_RESOLUTION = {"4k": "4K", "1440p": "1440p", "1080p": "1080p", "720p": "720p"}


@lru_cache(maxsize=1)
def dataset():
    value = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return value["rows"], value.get("sources", [])


@lru_cache(maxsize=1)
def _native_pair_index():
    """Index only native licensed pair rows for fast optimizer evidence checks."""
    rows, _ = dataset()
    return frozenset((_game_key(row.get("game")),
                      _name_key(row.get("cpu"), "CPU"),
                      _name_key(row.get("gpu"), "GPU"),
                      str(row.get("preset") or "").casefold())
                     for row in rows if native_cohort(row)
                     and row.get("cpu") and row.get("gpu"))


def has_native_pair_measurement(cpu_name: str, gpu_name: str, game: str,
                                preset: str = "high") -> bool:
    """Whether this candidate can use pair evidence; this does not imply settings match."""
    return (_game_key(game), _name_key(cpu_name, "CPU"),
            _name_key(gpu_name, "GPU"), str(preset or "").casefold()) in _native_pair_index()


def _name_key(value: str | None, kind: str) -> str:
    return signature(value or "", kind) or ""


def _game_key(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE)


def _ram_generation(value: str | None) -> str | None:
    match = re.match(r"\s*(DDR[345])", value or "", re.I)
    return match.group(1).upper() if match else None


def _resolution_key(value: str | None) -> str | None:
    normalized = str(value or "").casefold().replace("\u00d7", "x").replace(" ", "")
    return RESOLUTION_ALIASES.get(normalized)

def _context(row):
    """Fields held fixed when fitting a frame-time/resolution curve."""
    settings = row.get("settings") if isinstance(row.get("settings"), dict) else row
    return tuple(settings.get(key) for key in (
        "game_version", "ram_gb", "ram_type", "ram_channels", "vram_gb",
        "preset", "rt", "upscaling", "frame_generation", "frame_generation_mode",
        "render_scale", "scene", "overclocked", "os", "form_factor", "power_profile"))


def _source_details(rows):
    return sorted({(r["publisher"], r["source_url"], r["license"], r["attribution"],
                    r.get("observed_date")) for r in rows})


def _evidence(rows, cohort, *, exact: bool, method: str):
    source_details = _source_details(rows)
    series = {row["series_id"] for row in rows}
    publishers = {row["publisher"] for row in rows}
    fps_values = [float(row["average_fps"]) for row in rows]
    low_values = [float(row["one_percent_low"]) for row in rows
                  if row.get("one_percent_low") is not None]
    low_complete = len(low_values) == len(rows) and bool(rows)
    return {
        "status": "measured_reference" if exact else "estimated_interpolation",
        "measurement_type": "measured" if exact else "estimated",
        "average_fps": round(float(cohort["mean_fps"]), 2) if exact else None,
        "one_percent_low": round(float(cohort["one_percent_low_fps"]), 2)
            if exact and cohort.get("one_percent_low_fps") is not None else None,
        "method": method,
        "confidence": "limited" if len(series) < 3 or len(publishers) < 2 else "multi_source",
        "sample_count": len(rows), "independent_series": len(series),
        "independent_publishers": len(publishers),
        "measured_fps_range": ([round(min(fps_values), 2), round(max(fps_values), 2)] if exact else None),
        "one_percent_low_range": ([round(min(low_values), 2), round(max(low_values), 2)]
                                   if exact and low_complete else None),
        "sources": [{"publisher": p, "url": url, "license": license_name,
                     "attribution": attribution, "observed_date": observed_date}
                    for p, url, license_name, attribution, observed_date in source_details],
        "series_ids": sorted(series),
        "settings": cohort["settings"],
        "warnings": (["Это опубликованные измерения той же пары CPU/GPU, а не повторный тест вашего компьютера."]
                     if exact else ["FPS интерполирован по времени кадра между двумя разрешениями одной измеренной связки.",
                                    "Интерполяция не является замером; за пределами измеренных разрешений прогноз не строится."]),
    }


def predict_pair(cpu_name: str, gpu_name: str, game: str, resolution: str,
                 preset: str = "high", ram_type: str | None = None,
                 ram_channels: int | None = None, ram_capacity_gb: int | None = None,
                 rt: bool = False, upscaling: str = "off",
                 frame_generation: bool = False,
                 source_rows: list[dict] | None = None) -> dict:
    """Return an evidence-backed pair result or an explicit abstention.

    Curated data currently covers a single native Windows desktop pair. Keeping
    the matching and interpolation strict prevents a GPU-only number or a
    synthetic score from being presented as the FPS of a full PC.
    """
    unavailable = {
        "status": "insufficient_data", "measurement_type": None,
        "average_fps": None, "one_percent_low": None, "method": "abstain",
        "confidence": "insufficient", "sample_count": 0,
        "independent_series": 0, "independent_publishers": 0,
        "sources": [], "warnings": [],
    }
    if rt or frame_generation or (upscaling or "off").casefold() != "off":
        return {**unavailable, "reason": "The current curated model covers native raster runs only."}
    resolution_key = CANONICAL_RESOLUTION.get(_resolution_key(resolution))
    if not resolution_key or resolution_key not in PIXELS:
        return {**unavailable, "reason": "Unsupported resolution; no conversion or extrapolation is performed."}
    wanted_cpu, wanted_gpu = _name_key(cpu_name, "CPU"), _name_key(gpu_name, "GPU")
    if not wanted_cpu or not wanted_gpu:
        return {**unavailable, "reason": "CPU or GPU could not be normalized to a known model key."}

    raw_rows = source_rows if source_rows is not None else dataset()[0]
    eligible = []
    for raw in raw_rows:
        if not native_cohort(raw) or _game_key(raw["game"]) != _game_key(game):
            continue
        if _name_key(raw.get("cpu"), "CPU") != wanted_cpu or _name_key(raw.get("gpu"), "GPU") != wanted_gpu:
            continue
        if raw["preset"].casefold() != preset.casefold():
            continue
        if ram_type and _ram_generation(raw.get("ram_type")) != ram_type.upper():
            continue
        if ram_channels is not None and raw.get("ram_channels") != ram_channels:
            continue
        if ram_capacity_gb is not None and raw.get("ram_gb") != float(ram_capacity_gb):
            continue
        if _resolution_key(raw.get("resolution")):
            eligible.append(raw)
    if not eligible:
        return {**unavailable, "reason": "Нет лицензированного native игрового измерения этой пары при совместимых настройках."}

    cohorts = aggregate(eligible)
    contexts = {_context(row) for row in cohorts}
    if len(contexts) != 1:
        return {**unavailable, "reason": "Для этой связки найдено несколько несовпадающих тестовых конфигураций; без точных RAM/сцены их нельзя объединить."}

    target_mode = resolution_key
    exact_rows = [row for row in eligible if CANONICAL_RESOLUTION.get(_resolution_key(row["resolution"])) == resolution_key]
    exact_cohorts = [row for row in cohorts if CANONICAL_RESOLUTION.get(_resolution_key(row["settings"].get("resolution"))) == resolution_key]
    if exact_rows and exact_cohorts:
        return _evidence(exact_rows, exact_cohorts[0], exact=True,
                         method="published_pair_measurement")

    by_resolution = {}
    for cohort in cohorts:
        key = _resolution_key(cohort["settings"].get("resolution"))
        if key:
            by_resolution[CANONICAL_RESOLUTION[key]] = cohort
    target_pixels = PIXELS[target_mode]
    lower = [(PIXELS[key], row) for key, row in by_resolution.items() if PIXELS[key] < target_pixels]
    upper = [(PIXELS[key], row) for key, row in by_resolution.items() if PIXELS[key] > target_pixels]
    if not lower or not upper:
        return {**unavailable, "reason": "Целевое разрешение вне диапазона тех же измеренных настроек; экстраполяция запрещена."}
    x0, a = max(lower, key=lambda item: item[0])
    x1, b = min(upper, key=lambda item: item[0])
    if not a.get("mean_fps") or not b.get("mean_fps"):
        return {**unavailable, "reason": "У измерительных опор отсутствует средний FPS."}
    weight = (target_pixels - x0) / (x1 - x0)

    def interpolate_frame_time(fps_a, fps_b):
        if fps_a is None or fps_b is None or fps_a <= 0 or fps_b <= 0:
            return None
        frame_ms = (1000 / fps_a) * (1 - weight) + (1000 / fps_b) * weight
        return 1000 / frame_ms

    fps = interpolate_frame_time(a["mean_fps"], b["mean_fps"])
    low = interpolate_frame_time(a.get("one_percent_low_fps"), b.get("one_percent_low_fps"))
    lower_key = CANONICAL_RESOLUTION[_resolution_key(a["settings"]["resolution"])]
    upper_key = CANONICAL_RESOLUTION[_resolution_key(b["settings"]["resolution"])]
    anchor_rows = [row for row in eligible
                   if CANONICAL_RESOLUTION.get(_resolution_key(row["resolution"])) in {lower_key, upper_key}]
    settings = dict(a["settings"])
    settings["resolution"] = DISPLAY_RESOLUTION[target_mode]
    settings["average_fps"] = round(fps, 2)
    settings["one_percent_low_fps"] = round(low, 2) if low is not None else None
    settings["interpolation_anchors"] = [lower_key, upper_key]
    aggregate_row = {"settings": settings, "mean_fps": fps,
                     "one_percent_low_fps": low}
    result = _evidence(anchor_rows, aggregate_row, exact=False,
                       method="same_pair_frame_time_interpolation")
    result["average_fps"] = round(fps, 2)
    result["one_percent_low"] = round(low, 2) if low is not None else None
    result["interpolation"] = {"target_resolution": resolution_key,
        "anchors": [{"resolution": DISPLAY_RESOLUTION[lower_key], "average_fps": a["mean_fps"],
                     "one_percent_low": a.get("one_percent_low_fps")},
                    {"resolution": DISPLAY_RESOLUTION[upper_key], "average_fps": b["mean_fps"],
                     "one_percent_low": b.get("one_percent_low_fps")}],
        "interpolation_weight": round(weight, 6),
        "formula": "linear interpolation of frame time (1000 / FPS) by pixel count"}
    return result


def cpu_comparison_coverage(source_rows: list[dict] | None = None) -> dict:
    """Count like-for-like CPU variants; necessary, but insufficient, to calibrate CPU frame time."""
    raw_rows = source_rows if source_rows is not None else dataset()[0]
    eligible = [row for row in raw_rows if native_cohort(row)]
    groups = {}
    for row in eligible:
        settings = row.get("settings") if isinstance(row.get("settings"), dict) else row
        resolution_key = CANONICAL_RESOLUTION.get(_resolution_key(row.get("resolution")))
        key = (_game_key(row.get("game")), row.get("game_version"),
               _name_key(row.get("gpu"), "GPU"), resolution_key,
               _context(row), settings.get("scene"), settings.get("driver"))
        group = groups.setdefault(key, {"cpus": set(), "series": set(), "rows": 0})
        group["cpus"].add(_name_key(row.get("cpu"), "CPU"))
        group["series"].add(row.get("series_id"))
        group["rows"] += 1
    comparable = [group for group in groups.values() if len(group["cpus"]) >= 2]
    return {
        "eligible_native_observations": len(eligible),
        "fixed_gpu_settings_groups": len(groups),
        "groups_with_multiple_cpu_models": len(comparable),
        "games_with_multiple_cpu_models": len({key[0] for key, value in groups.items()
                                                  if len(value["cpus"]) >= 2}),
        "cpu_models_in_comparable_groups": len({cpu for group in comparable for cpu in group["cpus"]}),
        "independent_series_in_comparable_groups": len({series for group in comparable for series in group["series"]}),
        "calibrated_cpu_frame_time_games": 0,
        "calibrated": False,
        "reason": "No calibrated game-specific CPU frame-time curve is available. Matched CPU variation alone cannot separate CPU time from a GPU-limited result.",
    }


def model_coverage() -> dict:
    """Summarize actual pair-level data coverage for user-facing honesty."""
    raw_rows, sources = dataset()
    eligible = [row for row in raw_rows if native_cohort(row)]
    normalized_pairs = {(_game_key(row["game"]), _name_key(row["cpu"], "CPU"),
                         _name_key(row["gpu"], "GPU")) for row in eligible}
    resolution_groups = {}
    for row in eligible:
        key = CANONICAL_RESOLUTION.get(_resolution_key(row.get("resolution")))
        if key:
            item = resolution_groups.setdefault(key, {"observations": 0, "games": set()})
            item["observations"] += 1
            item["games"].add(_game_key(row["game"]))
    return {"dataset_observations": len(raw_rows), "native_pair_observations": len(eligible),
            "games": len({_game_key(row["game"]) for row in eligible}),
            "cpu_models": len({_name_key(row["cpu"], "CPU") for row in eligible}),
            "gpu_models": len({_name_key(row["gpu"], "GPU") for row in eligible}),
            "paired_configurations": len(normalized_pairs),
            "resolution_coverage": {DISPLAY_RESOLUTION[key]: {"observations": value["observations"], "games": len(value["games"])}
                                    for key, value in sorted(resolution_groups.items())},
            "cpu_comparison_coverage": cpu_comparison_coverage(raw_rows),
            "sources": sources,
            "cpu_gpu_curves_calibrated": False,
            "reason": "No calibrated CPU/GPU frame-time decomposition is available; paired measurements support only their tested configuration and controlled same-pair resolution interpolation."}

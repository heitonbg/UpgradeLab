"""GPU-oriented FPS estimates from the pinned PCGameBenchmarks snapshot.

All imported FPS points are external model estimates, never measured FPS.
"""
from __future__ import annotations

import json
import math
import re
from bisect import bisect_left
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

from app.services.hardware_matching import model_key

_DATA_PATH = (Path(__file__).resolve().parents[1] / "data" / "external_fps" /
              "pcgamebenchmarks" / "profiles.json")
_MOBILE = re.compile(r"\b(?:laptop|mobile|max[ -]?q|notebook)\b|\b(?:gt|gtx|rtx|rx)\s*\d+(?:\s*(?:xt|ti|super))?\s*m\b|\b(?:geforce\s+)?mx\d+\b|\bgeforce\s+\d{3,4}m\b|\bradeon\s+(?:hd|r[3579])\s*\d+[a-z]*m\b", re.I)
_INTEGRATED = re.compile(r"\bintel\s+(?:iris|uhd|hd)\b|\bintel\s+arc\s+\d{3}[vt]\b|\biris\s+xe\b|\bvega\s*\d+\s+graphics\b|\bradeon\s+(?:660m|680m|740m|760m|780m|840m|860m|880m|890m|graphics|vega\s*\d+|(?:hd|r[3579])\s*\d+[a-z]*d|(?:8040|8050|8060|8065)[a-z]*)\b|\bradeon\s+(?:rx\s+)?vega(?:\s+\d+)?\s+ryzen\b.*\b\d{4,5}(?:hs|ge|gt|u|h|g)\b|\bradeon\s+reno(ir)?\b.*\b\d{4,5}(?:hs|ge|gt|u|h|g)\b|\bradeon\s+r[357]\s+(?:(?:graphics|pro)\s+)?a\d{1,2}-\d{4,5}[a-z]?\b|\bradeon(?:t)?\s+ryzen\b.*\b(?:embedded|\d{4,5}(?:u|h|hs|g|ge|gt))\b|\b(?:qualcomm\s+)?adreno\s+(?:x\d[-\w]*|gpu)\b|\bapu\b", re.I)
_WORKSTATION = re.compile(r"\b(?:quadro|firepro|radeon\s+(?:ai\s+)?pro|radeon\s+instinct|rtx\s*(?:a\d+|pro\b|6000(?:\s*ada)?|5000\s*ada)|rtx6000|arc\s+pro\b|nvidia\s+(?:a100|a10g|a40|a16|l\d{2})|nvidia\s+t\d{3,4}|\b(?:a100|a10g|a40|a16|l40s?)\b)\b", re.I)
_DISCRETE = re.compile(r"\b(?:geforce(?:\s*\d+(?:\s*(?:mx|ti|ultra))?)?|nvidia\s+(?:gt|gtx|rtx)|gtx|rtx|titan\s+[a-z0-9]+|radeon\s+(?:rx\s*vega\s*\d+|rx\s*\d+[a-z0-9]*|hd\s*\d+[a-z0-9]*|x\d{3,4}|(?:7500|9000|9200|9250|9500|9550|9600|9700|9800)|r[3579]\s*\d+[a-z0-9]*|r9\s+fury(?:\s+x)?|vii\b|vega\s+frontier)|intel\s+arc\s+[ab]\d+[a-z0-9]*)\b|\bmoore\s+threads\s+mtt\s+s\d+\b", re.I)
_NON_RENDERING_DISPLAY = re.compile(r"\b(?:usb\s+display|displaylink(?:\s+usb)?\s+(?:device|adapter|driver)|display\s+(?:adapter|device|driver)|sharing\s+monitor|idd\s+(?:device|driver)|anyvieweridd\w*|horizon\s+indirect\s+display|indirect\s+display|mirror\s+driver|video\s+hook\s+driver|projector\s+support\s+driver|sqextframebuffer\w*|ice\s+display\s+wddm\s+driver|winsta0|turr?zx\s+display|macro[s]?ilicon\s+usb|aicusbdisplay|cxdisplay|mridd\w*)\b", re.I)
_VIRTUALIZED = re.compile(r"\b(?:nvidia\s+)?(?:grid(?:\s+rtx)?|mxgpu|mtvgpu|titangpu)\b|\b(?:a\d{1,2}|l\d{1,2})-\d+(?:q|b)\b|\brtx\s*\d+\s*ada(?:\s+generation)?-\d+(?:q|b)\b|\b(?:rtx\d+-ada|v\d+)-\d+q\b", re.I)


@lru_cache(maxsize=1)
def package() -> dict[str, Any]:
    document = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    source = document.get("source") or {}
    if source.get("license") != "CC BY 4.0" or source.get("data_type") != "external_model_estimate":
        raise RuntimeError("PCGameBenchmarks package provenance is invalid")
    if len(document.get("reference_gpus") or []) != 12:
        raise RuntimeError("PCGameBenchmarks package must carry all 12 reference GPUs")
    if len(document.get("gpu_catalog") or []) != int(source.get("source_gpu_rows") or 0):
        raise RuntimeError("PCGameBenchmarks package must carry its complete GPU catalog")
    return document


@lru_cache(maxsize=1)
def profiles_by_id() -> dict[str, dict[str, Any]]:
    return {str(item["game_id"]): item for item in package().get("profiles", [])}


@lru_cache(maxsize=1)
def _gpu_rows_by_key() -> dict[str, tuple[dict[str, Any], ...]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for item in package().get("gpu_catalog", []):
        index.setdefault(model_key(item.get("name", "")), []).append(item)
    return {key: tuple(rows) for key, rows in index.items() if key}


def gpu_device_class(name: str, vram_gb: int | float | None = None) -> str:
    """Classify only from model-name evidence; VRAM size is not a form-factor signal."""
    label = str(name or "")
    if _NON_RENDERING_DISPLAY.search(label):
        return "non_rendering"
    if _VIRTUALIZED.search(label):
        return "virtualized"
    if _INTEGRATED.search(label):
        return "integrated"
    if _MOBILE.search(label):
        return "mobile"
    if _WORKSTATION.search(label):
        return "workstation"
    if _DISCRETE.search(label):
        return "desktop"
    return "unknown"


def match_source_gpu(name: str, device_class: str) -> dict[str, Any]:
    """Match an exact normalized model and retain source device type.

    We never remove laptop/mobile markers, never resolve ambiguous rows by
    choosing the first, and never reinterpret an Unknown source row as Desktop.
    """
    key = model_key(str(name or ""))
    candidates = list(_gpu_rows_by_key().get(key, ())) if key else []
    if not candidates:
        return {"status": "no_exact_source_model", "candidates": []}
    expected_types = ({"Desktop"} if device_class == "desktop" else
                      {"Mobile"} if device_class == "mobile" else
                      {"Mobile", "Unknown"} if device_class == "integrated" else set())
    if expected_types:
        typed = [row for row in candidates if row.get("source_device_type") in expected_types]
        if len(typed) == 1:
            item = typed[0]
            return {"status": "exact_source_model_and_device_type", **item}
        if len(typed) > 1:
            return {"status": "ambiguous_source_model", "candidates": candidates}
    if len(candidates) == 1:
        item = candidates[0]
        source_type = str(item.get("source_device_type") or "Unknown")
        if "," in source_type:
            return {"status": "ambiguous_source_device_type", "candidates": candidates,
                    "source_device_type": source_type}
        if source_type in {"Desktop", "Mobile", "Workstation"} and device_class != "workstation":
            return {"status": "source_device_type_conflict", "candidates": candidates,
                    "source_device_type": source_type}
        return {"status": "source_device_type_unknown", "candidates": candidates}
    return {"status": "ambiguous_source_model", "candidates": candidates}


def _points(profile: dict[str, Any], device_class: str) -> list[dict[str, Any]]:
    point_values = profile.get("fps_by_reference_gpu") or {}
    return sorted(
        [anchor | {"fps": point_values.get(anchor["name"])}
         for anchor in package()["reference_gpus"]
         if anchor.get("device_class") == device_class and point_values.get(anchor["name"]) is not None],
        key=lambda point: float(point.get("g3d_mark") or 0),
    )


def _minimum_log_curve_elasticity(points: list[dict[str, Any]], fps_cap: float) -> float | None:
    """Return a conservative log-slope lower bound for the capped GPU curve."""
    valid = []
    for point in points:
        score = point.get("g3d_mark")
        fps = point.get("fps")
        if (isinstance(score, (int, float)) and not isinstance(score, bool)
                and isinstance(fps, (int, float)) and not isinstance(fps, bool)
                and math.isfinite(float(score)) and math.isfinite(float(fps))
                and score > 0 and fps > 0):
            valid.append((float(score), min(float(fps), float(fps_cap))))
    valid.sort()
    if len(valid) < 2:
        return None
    slopes = []
    for (left_score, left_fps), (right_score, right_fps) in zip(valid, valid[1:]):
        if right_score <= left_score or right_fps < left_fps:
            return None
        slopes.append((math.log(right_fps) - math.log(left_fps)) /
                      (math.log(right_score) - math.log(left_score)))
    return max(0.0, min(slopes)) if slopes else None

def _interpolate_log(points: list[dict[str, Any]], score: float) -> tuple[float | None, list[dict[str, Any]], str]:
    points = [point for point in points if float(point.get("g3d_mark") or 0) > 0 and
              float(point.get("fps") or 0) > 0 and math.isfinite(float(point["fps"]))]
    if len(points) < 2 or any(float(points[i]["fps"]) > float(points[i + 1]["fps"])
                              for i in range(len(points) - 1)):
        return None, [], "invalid_or_insufficient_reference_curve"
    scores = [float(point["g3d_mark"]) for point in points]
    position = bisect_left(scores, score)
    if position < len(scores) and math.isclose(scores[position], score, rel_tol=0.005):
        return float(points[position]["fps"]), [points[position]], "reference_gpu_score_match"
    outside = score < scores[0] or score > scores[-1]
    if score < scores[0]:
        if score < scores[0] * 0.5:
            return None, [], "below_safe_reference_range"
        lower, upper = points[0], points[1]
    elif score > scores[-1]:
        if score > scores[-1] * 1.25:
            return None, [], "above_safe_reference_range"
        lower, upper = points[-2], points[-1]
    else:
        lower, upper = points[position - 1], points[position]
    x0, x1 = math.log(float(lower["g3d_mark"])), math.log(float(upper["g3d_mark"]))
    y0, y1 = math.log(float(lower["fps"])), math.log(float(upper["fps"]))
    ratio = (math.log(score) - x0) / (x1 - x0)
    value = math.exp(y0 + ratio * (y1 - y0))
    return value, [lower, upper], "bounded_log_extrapolation" if outside else "piecewise_log_score_interpolation"


def estimate_gpu_fps(game_id: str, gpu_name: str, g3d_score: int | float | None,
                     vram_gb: int | float | None = None, *, resolution: str = "1080p",
                     preset: str = "high", rt: bool = False, upscaling: str = "off",
                     frame_generation: bool = False) -> dict[str, Any]:
    """Return a labeled GPU-only estimate or a reason to abstain."""
    profile = profiles_by_id().get(str(game_id))
    if profile is None:
        return {"available": False, "reason": "no_matched_external_game_profile"}
    source = package()["source"]
    settings_ok = (str(resolution).casefold() == "1080p" and str(preset).casefold() == "high"
                   and rt is False and str(upscaling).casefold() == "off" and not frame_generation)
    context = {
        "available": True,
        "data_type": "external_model_estimate",
        "source_name": "PCGameBenchmarks",
        "source_url": profile.get("source_url"),
        "dataset_url": source.get("repository"),
        "dataset_revision": source.get("git_revision"),
        "snapshot_date": source.get("snapshot_date"),
        "license": source.get("license"),
        "attribution": source.get("attribution"),
        "source_game_name": profile.get("source_game_name"),
        "source_game_id": profile.get("steam_app_id"),
        "source_settings": {"resolution": "1080p", "preset": "High", "rt": False,
                             "upscaling": "off", "frame_generation": False},
    }
    if not settings_ok:
        return {**context, "fps": None,
                "reason": "external_source_covers_only_1080p_high_native_without_rt_or_frame_generation"}
    device_class = gpu_device_class(gpu_name, vram_gb)
    match = None
    if device_class == "non_rendering":
        return {**context, "fps": None, "reason": "non_rendering_display_adapter", "device_class": device_class}
    if device_class == "virtualized":
        return {**context, "fps": None, "reason": "virtualized_gpu_has_no_matching_reference_curve", "device_class": device_class}
    if device_class in {"mobile", "workstation"}:
        reason = "no_separate_mobile_reference_curve" if device_class == "mobile" else "no_workstation_reference_curve"
        return {**context, "fps": None, "reason": reason, "device_class": device_class}
    if device_class == "unknown":
        if not _NON_RENDERING_DISPLAY.search(str(gpu_name or "")):
            exact = match_source_gpu(gpu_name, device_class)
            candidate = (exact.get("candidates") or [None])[0]
            if candidate and candidate.get("source_device_type") in {"Desktop", "Mobile", "Workstation"}:
                device_class = {"Desktop": "desktop", "Mobile": "mobile",
                                "Workstation": "workstation"}[candidate["source_device_type"]]
                match = {"status": "exact_source_model_device_type_inferred",
                         **candidate, "inference_note": "Exact normalized model and explicit PCGameBenchmarks source device type."}
            else:
                return {**context, "fps": None, "reason": "gpu_device_class_is_unknown", "device_class": device_class}
        else:
            return {**context, "fps": None, "reason": "gpu_device_class_is_unknown", "device_class": device_class}
    if device_class in {"mobile", "workstation"}:
        reason = "no_separate_mobile_reference_curve" if device_class == "mobile" else "no_workstation_reference_curve"
        return {**context, "fps": None, "reason": reason, "device_class": device_class,
                "gpu_match": match}
    if match is None:
        match = match_source_gpu(gpu_name, device_class)

    score = g3d_score
    score_provenance = {"source": "UpgradeLab Hardware.raw_score", "metric": "PassMark G3D Mark",
                        "crosswalk": match["status"]}
    if match["status"] == "exact_source_model_and_device_type":
        source_score = match.get("g3d_mark")
        if isinstance(source_score, (int, float)) and source_score > 0:
            score = source_score
            score_provenance = {"source": "PCGameBenchmarks gpus.csv", "metric": "PassMark G3D Mark",
                                "crosswalk": match["status"], "source_gpu_name": match.get("name"),
                                "source_device_type": match.get("source_device_type"),
                                "source_url": match.get("page_url"), "g3d_mark": source_score}
    elif match["status"] == "exact_source_model_device_type_inferred":
        source_score = match.get("g3d_mark")
        if isinstance(source_score, (int, float)) and source_score > 0:
            score = source_score
            score_provenance = {"source": "PCGameBenchmarks gpus.csv", "metric": "PassMark G3D Mark",
                                "crosswalk": match["status"], "source_gpu_name": match.get("name"),
                                "source_device_type": match.get("source_device_type"),
                                "source_url": match.get("page_url"), "g3d_mark": source_score,
                                "note": match.get("inference_note")}
    elif match["status"] == "source_device_type_conflict":
        return {**context, "fps": None, "reason": "exact_source_gpu_device_type_conflicts_with_target_name",
                "device_class": device_class, "gpu_match": match}
    elif match["status"] == "ambiguous_source_device_type":
        return {**context, "fps": None, "reason": "exact_source_gpu_has_mixed_device_types",
                "device_class": device_class, "gpu_match": match}
    if not isinstance(score, (int, float)) or not math.isfinite(float(score)) or score <= 0:
        return {**context, "fps": None, "reason": "missing_comparable_gpu_g3d_score",
                "device_class": device_class, "gpu_match": match}
    points = _points(profile, device_class)
    if len(points) < 2:
        return {**context, "fps": None, "reason": f"insufficient_{device_class}_reference_points"}
    fps, used, method = _interpolate_log(points, float(score))
    if fps is None:
        return {**context, "fps": None, "reason": method, "device_class": device_class,
                "target_g3d_score": float(score), "gpu_match": match,
                "gpu_score_provenance": score_provenance}
    cap = profile.get("engine_fps_cap")
    caps = [360.0]
    if isinstance(cap, (int, float)) and cap > 0:
        caps.append(float(cap))
    effective_fps_cap = min(caps)
    fps = max(1.0, min(float(fps), effective_fps_cap))
    curve_elasticity = _minimum_log_curve_elasticity(points, effective_fps_cap)
    outside = method == "bounded_log_extrapolation"
    integrated = device_class == "integrated"
    return {
        **context,
        "fps": int(round(fps)),
        "unrounded_fps": round(fps, 3),
        "device_class": device_class,
        "method": method,
        "confidence": "very_low" if outside or integrated or match["status"] not in {
            "exact_source_model_and_device_type"} else "low",
        "target_gpu": str(gpu_name),
        "target_g3d_score": float(score),
        "gpu_match": {"status": match["status"], "source_gpu_name": match.get("name"),
                      "source_device_type": match.get("source_device_type"), "source_url": match.get("page_url")},
        "gpu_score_provenance": score_provenance,
        "reference_points": [{"gpu": point["name"], "g3d_mark": point["g3d_mark"],
                              "fps": point["fps"]} for point in used],
        "engine_fps_cap": cap,
        "min_curve_log_elasticity": (round(curve_elasticity, 6)
                                      if curve_elasticity is not None else None),
        "reason": None,
    }


def estimate_nearest_game_gpu_anchor(game_id: str, gpu_name: str,
                                    g3d_score: int | float | None,
                                    vram_gb: int | float | None = None) -> dict[str, Any]:
    """Return the nearest same-class published anchor, never extrapolate it as target GPU FPS."""
    profile = profiles_by_id().get(str(game_id))
    if profile is None:
        return {"available": False, "reason": "no_matched_external_game_profile"}
    if not _positive_number(g3d_score):
        return {"available": False, "reason": "missing_positive_passmark_g3d_score"}
    device_class = gpu_device_class(gpu_name, vram_gb)
    if device_class not in {"desktop", "integrated"}:
        return {"available": False, "reason": "nearest_game_anchor_requires_desktop_or_integrated_gpu"}
    points = _points(profile, device_class)
    if not points:
        return {"available": False, "reason": "no_game_anchor_for_gpu_class"}
    anchor = min(points, key=lambda point: abs(math.log(float(g3d_score) / float(point["g3d_mark"]))))
    source = package()["source"]
    value = float(anchor["fps"])
    cap = profile.get("engine_fps_cap")
    if isinstance(cap, (int, float)) and cap > 0:
        value = min(value, float(cap))
    value = min(value, 360.0)
    return {
        "available": True, "fps": int(round(value)), "unrounded_fps": round(value, 3),
        "data_type": "external_model_estimate", "source_name": "PCGameBenchmarks",
        "source_url": profile.get("source_url"), "dataset_url": source.get("repository"),
        "dataset_revision": source.get("git_revision"), "snapshot_date": source.get("snapshot_date"),
        "license": source.get("license"), "attribution": source.get("attribution"),
        "source_game_name": profile.get("source_game_name"), "source_game_id": profile.get("steam_app_id"),
        "target_gpu": gpu_name, "target_g3d_score": float(g3d_score),
        "nearest_reference_gpu": anchor["name"], "nearest_reference_g3d_mark": anchor["g3d_mark"],
        "device_class": device_class,
        "source_settings": {"resolution": "1080p", "preset": "High", "rt": False,
                             "upscaling": "off", "frame_generation": False},
        "confidence": "very_low",
        "note": (f"Показана точка {anchor['name']} из таблицы {profile.get('source_game_name')}; "
                 "это не перенос на выбранную видеокарту и не FPS CPU/GPU-системы."),
    }



def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


@lru_cache(maxsize=512)
@lru_cache(maxsize=256)
def estimate_catalog_gpu_reference(gpu_name: str, g3d_score: float, vram_gb: float | None = None) -> dict[str, Any]:
    """Return a source-derived broad GPU reference when a title curve is absent.

    The median and 10th/90th percentiles are across different catalog games,
    not a prediction interval for the selected title. If the selected GPU score
    falls outside the source's supported range, use the nearest reference GPU
    without pretending it is the selected model.
    """
    requested_class = gpu_device_class(gpu_name, vram_gb)
    if requested_class in {"non_rendering", "virtualized"}:
        return {"available": False, "reason": "gpu_class_has_no_physical_rendering_reference"}
    score_provenance = {"source": "UpgradeLab Hardware.raw_score", "metric": "PassMark G3D Mark"}
    if not _positive_number(g3d_score):
        exact_match = match_source_gpu(gpu_name, requested_class)
        if (exact_match.get("status") != "exact_source_model_and_device_type"
                or not _positive_number(exact_match.get("g3d_mark"))):
            return {"available": False, "reason": "missing_positive_passmark_g3d_score",
                    "gpu_match": exact_match}
        g3d_score = float(exact_match["g3d_mark"])
        score_provenance = {
            "source": "PCGameBenchmarks gpus.csv", "metric": "PassMark G3D Mark",
            "crosswalk": exact_match.get("status"), "source_gpu_name": exact_match.get("name"),
            "source_device_type": exact_match.get("source_device_type"),
            "source_url": exact_match.get("page_url"), "g3d_mark": g3d_score,
        }
    device_class = requested_class if requested_class in {"desktop", "integrated"} else "desktop"
    profiles = package().get("profiles", [])
    values: list[float] = []
    for profile in profiles:
        points = _points(profile, device_class)
        fps, _, _ = _interpolate_log(points, float(g3d_score))
        if fps is None:
            continue
        cap = profile.get("engine_fps_cap")
        effective_cap = min(360.0, float(cap)) if isinstance(cap, (int, float)) and cap > 0 else 360.0
        values.append(max(1.0, min(float(fps), effective_cap)))

    scope = "same_gpu_population_median_by_game"
    nearest_gpu = None
    if len(values) < 100:
        anchors = [item for item in package().get("reference_gpus", [])
                   if item.get("device_class") == device_class and _positive_number(item.get("g3d_mark"))]
        if not anchors:
            anchors = [item for item in package().get("reference_gpus", [])
                       if item.get("device_class") == "desktop" and _positive_number(item.get("g3d_mark"))]
            device_class = "desktop"
        if not anchors:
            return {"available": False, "reason": "no_catalog_reference_gpu_for_device_class"}
        anchor = min(anchors, key=lambda item: abs(math.log(float(g3d_score) / float(item["g3d_mark"]))))
        nearest_gpu = anchor.get("name")
        values = []
        for profile in profiles:
            value = (profile.get("fps_by_reference_gpu") or {}).get(nearest_gpu)
            if not _positive_number(value):
                continue
            cap = profile.get("engine_fps_cap")
            effective_cap = min(360.0, float(cap)) if isinstance(cap, (int, float)) and cap > 0 else 360.0
            values.append(max(1.0, min(float(value), effective_cap)))
        scope = "nearest_reference_gpu_population_median_by_game"
    if not values:
        return {"available": False, "reason": "no_catalog_gpu_fps_values"}

    source = package()["source"]
    notes = ["Это широкий ориентир по распределению игр в каталоге, не FPS выбранной игры или всей системы."]
    if nearest_gpu:
        notes.append(f"Для выбранной карты показана медиана ближайшей опорной видеокарты {nearest_gpu}; производительность конкретной модели не рассчитана.")
    if requested_class not in {"desktop", "integrated"}:
        notes.append(f"Для класса видеокарты {requested_class} отдельной кривой нет; показан общий ориентир настольной видеокарты.")
    return {
        "available": True, "fps": int(round(median(values))), "unrounded_fps": round(median(values), 3),
        "fps_range": [round(_quantile(values, 0.10), 1), round(_quantile(values, 0.90), 1)],
        "range_type": "catalog_game_population_percentiles_not_prediction_interval",
        "sample_count": len(values), "scope": scope, "nearest_reference_gpu": nearest_gpu,
        "target_gpu": gpu_name, "device_class": requested_class, "curve_device_class": device_class,
        "target_g3d_score": float(g3d_score), "gpu_score_provenance": score_provenance,
        "data_type": "external_model_estimate", "source_name": "PCGameBenchmarks",
        "source_url": source.get("repository"), "dataset_url": source.get("repository"),
        "dataset_revision": source.get("git_revision"), "snapshot_date": source.get("snapshot_date"),
        "license": source.get("license"), "attribution": source.get("attribution"),
        "source_settings": {"resolution": "1080p", "preset": "High", "rt": False,
                             "upscaling": "off", "frame_generation": False},
        "confidence": "very_low", "note": " ".join(notes),
    }


def _positive_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) > 0)

def external_game_coverage() -> dict[str, int]:
    document = package()
    profiles = document.get("profiles", [])
    return {
        "games_with_external_model_estimate": len(profiles),
        "external_estimate_records": sum(len(item.get("fps_by_reference_gpu") or {}) for item in profiles),
        "reference_gpus": len(document["reference_gpus"]),
        "source_gpu_catalog_rows": len(document["gpu_catalog"]),
    }

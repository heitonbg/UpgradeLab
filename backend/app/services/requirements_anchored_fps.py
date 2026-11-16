"""Experimental CPU correction anchored to exact published game requirements.

This module never converts its scenario into measured or calibrated FPS. It
uses the PCGameBenchmarks external GPU estimate as the GPU-only baseline and
PassMark total CPU/G3D marks only as relative hardware features.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from statistics import median
from typing import Any, Iterable
from collections.abc import Mapping

from app.services.cpu_requirements import resolve_cpu_requirement
from app.services.external_fps_model import package
from app.services.hardware_matching import model_key

MODEL_VERSION = "requirements_anchored_v1_experimental"
DEFAULT_ALPHA = 0.25
DEFAULT_ETA = 0.75
DEFAULT_MIN_FACTOR = 0.40
SENSITIVITY_ALPHA = (0.15, 0.25, 0.35)
SENSITIVITY_ETA = (0.50, 0.75, 1.00)
SENSITIVITY_MIN_FACTOR = (0.30, 0.40, 0.50)

_VRAM = re.compile(r"(?<![a-z0-9])(\d+)\s*gb(?:\s+vram)?\b", re.I)
_ALT_SPLIT = re.compile(
    r"\s+(?:or|and)\s+|\s*/\s*|\s*[;|]\s*|\s*,\s*(?=(?:nvidia|amd|intel|geforce|radeon|arc|gtx|rtx|rx\b))",
    re.I,
)


def _positive_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) and score > 0 else None


def _rows(items: Iterable[Any], expected_type: str) -> list[dict[str, Any]]:
    result = []
    for item in items or ():
        if isinstance(item, Mapping):
            kind = str(item.get("type") or "").upper()
            name = str(item.get("name") or "").strip()
            score = _positive_score(item.get("raw_score"))
            item_id = item.get("id")
        else:
            kind = str(getattr(item, "type", "") or "").upper()
            name = str(getattr(item, "name", "") or "").strip()
            score = _positive_score(getattr(item, "raw_score", None))
            item_id = getattr(item, "id", None)
        if kind and kind != expected_type:
            continue
        if name and score is not None:
            result.append({"id": item_id, "name": name, "score": score})
    return result


def _explicit_vram(name: str) -> int | None:
    match = _VRAM.search(name)
    return int(match.group(1)) if match else None


def resolve_gpu_requirement(text: str | None, gpu_catalog: Iterable[Any]) -> dict[str, Any]:
    """Resolve every listed GPU alternative to an exact local model.

    Broad families, "or equivalent", unsupported names, and VRAM variants not
    written into the catalog model name are left unresolved. Hardware.vram is
    intentionally not used here because its legacy values are not reliable.
    """
    raw = str(text or "").strip()
    if not raw:
        return {"status": "missing_requirement", "resolved_models": [],
                "unresolved_models": [], "reference_gpu_mark": None,
                "reference_gpu_mark_range": None}
    normalized = re.sub(
        r"(\d+\s*gb(?:\s+vram)?)\s+or\s+more\b", r"\1 MIN_VRAM", raw, flags=re.I
    )
    catalog_rows = _rows(gpu_catalog, "GPU")
    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in catalog_rows:
        by_key.setdefault(model_key(_VRAM.sub("", row["name"])), []).append(row)

    tokens = [part.strip(" \t\r\n.,()[]{}") for part in _ALT_SPLIT.split(normalized) if part.strip(" \t\r\n.,()[]{}")]
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    seen: set[tuple[str, int | None, bool]] = set()
    for token in tokens:
        minimum_vram = "MIN_VRAM" in token
        vram_match = _VRAM.search(token)
        required_vram = int(vram_match.group(1)) if vram_match else None
        model_text = re.sub(r"\bMIN_VRAM\b", "", token, flags=re.I)
        model_text = re.sub(r"\bwith\s+", "", model_text, flags=re.I)
        model_text = _VRAM.sub("", model_text)
        model_text = re.sub(r"\b(?:graphics|video)\s+card\b|\bGPU\b", "", model_text, flags=re.I)
        key = model_key(model_text)
        signature = (key, required_vram, minimum_vram)
        if signature in seen:
            continue
        seen.add(signature)
        candidates = list(by_key.get(key, ())) if key else []
        if required_vram is not None:
            candidates = [row for row in candidates
                          if _explicit_vram(row["name"]) is not None
                          and (_explicit_vram(row["name"]) >= required_vram if minimum_vram
                               else _explicit_vram(row["name"]) == required_vram)]
        elif len({variant for row in candidates
                  if (variant := _explicit_vram(row["name"])) is not None}) > 1:
            unresolved.append({"token": token, "reason": "ambiguous_vram_variant_in_catalog"})
            continue
        if not candidates:
            unresolved.append({"token": token,
                               "reason": "exact_model_or_vram_variant_not_in_catalog"})
            continue
        scores = [row["score"] for row in candidates]
        chosen = min(candidates, key=lambda row: (len(row["name"]), row["name"].casefold(), row["id"] or 0))
        resolved.append({"id": chosen["id"], "name": chosen["name"],
                         "g3d_mark": float(median(scores)),
                         "g3d_mark_range": [float(min(scores)), float(max(scores))],
                         "catalog_entry_count": len(candidates), "matched_token": token,
                         "match_type": "exact_catalog_model"})

    if resolved and unresolved:
        status = "partially_resolved"
    elif resolved:
        status = "resolved_exact_models"
    else:
        status = "unmatched"
    all_scores = [score for item in resolved for score in item["g3d_mark_range"]]
    centers = [item["g3d_mark"] for item in resolved]
    return {
        "status": status,
        "resolved_models": resolved,
        "unresolved_models": unresolved,
        "reference_gpu_mark": float(median(centers)) if centers else None,
        "reference_gpu_mark_range": [min(all_scores), max(all_scores)] if all_scores else None,
        "match_confidence": "high" if status == "resolved_exact_models" else "none" if not resolved else "low",
        "match_provenance": "Exact normalized GPU SKU and PassMark G3D Mark from the local Hardware catalog; explicit VRAM variants must be present in the model name.",
    }


def minimum_log_curve_elasticity(profile: dict[str, Any], device_class: str = "desktop") -> float | None:
    """Conservative lower bound for d(log GPU FPS)/d(log PassMark G3D).

    Uses all licensed reference anchors and the effective FPS cap. A flat
    segment yields zero, which disables unsubstantiated CPU/GPU balancing.
    """
    values = profile.get("fps_by_reference_gpu") or {}
    points = []
    for anchor in package().get("reference_gpus", []):
        if anchor.get("device_class") != device_class:
            continue
        score = _positive_score(anchor.get("g3d_mark"))
        fps = _positive_score(values.get(anchor.get("name")))
        if score is not None and fps is not None:
            points.append((score, fps))
    points.sort()
    if len(points) < 2:
        return None
    fps_cap = 360.0
    source_cap = _positive_score(profile.get("engine_fps_cap"))
    if source_cap is not None:
        fps_cap = min(fps_cap, source_cap)
    capped = [(score, min(fps, fps_cap)) for score, fps in points]
    slopes = []
    for (left_score, left_fps), (right_score, right_fps) in zip(capped, capped[1:]):
        if right_score <= left_score or right_fps < left_fps:
            return None
        slopes.append((math.log(right_fps) - math.log(left_fps)) /
                      (math.log(right_score) - math.log(left_score)))
    return max(0.0, min(slopes)) if slopes else None


def _scenario(gpu_fps: float, cpu_score: float, gpu_score: float,
              reference_cpu: float, reference_gpu: float,
              alpha: float, eta: float, minimum_factor: float,
              curve_elasticity: float | None) -> tuple[float, float]:
    r_cpu = cpu_score / reference_cpu
    r_gpu = gpu_score / reference_gpu
    eta_effective = min(eta, curve_elasticity / alpha) if curve_elasticity is not None and alpha > 0 else 0.0
    eta_effective = max(0.0, eta_effective)
    r_balance = r_cpu / (r_gpu ** eta_effective)
    cpu_factor = min(1.0, max(minimum_factor, r_balance ** alpha))
    return gpu_fps * cpu_factor, eta_effective


def estimate_requirements_anchored_fps(
    profile: dict[str, Any] | None, cpu: Any, gpu: Any,
    cpu_catalog: Iterable[Any], gpu_catalog: Iterable[Any],
    gpu_reference: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return an explicitly experimental full-system scenario or abstain."""
    def unavailable(reason: str, **details: Any) -> dict[str, Any]:
        return {"available": False, "data_type": "experimental_requirements_anchored_estimate",
                "model_version": MODEL_VERSION, "reason": reason,
                "one_percent_low": None, "ram_used_by_model": False, **details}

    if not profile:
        return unavailable("game_profile_not_found")
    if not isinstance(gpu_reference, dict) or not gpu_reference.get("available"):
        return unavailable("gpu_reference_estimate_unavailable",
                           gpu_reference_reason=(gpu_reference or {}).get("reason"))
    if (gpu_reference.get("data_type") not in {"external_model_estimate", "published_gpu_measurement"}
            or gpu_reference.get("source_name") not in {"PCGameBenchmarks", "FPSHQ"}):
        return unavailable("gpu_reference_is_not_an_allowed_licensed_source")
    if str(gpu_reference.get("device_class") or "") not in {"desktop", "integrated"}:
        return unavailable("unsupported_gpu_device_class")

    selected_cpu = _positive_score(getattr(cpu, "raw_score", None))
    selected_gpu = _positive_score(getattr(gpu, "raw_score", None))
    gpu_fps = _positive_score(gpu_reference.get("unrounded_fps") or gpu_reference.get("fps"))
    if selected_cpu is None or selected_gpu is None:
        return unavailable("selected_hardware_score_missing")
    if gpu_fps is None:
        return unavailable("gpu_reference_fps_missing")

    requirement_candidates = []
    for level in ("recommended", "minimum"):
        candidate = profile.get(f"{level}_requirements") or {}
        cpu_text = str(candidate.get("cpu") or "").strip()
        gpu_text = str(candidate.get("gpu") or "").strip()
        if cpu_text and gpu_text:
            requirement_candidates.append((level, cpu_text, gpu_text))
    resolved_requirements = None
    failures = []
    for level, cpu_text, gpu_text in requirement_candidates:
        cpu_reference = resolve_cpu_requirement(cpu_text, cpu_catalog)
        gpu_requirement = resolve_gpu_requirement(gpu_text, gpu_catalog)
        if (cpu_reference.get("status") == "resolved_exact_models"
                and gpu_requirement.get("status") == "resolved_exact_models"):
            resolved_requirements = (level, cpu_text, gpu_text, cpu_reference, gpu_requirement)
            break
        failures.append({"level": level, "cpu_status": cpu_reference.get("status"),
                         "gpu_status": gpu_requirement.get("status"),
                         "unresolved_cpu_models": cpu_reference.get("unresolved_models") or [],
                         "unresolved_gpu_models": gpu_requirement.get("unresolved_models") or []})
    if resolved_requirements is None:
        if not requirement_candidates:
            return unavailable("game_requirements_do_not_include_resolvable_cpu_and_gpu")
        best_failure = failures[0]
        reason = ("recommended_cpu_not_fully_resolved" if best_failure["level"] == "recommended"
                  and best_failure["cpu_status"] != "resolved_exact_models" else
                  "recommended_gpu_not_exactly_resolved" if best_failure["level"] == "recommended"
                  else "minimum_cpu_not_fully_resolved" if best_failure["cpu_status"] != "resolved_exact_models"
                  else "minimum_gpu_not_exactly_resolved")
        return unavailable(reason, requirement_resolution_attempts=failures,
                           cpu_requirement_status=best_failure["cpu_status"],
                           gpu_requirement_status=best_failure["gpu_status"],
                           unresolved_cpu_models=best_failure["unresolved_cpu_models"],
                           unresolved_gpu_models=best_failure["unresolved_gpu_models"])
    requirement_level, cpu_text, gpu_text, cpu_reference, gpu_requirement = resolved_requirements

    reference_cpu = _positive_score(cpu_reference.get("reference_cpu_mark"))
    reference_gpu = _positive_score(gpu_requirement.get("reference_gpu_mark"))
    reference_cpu_range = cpu_reference.get("reference_cpu_mark_range")
    reference_gpu_range = gpu_requirement.get("reference_gpu_mark_range")
    if reference_cpu is None or reference_gpu is None:
        return unavailable("recommended_passmark_reference_missing")

    developer_target=profile.get("developer_target") or {}
    target_status="not_used_incomplete_conditions"
    original_gpu_fps=gpu_fps
    baseline_settings=gpu_reference.get("source_settings") or {}
    if (developer_target.get("fps") and developer_target.get("rt") is False
            and developer_target.get("upscaling")=="off" and developer_target.get("frame_generation") is False
            and str(developer_target.get("resolution", "")).casefold()==str(baseline_settings.get("resolution", "")).casefold()
            and str(developer_target.get("preset", "")).casefold()==str(baseline_settings.get("preset", "")).casefold()
            and gpu_reference.get("source_name")=="PCGameBenchmarks"):
        from app.services.external_fps_model import estimate_gpu_fps
        reference_name=gpu_requirement['resolved_models'][0]['name']
        point=estimate_gpu_fps(profile.get("game_id"),reference_name,reference_gpu,
                               resolution=baseline_settings['resolution'],preset=baseline_settings['preset'])
        reference_fps=_positive_score(point.get("unrounded_fps") or point.get("fps"))
        if reference_fps:
            gpu_fps=gpu_fps*float(developer_target['fps'])/reference_fps
            target_status="used_declared_workload_target_not_measurement"
        else:target_status="not_used_reference_curve_unavailable"

    elasticity = _positive_score(gpu_reference.get("min_curve_log_elasticity"))
    if elasticity is None and gpu_reference.get("min_curve_log_elasticity") == 0:
        elasticity = 0.0
    alpha, eta, minimum_factor = DEFAULT_ALPHA, DEFAULT_ETA, DEFAULT_MIN_FACTOR
    scenario_fps, eta_effective = _scenario(
        gpu_fps, selected_cpu, selected_gpu, reference_cpu, reference_gpu,
        alpha, eta, minimum_factor, elasticity,
    )

    cpu_bounds = reference_cpu_range if isinstance(reference_cpu_range, list) and len(reference_cpu_range) == 2 else [reference_cpu, reference_cpu]
    gpu_bounds = reference_gpu_range if isinstance(reference_gpu_range, list) and len(reference_gpu_range) == 2 else [reference_gpu, reference_gpu]
    sensitivity_values = []
    for alpha_value in SENSITIVITY_ALPHA:
        for eta_value in SENSITIVITY_ETA:
            for factor_value in SENSITIVITY_MIN_FACTOR:
                for cpu_ref in cpu_bounds:
                    for gpu_ref in gpu_bounds:
                        cpu_ref_score, gpu_ref_score = _positive_score(cpu_ref), _positive_score(gpu_ref)
                        if cpu_ref_score is None or gpu_ref_score is None:
                            continue
                        value, _ = _scenario(
                            gpu_fps, selected_cpu, selected_gpu, cpu_ref_score, gpu_ref_score,
                            alpha_value, eta_value, factor_value, elasticity,
                        )
                        sensitivity_values.append(value)
    if not sensitivity_values:
        sensitivity_values = [scenario_fps]

    source = profile.get("requirements_provenance") or package().get("source") or {}
    return {
        "available": True,
        "data_type": "experimental_requirements_anchored_estimate",
        "model_version": MODEL_VERSION,
        "scenario_fps": round(scenario_fps, 1),
        "developer_target": developer_target or None,
        "developer_target_status": target_status,
        "developer_target_used_as_measurement": False,
        "original_gpu_reference_fps": original_gpu_fps,

        "scenario_fps_sensitivity_range": [round(min(sensitivity_values), 1),
                                            round(max(sensitivity_values), 1)],
        "range_type": "parameter_and_requirement_sensitivity_not_statistical_confidence_interval",
        "cpu_gpu_reference_fps": round(gpu_fps, 1),
        "r_cpu": round(selected_cpu / reference_cpu, 4),
        "r_gpu": round(selected_gpu / reference_gpu, 4),
        "r_balance": round((selected_cpu / reference_cpu) /
                            ((selected_gpu / reference_gpu) ** eta_effective), 4),
        "cpu_factor": round(scenario_fps / gpu_fps, 4),
        "alpha": alpha,
        "eta_requested": eta,
        "eta_effective": round(eta_effective, 4),
        "eta_note": ("Bounded by the lowest log-slope in the source GPU curve to preserve non-decreasing GPU scaling."
                     if elasticity is not None and elasticity > 0 else
                     "Set to 0 because the source curve is flat or its elasticity is unavailable."),
        "min_factor": minimum_factor,
        "gpu_curve_min_log_elasticity": round(elasticity, 6) if elasticity is not None else None,
        "reference_cpu_mark": reference_cpu,
        "reference_cpu_mark_range": cpu_reference.get("reference_cpu_mark_range"),
        "reference_cpu_models": [item["name"] for item in cpu_reference.get("resolved_models", [])],
        "reference_gpu_mark": reference_gpu,
        "reference_gpu_mark_range": gpu_requirement.get("reference_gpu_mark_range"),
        "reference_gpu_models": [item["name"] for item in gpu_requirement.get("resolved_models", [])],
        "selected_cpu_mark": selected_cpu,
        "selected_gpu_g3d_mark": selected_gpu,
        "selected_cpu": str(getattr(cpu, "name", "")),
        "selected_gpu": str(getattr(gpu, "name", "")),
        "requirements": {"cpu": cpu_text, "gpu": gpu_text,
                         "level": requirement_level,
                         "source_url": profile.get("source_url"),
                         "license": source.get("license"),
                         "snapshot_date": source.get("snapshot_date")},
        "gpu_baseline": {"source_name": gpu_reference.get("source_name"),
                         "source_url": gpu_reference.get("source_url"),
                         "dataset_revision": gpu_reference.get("dataset_revision"),
                         "license": gpu_reference.get("license"),
                         "settings": gpu_reference.get("source_settings"),
                         "fps": round(gpu_fps, 1)},
        "confidence": "very_low",
        "one_percent_low": None,
        "limiting_component": None,
        "ram_used_by_model": False,
        "note": (f"Экспериментальный сценарий: GPU-ориентир источника {gpu_reference.get('source_name')} "
                 f"скорректирован отношением PassMark CPU/GPU к точным {requirement_level} требованиям. "
                 "Системные требования не задают целевой FPS; PassMark CPU Mark не отражает игровую нагрузку и Single Thread. "
                 "Сценарий не является измерением или калиброванным прогнозом всей системы."),
    }


def _catalog_fingerprint(items: Iterable[Any], expected_type: str) -> tuple[tuple[str, float], ...]:
    values = []
    for row in _rows(items, expected_type):
        values.append((row["name"], row["score"]))
    return tuple(sorted(values, key=lambda item: (item[0].casefold(), item[1])))


@lru_cache(maxsize=4)
def _cached_coverage(cpu_fingerprint: tuple[tuple[str, float], ...],
                     gpu_fingerprint: tuple[tuple[str, float], ...]) -> dict[str, Any]:
    cpus = [{"name": name, "raw_score": score, "type": "CPU"}
            for name, score in cpu_fingerprint]
    gpus = [{"name": name, "raw_score": score, "type": "GPU"}
            for name, score in gpu_fingerprint]
    profiles = list(package().get("profiles", []))
    counts = {"profiles_with_recommended_cpu": 0,
              "profiles_with_recommended_gpu": 0,
              "profiles_with_both_recommended_fields": 0,
              "recommended_cpu_exactly_resolved": 0,
              "recommended_gpu_exactly_resolved": 0,
              "both_recommended_models_exactly_resolved": 0,
              "profiles_with_minimum_cpu_and_gpu": 0,
              "minimum_cpu_exactly_resolved": 0,
              "minimum_gpu_exactly_resolved": 0,
              "both_minimum_models_exactly_resolved": 0,
              "minimum_tier_fallback_only_profiles": 0,
              "both_exact_and_external_gpu_curve_available": 0}
    for profile in profiles:
        tier_results = {}
        for level in ("recommended", "minimum"):
            requirements = profile.get(f"{level}_requirements") or {}
            cpu_text, gpu_text = requirements.get("cpu"), requirements.get("gpu")
            has_cpu, has_gpu = bool(str(cpu_text or "").strip()), bool(str(gpu_text or "").strip())
            if level == "recommended":
                counts["profiles_with_recommended_cpu"] += int(has_cpu)
                counts["profiles_with_recommended_gpu"] += int(has_gpu)
                counts["profiles_with_both_recommended_fields"] += int(has_cpu and has_gpu)
            else:
                counts["profiles_with_minimum_cpu_and_gpu"] += int(has_cpu and has_gpu)
            cpu_result = resolve_cpu_requirement(str(cpu_text or ""), cpus)
            gpu_result = resolve_gpu_requirement(str(gpu_text or ""), gpus)
            cpu_ok = cpu_result.get("status") == "resolved_exact_models"
            gpu_ok = gpu_result.get("status") == "resolved_exact_models"
            both = cpu_ok and gpu_ok
            tier_results[level] = both
            if level == "recommended":
                counts["recommended_cpu_exactly_resolved"] += int(cpu_ok)
                counts["recommended_gpu_exactly_resolved"] += int(gpu_ok)
                counts["both_recommended_models_exactly_resolved"] += int(both)
            else:
                counts["minimum_cpu_exactly_resolved"] += int(cpu_ok)
                counts["minimum_gpu_exactly_resolved"] += int(gpu_ok)
                counts["both_minimum_models_exactly_resolved"] += int(both)
        fallback_only = tier_results["minimum"] and not tier_results["recommended"]
        counts["minimum_tier_fallback_only_profiles"] += int(fallback_only)
        if any(tier_results.values()) and minimum_log_curve_elasticity(profile, "desktop") is not None:
            counts["both_exact_and_external_gpu_curve_available"] += 1
    return {
        "total_external_game_profiles": len(profiles),
        **counts,
        "scenario_eligible_game_profiles": counts["both_exact_and_external_gpu_curve_available"],
        "coverage_policy": "Use exact recommended CPU+GPU requirements when both resolve; otherwise exact minimum requirements may provide a very-low-confidence scenario. A GPU curve must be available. This is title-level eligibility, not accuracy validation.",
        "source_license": (package().get("source") or {}).get("license"),
    }


def requirements_anchored_coverage_summary(cpu_catalog: Iterable[Any],
                                           gpu_catalog: Iterable[Any]) -> dict[str, Any]:
    """Cached title-level coverage over all currently packaged game profiles."""
    return _cached_coverage(_catalog_fingerprint(cpu_catalog, "CPU"),
                            _catalog_fingerprint(gpu_catalog, "GPU"))

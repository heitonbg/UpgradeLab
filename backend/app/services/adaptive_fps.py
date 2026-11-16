from __future__ import annotations

from functools import lru_cache
from math import isfinite
from typing import Any, Mapping

from app.core.constants import GAME_PROFILES
from app.services.benchmark_data import native_cohort
from app.services.benchmark_model_v2 import dataset
from app.services.external_fps_model import (
    estimate_gpu_fps, external_game_coverage, package as external_package, profiles_by_id,
)
from app.services.fps_engine_v4 import (
    comparable_gpu_estimates, comparable_pair_measurements, resolve_fps_v4,
)
from app.services.game_catalog import catalog, key as game_key
from app.services.requirements_anchored_fps import (
    estimate_requirements_anchored_fps, requirements_anchored_coverage_summary,
)


def _requested_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    values = dict(settings or {})
    requested = {
        "resolution": values.get("resolution", "1080p"),
        "preset": str(values.get("preset", "high")).casefold(),
        "rt": bool(values.get("rt", False)),
        "upscaling": str(values.get("upscaling", "off")).casefold(),
        "frame_generation": bool(values.get("frame_generation", False)),
    }
    # RAM is benchmark context for strict matching and comparisons only;
    # it is never used as a coefficient by an FPS model.
    for field in ("ram_type", "ram_channels", "ram_capacity_gb"):
        if values.get(field) is not None:
            requested[field] = values[field]
    return requested


def present_adaptive_result(evidence: Mapping[str, Any],
                            settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Normalize FPS evidence without merging measurements and unlike estimates."""
    status = str(evidence.get("status") or "insufficient_data")
    average = evidence.get("average_fps")
    gpu_only = evidence.get("gpu_oriented_fps")
    if status == "measured_reference" and average is not None:
        result_type, label = "measured_system_fps", "FPS по опубликованному тесту"
        confidence_label = "Условия теста сохранены; результат относится к опубликованной системе."
    elif status in {"estimated_interpolation", "legacy_profile_estimate"} and average is not None:
        result_type, label = "estimated_system_fps", "Расчётный прогноз FPS системы"
        confidence_label = ("Интерполяция по измерениям этой связки."
                           if status == "estimated_interpolation"
                           else "Расчётный FPS.")
    elif status in {"external_model_anchored", "external_fpshq_gpu_only",
                    "external_model_settings_fallback", "external_model_nearest_anchor_fallback",
                    "catalog_gpu_reference_only"} and gpu_only is not None:
        if status == "external_fpshq_gpu_only" and evidence.get("measurement_type") == "published_gpu_measurement":
            label = "Опубликованный FPS-тест видеокарты"
        elif status == "external_fpshq_gpu_only":
            label = "Оценка GPU по FPSHQ"
        elif status == "external_model_anchored":
            label = "Оценка GPU по PCGameBenchmarks"
        elif status == "external_model_settings_fallback":
            label = "Оценка GPU по данным 1080p High"
        elif status == "external_model_nearest_anchor_fallback":
            label = "Ближайшая GPU-опора той же игры"
        else:
            label = "Широкий GPU-ориентир по каталогу игр"
        result_type = "gpu_reference_only"
        confidence_label = evidence.get("note") or "Внешний GPU-ориентир; FPS всей системы не рассчитан."
    else:
        result_type, label = "unavailable", "Оценка FPS недоступна"
        confidence_label = "Нет игровой опоры для выбранной конфигурации и настроек."

    technical_settings = evidence.get("settings")
    if not isinstance(technical_settings, dict):
        technical_settings = _requested_settings(settings)
    source_settings = evidence.get("source_settings") or technical_settings
    gpu_details = evidence.get("gpu_estimate_details") or {}
    alternative = evidence.get("gpu_reference_alternative") or {}
    alternative_details = alternative.get("gpu_estimate_details") or {}
    best_available_fps = (average if result_type in {"measured_system_fps", "estimated_system_fps"}
                          else gpu_only if result_type == "gpu_reference_only" else None)
    return {
        "result_type": result_type,
        "result_label": label,
        "average_fps": average if result_type in {"measured_system_fps", "estimated_system_fps"} else None,
        "gpu_oriented_fps": gpu_only if result_type == "gpu_reference_only" else None,
        "best_available_fps": best_available_fps,
        "best_available_fps_basis": result_type if best_available_fps is not None else None,
        "gpu_reference_range": gpu_details.get("fps_range"),
        "gpu_reference_range_type": gpu_details.get("range_type"),
        "gpu_reference_alternative": ({
            "result_type": "gpu_reference_only",
            "result_label": alternative.get("note") or "Вторичная оценка видеокарты",
            "average_fps": None,
            "gpu_oriented_fps": alternative.get("gpu_oriented_fps"),
            "settings": alternative.get("settings"),
            "source_settings": alternative.get("source_settings"),
            "sources": alternative.get("source_evidence") or [],
            "source_name": alternative.get("workload_source"),
            "note": alternative.get("note"),
            "confidence": alternative.get("confidence"),
            "technical_details": alternative,
            "gpu_reference_range": alternative_details.get("fps_range"),
            "gpu_reference_range_type": alternative_details.get("range_type"),
        } if alternative.get("gpu_oriented_fps") is not None else None),
        "one_percent_low": evidence.get("one_percent_low") if result_type in {"measured_system_fps", "estimated_system_fps"} else None,
        "limiting_component": evidence.get("limiting_component") if evidence.get("cpu_limit_assessed") is True else None,
        "confidence": evidence.get("confidence", "insufficient"),
        "confidence_label": confidence_label,
        "game": evidence.get("game"),
        "settings": _requested_settings(settings) if settings is not None else technical_settings,
        "source_settings": source_settings,
        "sources": evidence.get("source_evidence") or [],
        "note": evidence.get("note"),
        "missing_data": evidence.get("missing_data") or [],
        "ram_used_by_model": False,
        "technical_details": dict(evidence),
    }


@lru_cache(maxsize=1)
def _external_profile_aliases() -> dict[str, dict[str, Any]]:
    aliases: dict[str, dict[str, Any]] = {}
    for game_id, profile in profiles_by_id().items():
        for candidate in (game_id, profile.get("catalog_name"), profile.get("source_game_name"),
                          profile.get("steam_app_id")):
            normalized = game_key(str(candidate or ""))
            if normalized:
                aliases.setdefault(normalized, profile)
    return aliases


def _external_profile_for_game(game: Any) -> dict[str, Any] | None:
    label = getattr(game, "value", game)
    text = str(label or "").strip()
    profile = profiles_by_id().get(text)
    from app.services.steam_storage import enriched_profile
    if profile is not None:
        return enriched_profile(profile)
    return enriched_profile(_external_profile_aliases().get(game_key(text)))


def _predict_adaptive_evidence(cpu, gpu, game: str, settings: Mapping[str, Any] | None = None,
                         *, cpu_catalog=(), gpu_catalog=()) -> dict[str, Any]:
    """Select the strongest defensible result. RAM never affects this estimate."""
    requested = _requested_settings(settings)
    evidence = resolve_fps_v4(
        cpu, gpu, game, requested["resolution"], requested["preset"],
        rt=requested["rt"], upscaling=requested["upscaling"],
        frame_generation=requested["frame_generation"], cpu_catalog=cpu_catalog,
        ram_type=requested.get("ram_type"),
        ram_channels=requested.get("ram_channels"),
        ram_capacity_gb=requested.get("ram_capacity_gb"),
    )
    # A pixel-workload fallback is explicitly estimated, never a measurement.
    # Preserve source settings and provenance so callers can inspect assumptions.
    if evidence.get("average_fps") is None and evidence.get("gpu_oriented_fps"):
        source = evidence.get("source_settings") or {"resolution": "1080p"}
        pixels = {"1080p": 1920 * 1080, "1440p": 2560 * 1440,
                  "2160p": 3840 * 2160, "4k": 3840 * 2160}
        source_pixels = pixels.get(str(source.get("resolution", "1080p")).lower())
        target_pixels = pixels.get(str(requested["resolution"]).lower())
        if source_pixels and target_pixels:
            evidence = dict(evidence)
            evidence["gpu_oriented_fps"] = round(
                float(evidence["gpu_oriented_fps"]) * source_pixels / target_pixels, 2)
            evidence["resolution_scaling"] = {
                "method": "inverse_pixel_workload", "source_resolution": source.get("resolution"),
                "target_resolution": requested["resolution"], "validated": False}
            evidence["confidence"] = "very_low"
    result = present_adaptive_result(evidence, requested)
    from app.services.steam_storage import current_status
    steam_state = current_status() or {}
    steam_levels = (steam_state.get('requirements') or {})
    steam_resolved = any(steam_levels.get(level, {}).get('fully_resolved') for level in ('minimum','recommended'))
    anchor_statuses = {"external_model_anchored", "external_fpshq_gpu_only"}
    if steam_resolved:
        anchor_statuses.add("external_model_settings_fallback")
    scenario_anchor = evidence.get("gpu_reference_alternative")
    if scenario_anchor is not None and scenario_anchor.get("status") not in anchor_statuses:
        scenario_anchor = None
    if scenario_anchor is None and evidence.get("status") in anchor_statuses:
        scenario_anchor = evidence
    if scenario_anchor is not None:
        profile = _external_profile_for_game(game)
        baseline_settings = scenario_anchor.get("source_settings") or scenario_anchor.get("settings") or {}
        requested_core_settings = {key: requested.get(key) for key in (
            "resolution", "preset", "rt", "upscaling", "frame_generation")}
        source_core_settings = {key: baseline_settings.get(key) for key in (
            "resolution", "preset", "rt", "upscaling", "frame_generation")}
        settings_match = (str(requested_core_settings.get("resolution")).casefold() ==
                          str(source_core_settings.get("resolution")).casefold()
                          and str(requested_core_settings.get("preset")).casefold() ==
                          str(source_core_settings.get("preset")).casefold()
                          and all(requested_core_settings[key] == source_core_settings[key]
                                  for key in ("rt", "upscaling", "frame_generation")))
        transferred = (steam_resolved and not settings_match
                       and source_core_settings.get("preset", "").casefold() == requested["preset"]
                       and not requested["rt"] and requested["upscaling"] == "off"
                       and not requested["frame_generation"]
                       and evidence.get("resolution_scaling") is not None
                       and scenario_anchor is evidence)
        if not settings_match and not transferred:
            evidence["requirements_anchored_estimate"] = {
                "available": False, "data_type": "experimental_requirements_anchored_estimate",
                "model_version": "requirements_anchored_v1_experimental",
                "reason": "requested_settings_do_not_match_gpu_baseline",
                "source_settings": baseline_settings, "ram_used_by_model": False,
            }
            result["technical_details"] = dict(evidence)
            result["requirements_anchored_estimate"] = evidence["requirements_anchored_estimate"]
            if result.get("gpu_reference_alternative") is not None:
                result["gpu_reference_alternative"]["requirements_anchored_estimate"] = evidence["requirements_anchored_estimate"]
            return result
        if profile is None:
            scenario = {"available": False,
                        "data_type": "experimental_requirements_anchored_estimate",
                        "model_version": "requirements_anchored_v1_experimental",
                        "reason": "game_profile_not_found", "one_percent_low": None,
                        "ram_used_by_model": False}
        else:
            gpu_reference = scenario_anchor.get("gpu_estimate_details")
            if transferred and gpu_reference:
                gpu_reference = {**gpu_reference, "fps": evidence["gpu_oriented_fps"],
                                 "unrounded_fps": evidence["gpu_oriented_fps"]}
            scenario = estimate_requirements_anchored_fps(
                profile, cpu, gpu, cpu_catalog, gpu_catalog, gpu_reference)
            if transferred:
                scenario["resolution_transfer"] = evidence["resolution_scaling"]
            if steam_levels.get("official_target"):
                scenario["developer_target"] = steam_levels["official_target"]
                scenario["developer_target_used_as_measurement"] = False
        if scenario_anchor is evidence:
            evidence["requirements_anchored_estimate"] = scenario
        else:
            scenario_anchor["requirements_anchored_estimate"] = scenario
            evidence["gpu_reference_alternative"] = scenario_anchor
        evidence["requirements_anchored_estimate"] = scenario
        result["technical_details"] = dict(evidence)
        result["requirements_anchored_estimate"] = scenario
        if result.get("gpu_reference_alternative") is not None:
            result["gpu_reference_alternative"]["requirements_anchored_estimate"] = scenario
    return result

def compare_adaptive_results(before: Mapping[str, Any] | None,
                             after: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compare only like evidence; experimental scenario gain stays separate."""
    empty = {"gain_fps": None, "gain_type": None, "gpu_oriented_gain_fps": None,
             "gpu_reference_alternative_gain_fps": None,
             "requirements_anchored_scenario_gain_fps": None}
    if (not before or not after or before.get("game") != after.get("game")
            or before.get("settings") != after.get("settings")):
        return empty
    left_model = before.get("technical_details") or {}
    right_model = after.get("technical_details") or {}
    if (left_model.get("status") == right_model.get("status") == "universal_fallback_estimate"
            and left_model.get("method") == right_model.get("method")
            and before.get("average_fps") is not None and after.get("average_fps") is not None):
        return {**empty, "gain_fps": round(after["average_fps"] - before["average_fps"], 2),
                "gain_type": "same_model_estimate"}
    left = before.get("technical_details") or {}
    right = after.get("technical_details") or {}
    scenario_left = before.get("requirements_anchored_estimate") or left.get("requirements_anchored_estimate") or {}
    scenario_right = after.get("requirements_anchored_estimate") or right.get("requirements_anchored_estimate") or {}
    scenario_gain = None
    if (scenario_left.get("available") is True and scenario_right.get("available") is True
            and scenario_left.get("model_version") == scenario_right.get("model_version")
            and scenario_left.get("scenario_fps") is not None
            and scenario_right.get("scenario_fps") is not None):
        scenario_gain = round(scenario_right["scenario_fps"] - scenario_left["scenario_fps"], 2)
    alternative_gpu_gain = None
    left_alternative = left.get("gpu_reference_alternative") or {}
    right_alternative = right.get("gpu_reference_alternative") or {}
    left_alternative_gpu = (left_alternative.get("gpu_estimate_details") or {}).get("target_gpu")
    right_alternative_gpu = (right_alternative.get("gpu_estimate_details") or {}).get("target_gpu")
    if (left_alternative_gpu != right_alternative_gpu
            and comparable_gpu_estimates(left_alternative, right_alternative)
            and left_alternative.get("gpu_oriented_fps") is not None
            and right_alternative.get("gpu_oriented_fps") is not None):
        alternative_gpu_gain = round(
            right_alternative["gpu_oriented_fps"] - left_alternative["gpu_oriented_fps"], 2)
    scenario_fields = {"requirements_anchored_scenario_gain_fps": scenario_gain,
                       "gpu_reference_alternative_gain_fps": alternative_gpu_gain}
    if (before.get("result_type") == after.get("result_type") == "measured_system_fps"
            and comparable_pair_measurements(left, right)
            and before.get("average_fps") is not None and after.get("average_fps") is not None):
        return {**empty, **scenario_fields,
                "gain_fps": round(after["average_fps"] - before["average_fps"], 2),
                "gain_type": "measured_comparison"}
    if (before.get("result_type") == after.get("result_type") == "estimated_system_fps"
            and left.get("status") == right.get("status") == "legacy_profile_estimate"
            and left.get("method") == right.get("method")
            and before.get("average_fps") is not None and after.get("average_fps") is not None):
        return {**empty, **scenario_fields,
                "gain_fps": round(after["average_fps"] - before["average_fps"], 2),
                "gain_type": "same_model_estimate"}
    left_gpu = (left.get("gpu_estimate_details") or {}).get("target_gpu")
    right_gpu = (right.get("gpu_estimate_details") or {}).get("target_gpu")
    if (before.get("result_type") == after.get("result_type") == "gpu_reference_only"
            and left_gpu != right_gpu and comparable_gpu_estimates(left, right)
            and before.get("gpu_oriented_fps") is not None and after.get("gpu_oriented_fps") is not None):
        return {**empty, **scenario_fields,
                "gpu_oriented_gain_fps": round(after["gpu_oriented_fps"] - before["gpu_oriented_fps"], 2)}
    return {**empty, **scenario_fields}

def adaptive_game_coverage(cpu_catalog=(), gpu_catalog=()) -> dict[str, Any]:
    """Count title-level evidence tiers; this is not per-hardware coverage."""
    items = catalog()
    by_alias: dict[str, str] = {}
    for item in items:
        for alias in [item.get("name", ""), *(item.get("aliases") or [])]:
            normalized = game_key(alias)
            if normalized:
                by_alias[normalized] = str(item.get("id"))
    catalog_ids = {str(item.get("id")) for item in items}
    legacy_ids = {by_alias.get(game_key(getattr(game, "value", str(game)))) for game in GAME_PROFILES}
    legacy_ids.discard(None)
    measured_ids = set()
    interpolation_cohorts: dict[tuple, set[str]] = {}
    rows, _ = dataset()
    for row in rows:
        if not native_cohort(row):
            continue
        matched = by_alias.get(game_key(row.get("game", "")))
        if not matched:
            continue
        measured_ids.add(matched)
        resolution = str(row.get("resolution", "")).casefold().replace("×", "x").replace(" ", "")
        resolution = {"3840x2160": "4k", "2160p": "4k", "2560x1440": "1440p",
                      "1920x1080": "1080p", "1280x720": "720p"}.get(resolution, resolution)
        settings = row.get("settings") if isinstance(row.get("settings"), dict) else row
        context = tuple(settings.get(key) for key in (
            "game_version", "ram_gb", "ram_type", "ram_channels", "vram_gb", "preset",
            "rt", "upscaling", "frame_generation", "frame_generation_mode", "render_scale",
            "scene", "overclocked", "os", "form_factor", "power_profile"))
        cohort = (matched, row.get("cpu"), row.get("gpu"), context)
        interpolation_cohorts.setdefault(cohort, set()).add(resolution)
    interpolated_ids = {cohort[0] for cohort, resolutions in interpolation_cohorts.items()
                        if len(resolutions) >= 2}

    profiles = profiles_by_id()
    reference_types = {item.get("name"): item.get("device_class")
                       for item in external_package().get("reference_gpus", [])}
    gpu_curve_ids = set()
    for profile in profiles.values():
        matched = None
        for candidate in (profile.get("catalog_name"), profile.get("source_game_name"),
                          profile.get("steam_app_id")):
            matched = by_alias.get(game_key(str(candidate or "")))
            if matched:
                break
        if not matched:
            continue
        curve_counts: dict[str, int] = {}
        for gpu_name, value in (profile.get("fps_by_reference_gpu") or {}).items():
            device_class = reference_types.get(gpu_name)
            if (device_class and isinstance(value, (int, float)) and not isinstance(value, bool)
                    and isfinite(float(value)) and float(value) > 0):
                curve_counts[device_class] = curve_counts.get(device_class, 0) + 1
        if any(count >= 2 for count in curve_counts.values()):
            gpu_curve_ids.add(matched)

    full_system_ids = (legacy_ids | measured_ids) & catalog_ids
    estimated_system_ids = (legacy_ids | interpolated_ids) & catalog_ids
    gpu_only_ids = gpu_curve_ids - full_system_ids
    return {
        "total_games": len(items),
        "games_with_licensed_pair_measurements": len(measured_ids & catalog_ids),
        "games_with_same_pair_resolution_interpolation": len(interpolated_ids & catalog_ids),
        "games_with_legacy_system_estimate": len(legacy_ids & catalog_ids),
        "games_with_approximate_system_estimate": len(estimated_system_ids),
        "games_with_any_full_system_number": len(full_system_ids),
        "games_with_external_gpu_curve": len(gpu_curve_ids),
        "gpu_only_tier_games": len(gpu_only_ids),
        "games_without_title_specific_gpu_or_system_estimate": len(catalog_ids - full_system_ids - gpu_curve_ids),
        "games_with_generic_gpu_catalog_reference_available": len(catalog_ids),
        "games_using_generic_gpu_catalog_fallback": len(catalog_ids - full_system_ids - gpu_curve_ids),
        "external_model_estimate_records": external_game_coverage()["external_estimate_records"],
        "scope_note": "Покрытие по играм означает наличие хотя бы одной опоры в каталоге. Доступность числа для ПК зависит от точного сопоставления GPU и поддерживаемых настроек; GPU-only опора не является FPS всей системы.",
    }


def predict_adaptive_fps(cpu, gpu, game, settings=None, *, cpu_catalog=(), gpu_catalog=()):
    """Public estimate chain; retain measured results and expose fallback provenance."""
    from statistics import median
    from app.services.performance import cpu_capacity
    from app.schemas.calculate import CalcMode
    result = _predict_adaptive_evidence(cpu, gpu, game, settings,
        cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
    from app.services.steam_storage import current_status
    state = current_status()
    if state:
        result['requirements_enrichment'] = {k:state.get(k) for k in ('game_id','status','version','refresh_pending','last_checked_at','source_url','source_type')}

    if result.get("average_fps") is not None:
        return result
    requested = _requested_settings(settings)
    gpu_fps = result.get("gpu_oriented_fps")
    if not isinstance(gpu_fps, (int, float)) or not isfinite(gpu_fps) or gpu_fps <= 0:
        return result
    scenario = result.get("requirements_anchored_estimate") or {}
    if scenario.get("available") and scenario.get("scenario_fps"):
        fps = min(float(scenario["scenario_fps"]), gpu_fps)
        basis = "requirements_anchored_v1_experimental"
        ceiling = None
    else:
        score = getattr(cpu, "raw_score", None)
        if not isinstance(score, (int, float)) or not isfinite(score) or score <= 0:
            return result
        ceilings = []
        # Existing game CPU curves supply a population prior, not new measurements.
        mode = CalcMode.MODE_1080P_HIGH
        for profile, modes in GAME_PROFILES.items():
            if mode in modes:
                ceilings.append(cpu_capacity(score, cpu.name, profile, mode, 1.0)
                                * modes[mode]["overhead"])
        if not ceilings:
            return result
        ceiling = median(ceilings)
        fps = min(float(gpu_fps), ceiling)
        basis = "catalog_gpu_cpu_population_prior_v1"
    evidence = dict(result.get("technical_details") or {})
    evidence.update(status="universal_fallback_estimate", average_fps=round(fps, 2),
        method=basis, cpu_limit_assessed=ceiling is not None,
        limiting_component=("CPU" if ceiling < gpu_fps else "GPU") if ceiling else None,
        confidence="very_low", one_percent_low=None)
    result.update(result_type="estimated_system_fps", result_label="Расчётный FPS",
        average_fps=round(fps, 2), best_available_fps=round(fps, 2),
        best_available_fps_basis="estimated_system_fps", one_percent_low=None,
        confidence="very_low", limiting_component=evidence["limiting_component"],
        technical_details=evidence)
    return result

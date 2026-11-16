"""Universal FPS evidence resolver.

The resolver widens game selection without manufacturing system FPS. It
prefers pair measurements, then retained legacy profiles, then a separately
labeled external GPU-only model estimate. PassMark scores are used only to
interpolate across that source's per-game GPU reference curve; no CPU or RAM
multiplier is inferred.
"""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from app.schemas.calculate import GameName
from app.core.constants import GAME_PROFILES
from app.services.benchmark_model_v2 import predict_pair, cpu_comparison_coverage
from app.services.fps_v2 import predict as predict_legacy
from app.services.game_catalog import catalog, key as game_key
from app.services.external_fps_model import (
    estimate_gpu_fps, estimate_nearest_game_gpu_anchor, estimate_catalog_gpu_reference,
    profiles_by_id, package as external_fps_package,
)
from app.services.cpu_requirements import assess_cpu_adequacy


def supported_profile(game: str | GameName) -> GameName | None:
    """Return the legacy-calibrated game enum, if this title has a profile."""
    try:
        candidate = game if isinstance(game, GameName) else GameName(str(game))
    except ValueError:
        return None
    return candidate if candidate in GAME_PROFILES else None


@lru_cache(maxsize=1024)
def _catalog_game(game: str | GameName) -> dict[str, Any] | None:
    wanted = game_key(game.value if isinstance(game, GameName) else str(game))
    return next((item for item in catalog()
                 if wanted in {game_key(item.get("name", "")),
                               *(game_key(alias) for alias in item.get("aliases", []))}), None)


def comparable_pair_measurements(before: dict[str, Any] | None,
                                  after: dict[str, Any] | None) -> bool:
    """Allow a measured FPS delta only for shared, exact, like-for-like test series."""
    if not before or not after:
        return False
    if before.get("status") != "measured_reference" or after.get("status") != "measured_reference":
        return False
    if before.get("workload_source") != "licensed_pair_measurements" or after.get("workload_source") != "licensed_pair_measurements":
        return False
    if before.get("settings") != after.get("settings"):
        return False
    before_series = set(before.get("series_ids") or [])
    after_series = set(after.get("series_ids") or [])
    before_publishers = {item.get("publisher") for item in before.get("source_evidence", [])}
    after_publishers = {item.get("publisher") for item in after.get("source_evidence", [])}
    return bool(before_series.intersection(after_series) and before_publishers.intersection(after_publishers))


def comparable_gpu_estimates(before: dict[str, Any] | None,
                             after: dict[str, Any] | None) -> bool:
    """Compare GPU-only outputs only within the same pinned source and settings."""
    allowed = {"external_model_anchored", "external_fpshq_gpu_only", "external_model_nearest_anchor_fallback"}
    if not before or not after or before.get("status") not in allowed or after.get("status") not in allowed:
        return False
    left, right = before.get("gpu_estimate_details") or {}, after.get("gpu_estimate_details") or {}
    return bool(left.get("source_name") == right.get("source_name") and
                (left.get("dataset_revision") or left.get("dataset_url")) and
                (left.get("dataset_revision") or left.get("dataset_url")) ==
                (right.get("dataset_revision") or right.get("dataset_url")) and
                (left.get("source_game_id") or left.get("source_game_name")) ==
                (right.get("source_game_id") or right.get("source_game_name")) and
                left.get("source_settings") == right.get("source_settings"))


def _gpu_only_result(base: dict[str, Any], estimate: dict[str, Any], *,
                     status: str, requested_settings: dict[str, Any], note: str,
                     source_name: str | None = None) -> dict[str, Any]:
    fps = estimate.get("unrounded_fps", estimate.get("fps"))
    if not isinstance(fps, (int, float)) or fps <= 0:
        return base
    if source_name and not estimate.get("source_name"):
        estimate = {**estimate, "source_name": source_name}
    source = {
        "title": (f"{estimate.get('source_name') or source_name or 'Источник'} · {estimate.get('scope') or 'GPU-only'}"),
        "publisher": estimate.get("source_name") or source_name or "Источник",
        "url": estimate.get("source_url") or estimate.get("dataset_url"),
        "dataset_url": estimate.get("dataset_url"),
        "dataset_revision": estimate.get("dataset_revision"),
        "fps": round(float(fps)),
        "settings": estimate.get("source_settings"),
        "data_type": "external_model_estimate",
        "license": estimate.get("license"),
        "attribution": estimate.get("attribution"),
        "observed_date": estimate.get("snapshot_date"),
        "measurement_type": estimate.get("measurement_type"),
    }
    evidence = estimate.get("sources") or []
    if evidence:
        source_evidence = [{**source, **item, "publisher": item.get("publisher") or source["publisher"],
                            "license": item.get("license") or source["license"],
                            "data_type": estimate.get("data_type", "external_model_estimate")} for item in evidence]
    elif estimate.get("reference_points"):
        source_evidence = [{**source, "title": f"{source['publisher']} · {point.get('gpu')}",
                            "fps": point.get("fps"), "settings": "1080p High · GPU reference"}
                           for point in estimate["reference_points"]]
    else:
        source_evidence = [{**source, "data_type": estimate.get("data_type", "external_model_estimate")}]
    return {
        **base, "status": status, "confidence_level": status,
        "confidence": estimate.get("confidence", "very_low"),
        "measurement_type": estimate.get("measurement_type", "external_model_estimate"),
        "method": estimate.get("method", estimate.get("scope", "external_gpu_reference")),
        "gpu_oriented_fps": int(round(float(fps))),
        "gpu_estimate_details": estimate, "source_evidence": source_evidence,
        "workload_source": estimate.get("source_name") or source_name or "external GPU estimate",
        "settings": requested_settings,
        "source_settings": estimate.get("source_settings"),
        "missing_data": ["FPS всей CPU/GPU-системы", "CPU-кривая игровой производительности",
                         "сцена и версия игры"],
        "note": note,
    }


@lru_cache(maxsize=1)
def _fpshq_metadata() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "fpshq_model_top50_raw.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    meta = document.get("meta", {})
    if meta.get("license") != "CC BY 4.0" or meta.get("url") != "https://fpshq.com/en/data/fps-model-top50/":
        raise ValueError("Unexpected FPSHQ dataset provenance")
    return meta


def _fpshq_gpu_estimate(gpu, game: str, resolution: str, preset: str,
                        rt: bool, upscaling: str, frame_generation: bool) -> dict[str, Any] | None:
    if rt or str(upscaling).casefold() != "off" or frame_generation or str(preset).casefold() != "high":
        return None
    normalized_resolution = "4K" if str(resolution).casefold() in {"4k", "2160p", "3840x2160"} else str(resolution)
    mode_key = {"1080p": "1080p_high", "1440p": "1440p_high", "4K": "4k_high"}.get(normalized_resolution)
    if not mode_key:
        return None
    try:
        from app.services.benchmark_estimates import fpshq_gpu_reference
        result = fpshq_gpu_reference(gpu.name, game, mode_key, getattr(gpu, "raw_score", None))
    except (ImportError, KeyError, OSError, ValueError, TypeError):
        return None
    if not result or result.get("fps") is None:
        return None
    try:
        metadata = _fpshq_metadata()
    except (OSError, ValueError, TypeError):
        metadata = {}
    is_direct_gpu_measurement = (result.get("measurement_type") == "measured"
                                 and result.get("exact_gpu") is True)
    return {
        **result, "available": True, "data_type": "external_model_estimate",
        "source_name": "FPSHQ", "source_url": (result.get("sources") or [{}])[0].get("url"),
        "dataset_url": metadata.get("url"), "dataset_revision": metadata.get("version"),
        "snapshot_date": metadata.get("version_date"), "license": metadata.get("license", "CC BY 4.0"),
        "attribution": metadata.get("attribution"), "unrounded_fps": float(result["fps"]),
        "measurement_type": "published_gpu_measurement" if is_direct_gpu_measurement
                            else "external_model_estimate",
        "data_type": "published_gpu_measurement" if is_direct_gpu_measurement
                     else "external_model_estimate",
        "device_class": "desktop",
        "source_settings": {"resolution": normalized_resolution, "preset": "High", "rt": False,
                             "upscaling": "off", "frame_generation": False},
        "note": str(result.get("note") or "GPU-only FPSHQ estimate.") +
                " FPSHQ GPU-only estimate; not a CPU/GPU system result.",
        "source_game_id": game_key(game),
        "source_game_name": game,
        "target_gpu": gpu.name,
        "target_g3d_score": getattr(gpu, "raw_score", None),
        "gpu_match": {"status": "exact_gpu_model" if result.get("exact_gpu") else "FPSHQ_reference_interpolation",
                      "reference_gpu": (result.get("sources") or [{}])[0].get("gpu")},
    }


def _same_settings_gpu_reference(gpu, game: str, game_row: dict[str, Any] | None,
                                 resolution: str, preset: str, *, rt: bool,
                                 upscaling: str, frame_generation: bool,
                                 base: dict[str, Any]) -> dict[str, Any] | None:
    """Attach an independent GPU-only source only when its settings match."""
    settings = {"resolution": resolution, "preset": str(preset).casefold(),
                "rt": bool(rt), "upscaling": str(upscaling).casefold(),
                "frame_generation": bool(frame_generation)}
    fpshq = _fpshq_gpu_estimate(gpu, game, resolution, preset, rt, upscaling, frame_generation)
    if fpshq is not None:
        return _gpu_only_result(
            base, fpshq, status="external_fpshq_gpu_only", requested_settings=settings,
            note=(fpshq.get("note") or "FPSHQ GPU-only reference.") +
                 " Это не FPS полной CPU/GPU-системы.", source_name="FPSHQ")
    if (game_row is None or str(resolution).casefold() != "1080p"
            or str(preset).casefold() != "high" or rt
            or str(upscaling).casefold() != "off" or frame_generation):
        return None
    profile = profiles_by_id().get(str(game_row.get("id")))
    if profile is None:
        return None
    external = estimate_gpu_fps(
        game_row.get("id"), gpu.name, getattr(gpu, "raw_score", None), getattr(gpu, "vram", None),
        resolution="1080p", preset="high", rt=False, upscaling="off", frame_generation=False,
    )
    if external.get("fps") is None:
        if external.get("reason") not in {"above_safe_reference_range", "below_safe_reference_range"}:
            return None
        anchor = estimate_nearest_game_gpu_anchor(
            game_row.get("id"), gpu.name, getattr(gpu, "raw_score", None), getattr(gpu, "vram", None))
        if not anchor.get("available"):
            return None
        return _gpu_only_result(
            base, anchor, status="external_model_nearest_anchor_fallback", requested_settings=settings,
            note=anchor.get("note") or "Closest licensed GPU reference; not a target GPU/system prediction.",
            source_name="PCGameBenchmarks")
    return _gpu_only_result(
        base, external, status="external_model_anchored", requested_settings=settings,
        note=("PCGameBenchmarks GPU estimate at the selected 1080p High settings; "
              "not a full-system result."), source_name="PCGameBenchmarks")


def _with_gpu_reference_alternative(result: dict[str, Any], base: dict[str, Any], gpu,
                                    game: str, game_row: dict[str, Any] | None,
                                    resolution: str, preset: str, *, rt: bool,
                                    upscaling: str, frame_generation: bool) -> dict[str, Any]:
    alternative = _same_settings_gpu_reference(
        gpu, game, game_row, resolution, preset, rt=rt, upscaling=upscaling,
        frame_generation=frame_generation, base=base,
    )
    if alternative is not None:
        result["gpu_reference_alternative"] = alternative
    return result


def resolve_fps_v4(cpu, gpu, game: str | GameName, resolution: str = "1080p",
                   preset: str = "high", *, rt: bool = False,
                   upscaling: str = "off", frame_generation: bool = False,
                   cpu_catalog=(), measurement_rows: list[dict[str, Any]] | None = None,
                   ram_type: str | None = None, ram_channels: int | None = None,
                   ram_capacity_gb: int | None = None) -> dict[str, Any]:
    """Resolve the strongest defensible estimate for a game and hardware pair.

    RAM settings are used only to reject measurements from a known, different
    memory setup. They never influence a calculated FPS value.
    """
    label = game.value if isinstance(game, GameName) else str(game).strip()
    game_row = _catalog_game(label)
    requirement_profile = profiles_by_id().get(str(game_row.get("id"))) if game_row else None
    cpu_adequacy = assess_cpu_adequacy(requirement_profile, cpu, cpu_catalog)
    cpu_coverage = cpu_comparison_coverage()
    cpu_frame_time_evidence = {
        "status": "not_calibrated", "calibrated": False, "frame_time_ms": None,
        "comparison_groups": cpu_coverage["groups_with_multiple_cpu_models"],
        "games_with_comparable_cpu_measurements": cpu_coverage["games_with_multiple_cpu_models"],
        "independent_series_in_comparable_groups": cpu_coverage["independent_series_in_comparable_groups"],
        "reason": cpu_coverage["reason"],
    }
    base = {
        "model": "fps_engine_v4_universal",
        "model_version": "4.0",
        "game": label,
        "game_in_catalog": game_row is not None,
        "average_fps": None,
        "gpu_oriented_fps": None,
        "one_percent_low": None,
        "status": "insufficient_data",
        "confidence_level": "insufficient_data",
        "confidence": "insufficient",
        "measurement_type": None,
        "method": "abstain",
        "source_evidence": [],
        "workload_source": None,
        "limiting_component": None,
        "cpu_limit_assessed": False,
        "cpu_frame_time_ms": None,
        "gpu_frame_time_ms": None,
        "cpu_frame_time_evidence": cpu_frame_time_evidence,
        "ram_used_by_model": False,
        "missing_data": [],
        "external_model_available": bool(game_row and game_row.get("external_gpu_estimate_available")),
        "cpu_adequacy": cpu_adequacy,
        "note": "Для этой игры и связки пока нет проверенной игровой опоры; FPS не рассчитан.",
    }

    pair = predict_pair(cpu.name, gpu.name, label, resolution, preset,
                        ram_type=ram_type, ram_channels=ram_channels,
                        ram_capacity_gb=ram_capacity_gb,
                        rt=rt, upscaling=upscaling,
                        frame_generation=frame_generation, source_rows=measurement_rows)
    if pair.get("status") in {"measured_reference", "estimated_interpolation"} and pair.get("average_fps"):
        measured_result = {
            **base,
            "average_fps": pair.get("average_fps"),
            # A percentile low is only published for a direct matching run.
            # Resolution interpolation currently calibrates average FPS only.
            "one_percent_low": pair.get("one_percent_low") if pair["status"] == "measured_reference" else None,
            "status": pair["status"],
            "confidence_level": "measured_pair" if pair["status"] == "measured_reference" else "same_pair_interpolation",
            "confidence": pair.get("confidence", "limited"),
            "measurement_type": pair.get("measurement_type"),
            "method": pair.get("method"),
            "source_evidence": pair.get("sources", []),
            "workload_source": "licensed_pair_measurements",
            "missing_data": [],
            "settings": pair.get("settings"),
            "sample_count": pair.get("sample_count", 0),
            "independent_series": pair.get("independent_series", 0),
            "series_ids": pair.get("series_ids", []),
            "note": "FPS основан на опубликованных измерениях этой CPU/GPU связки и указанных настройках; это не тест вашего экземпляра ПК.",
        }
        return _with_gpu_reference_alternative(
            measured_result, base, gpu, label, game_row, resolution, preset,
            rt=rt, upscaling=upscaling, frame_generation=frame_generation)

    profile = supported_profile(label)
    if profile is not None:
        legacy = predict_legacy(cpu, gpu, profile, resolution=resolution,
                               preset=preset, ram_type=None, ram_channels=None,
                               ram_capacity_gb=None, rt=rt, upscaling=upscaling,
                               frame_generation=frame_generation)
        if legacy.get("average_fps") is not None:
            legacy_result = {
                **base,
                "average_fps": legacy["average_fps"],
                "status": "legacy_profile_estimate",
                "confidence_level": "legacy_profile",
                "confidence": "low",
                "measurement_type": "estimated",
                "method": legacy.get("method", "legacy_game_profile"),
                "source_evidence": legacy.get("sources", []),
                "workload_source": "UpgradeLab GAME_PROFILES / legacy FPS model",
                "limiting_component": None,
                "cpu_limit_assessed": False,
                "missing_data": ["independent CPU/GPU workload calibration", "verified per-game scene settings"],
                "warnings": legacy.get("warnings", []),
                "note": "Ориентир прежней модели для поддерживаемой игры, а не прямой замер и не независимая калибровка v4.",
            }
            return _with_gpu_reference_alternative(
                legacy_result, base, gpu, label, game_row, resolution, preset,
                rt=rt, upscaling=upscaling, frame_generation=frame_generation)
        base["missing_data"] = legacy.get("candidate_v2", {}).get("reason") and [legacy["candidate_v2"]["reason"]] or [
            "совместимые измерения для CPU/GPU и настроек игры"]
    else:
        base["missing_data"] = ["точные измерения CPU/GPU", "калиброванная игровая нагрузка или источник системных требований"]

    requested_settings = {"resolution": resolution, "preset": str(preset).casefold(),
                         "rt": bool(rt), "upscaling": str(upscaling).casefold(),
                         "frame_generation": bool(frame_generation)}
    # FPSHQ has independent GPU-only reference tables for 50 titles at 1080p,
    # 1440p and 4K High. They are used only when the selected settings match.
    fpshq = _fpshq_gpu_estimate(gpu, label, resolution, preset,
                                rt, upscaling, frame_generation)
    if fpshq is not None:
        return _gpu_only_result(
            base, fpshq, status="external_fpshq_gpu_only", requested_settings=requested_settings,
            note=(fpshq.get("note") or "FPSHQ GPU-only model estimate.") +
                 " Это не измерение CPU/GPU-связки.", source_name="FPSHQ")

    external = None
    if game_row is not None:
        external = estimate_gpu_fps(
            game_row.get("id"), gpu.name, getattr(gpu, "raw_score", None), getattr(gpu, "vram", None),
            resolution=resolution, preset=preset, rt=rt, upscaling=upscaling,
            frame_generation=frame_generation,
        )
        base["external_model_available"] = bool(external.get("available"))
        if external.get("fps") is not None:
            profile = profiles_by_id().get(str(game_row.get("id")), {})
            evidence = [{
                "title": f"PCGameBenchmarks — {profile.get('source_game_name')} · {point['gpu']}",
                "publisher": "PCGameBenchmarks", "url": external.get("source_url"),
                "dataset_url": external.get("dataset_url"), "dataset_revision": external.get("dataset_revision"),
                "fps": point["fps"], "gpu": point["gpu"],
                "settings": "1080p High · нативный рендер",
                "data_type": "external_model_estimate", "license": external.get("license"),
                "attribution": external.get("attribution"), "observed_date": external.get("snapshot_date"),
            } for point in external.get("reference_points", [])]
            return {
                **base, "status": "external_model_anchored", "confidence_level": "external_model_estimate",
                "confidence": external["confidence"], "measurement_type": "external_model_estimate",
                "method": external["method"], "gpu_oriented_fps": external["fps"],
                "gpu_estimate_details": external, "source_evidence": evidence,
                "workload_source": "PCGameBenchmarks external model estimates",
                "missing_data": ["CPU-specific game performance and bottleneck curve", "game scene and version"],
                "settings": {"resolution": "1080p", "preset": "high", "rt": False,
                             "upscaling": "off", "frame_generation": False},
                "source_settings": external.get("source_settings"),
                "note": "Приблизительная оценка видеокарты по внешней модели PCGameBenchmarks. Это не измерение и не прогноз FPS всей системы: результат зависит от CPU и конкретной сцены. Источник охватывает только 1080p High без RT, апскейлинга и генерации кадров; 1% Low и CPU-ограничение не оценивались.",
            }

        # Preserve a numeric source value when the game is known but the source
        # does not cover the requested mode. Keep the source settings explicit.
        if external.get("reason") == "external_source_covers_only_1080p_high_native_without_rt_or_frame_generation":
            baseline = estimate_gpu_fps(
                game_row.get("id"), gpu.name, getattr(gpu, "raw_score", None), getattr(gpu, "vram", None),
                resolution="1080p", preset="high", rt=False, upscaling="off", frame_generation=False,
            )
            if baseline.get("fps") is not None:
                return _gpu_only_result(
                    base, baseline, status="external_model_settings_fallback",
                    requested_settings=requested_settings,
                    note=("Для выбранных настроек источник не даёт прогноза. Показан только GPU-ориентир "
                          "этой игры при 1080p High; не трактуйте его как FPS выбранного разрешения, "
                          "пресета или полной системы."), source_name="PCGameBenchmarks")

        if external.get("reason") in {"above_safe_reference_range", "below_safe_reference_range"}:
            anchor = estimate_nearest_game_gpu_anchor(
                game_row.get("id"), gpu.name, getattr(gpu, "raw_score", None), getattr(gpu, "vram", None))
            if anchor.get("available"):
                return _gpu_only_result(
                    base, anchor, status="external_model_nearest_anchor_fallback",
                    requested_settings=requested_settings,
                    note=(anchor.get("note") or "Ближайшая опубликованная GPU-опора этой игры.") +
                         " Используется модельный результат ближайшей видеокарты; он не переносится "
                         "математически на выбранную видеокарту и относится к 1080p High.",
                    source_name="PCGameBenchmarks")

    # Last resort: a broad, source-derived population reference so the UI can
    # still show a number when no game-specific curve exists. It is never
    # represented as FPS for the selected game or full system.
    generic = estimate_catalog_gpu_reference(
        str(getattr(gpu, "name", "")), float(getattr(gpu, "raw_score", 0) or 0),
        getattr(gpu, "vram", None),
    )
    if generic.get("available"):
        base["external_model_available"] = True
        title_scope = "" if game_row is not None else "Для игры нет сопоставленной кривой. "
        settings_note = (" Источник использует 1080p High, тогда как выбраны другие настройки."
                         if requested_settings != generic.get("source_settings") else "")
        return _gpu_only_result(
            base, generic, status="catalog_gpu_reference_only",
            requested_settings=requested_settings,
            note=(title_scope + (generic.get("note") or "Общий GPU-ориентир по каталогу.") + settings_note +
                  " Число не описывает производительность CPU/GPU-связки."),
            source_name="PCGameBenchmarks")

    base["note"] = "Даже общий внешний GPU-ориентир для этой видеокарты отсутствует; FPS всей системы недоступен без сопоставимых данных."
    base["missing_data"] = ["GPU reference curve", "CPU/GPU system measurements"]
    return base


def relative_hardware_index(score: int | float | None,
                            peer_scores: list[int | float]) -> dict[str, Any]:
    """Return a within-component PassMark percentile, never an FPS estimate."""
    valid = sorted(float(value) for value in peer_scores if isinstance(value, (int, float)) and value > 0)
    if not isinstance(score, (int, float)) or score <= 0 or not valid:
        return {"score": score, "percentile": None, "peer_count": len(valid),
                "scale": "PassMark CPU Mark" if valid else None}
    percentile = round(100 * bisect_right(valid, float(score)) / len(valid), 1)
    return {"score": score, "percentile": percentile, "peer_count": len(valid),
            "scale": "PassMark score percentile within same hardware type",
            "note": "Относительный аппаратный индекс; не является игровым FPS и не сопоставляется между CPU и GPU."}


def relative_pair_proxy(cpu_score, gpu_score, cpu_scores, gpu_scores) -> dict[str, Any]:
    """Provide separate CPU/GPU rank data plus a balanced non-FPS proxy."""
    cpu = relative_hardware_index(cpu_score, cpu_scores)
    gpu = relative_hardware_index(gpu_score, gpu_scores)
    if cpu["percentile"] is None or gpu["percentile"] is None:
        balanced = None
    else:
        # Geometric mean on two independently normalized percentile axes.
        balanced = round((max(cpu["percentile"], 0.1) * max(gpu["percentile"], 0.1)) ** 0.5, 1)
    return {"cpu": cpu, "gpu": {**gpu, "scale": "PassMark G3D Mark percentile within GPU"},
            "balanced_percentile_proxy": balanced,
            "note": "CPU и GPU ранжируются отдельно; общий proxy предназначен только для сравнения комплектующих, не для FPS."}

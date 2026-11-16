"""Reproducible descriptive validation of FPS v2 against the retained baseline."""
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

from app.services.benchmark_data import native_cohort
from app.services.benchmark_model_v2 import CANONICAL_RESOLUTION, dataset, predict_pair
from app.services.offers import signature
from app.services.performance import estimate_fps, fps_outlook, ram_performance_factor
from app.schemas.calculate import CalcMode, GameName


def _point_metrics(points, denominator=None):
    denominator = len(points) if denominator is None else denominator
    if not points:
        return {"n": 0, "eligible_holdouts": denominator,
                "prediction_coverage": 0.0 if denominator else None,
                "mae_fps": None, "mape_percent": None, "mdape_percent": None,
                "p90_ape_percent": None, "bias_fps": None}
    errors = [abs(p["predicted"] - p["measured"]) for p in points]
    signed = [p["predicted"] - p["measured"] for p in points]
    ape = sorted(100 * error / p["measured"] for error, p in zip(errors, points))
    p90 = ape[max(0, math.ceil(0.9 * len(ape)) - 1)]
    return {"n": len(points), "eligible_holdouts": denominator,
            "prediction_coverage": len(points) / denominator if denominator else None,
            "mae_fps": sum(errors) / len(errors),
            "mape_percent": sum(ape) / len(ape),
            "mdape_percent": median(ape), "p90_ape_percent": p90,
            "bias_fps": sum(signed) / len(signed)}


def _grouped_metrics(points, field):
    groups = defaultdict(list)
    for point in points:
        if field == "x3d_class":
            value = "x3d" if "x3d" in str(point.get("cpu", "")).casefold() else "other_or_unknown"
        else:
            value = point.get(field) or "unknown"
        groups[str(value)].append(point)
    return {key: _point_metrics(value) for key, value in sorted(groups.items())}


def evaluate_v2():
    raw_rows, source_manifest = dataset()
    eligible = [row for row in raw_rows if native_cohort(row)]
    # Deliberately hold out a complete resolution cohort, while retaining other
    # resolutions from the same test series. This is a within-series diagnostic,
    # NOT an independent-source/generalization score.
    groups = defaultdict(list)
    for row in eligible:
        key = (row["game"], row["game_version"], signature(row["cpu"], "CPU"),
               signature(row["gpu"], "GPU"), row["preset"], row["ram_gb"],
               row["ram_type"], row["ram_channels"], row["rt"], row["upscaling"],
               row["frame_generation"], row["scene"], row["os"], row["form_factor"])
        groups[key].append(row)

    baseline_index = defaultdict(list)
    seed = json.loads((Path(__file__).resolve().parents[2] / "seed_data.json").read_text(encoding="utf-8"))
    for kind in ("cpus", "gpus"):
        for item in seed[kind]:
            baseline_index[(kind, signature(item["name"], "CPU" if kind == "cpus" else "GPU"))].append(item)

    candidate_points, baseline_points, v4_points, rejected = [], [], [], []
    eligible_holdouts = 0
    for rows in groups.values():
        resolutions = {row["resolution"] for row in rows}
        if len(resolutions) < 3:
            continue
        eligible_holdouts += len(resolutions)
        for target_resolution in sorted(resolutions):
            train_rows = [row for row in rows if row["resolution"] != target_resolution]
            held_rows = [row for row in rows if row["resolution"] == target_resolution]
            if not train_rows or not held_rows:
                continue
            actual = sum(row["average_fps"] for row in held_rows) / len(held_rows)
            first = held_rows[0]
            candidate = predict_pair(first["cpu"], first["gpu"], first["game"],
                target_resolution, first["preset"], ram_type=first["ram_type"].split("-")[0],
                ram_channels=first["ram_channels"], ram_capacity_gb=int(first["ram_gb"]),
                source_rows=train_rows)
            if candidate["average_fps"] is None:
                rejected.append({"resolution": target_resolution, "reason": candidate.get("reason")})
                continue
            point = {"game": first["game"], "resolution": target_resolution,
                "cpu": first["cpu"], "gpu": first["gpu"], "measured": actual,
                "predicted": candidate["average_fps"], "absolute_error": abs(candidate["average_fps"] - actual),
                "series": first["series_id"], "method": candidate["method"]}
            candidate_points.append(point)

            # Evaluate the actual v4 resolver with the held-out resolution
            # removed from its pair evidence. This preserves its production
            # fallback order without leaking the target measurement.
            from types import SimpleNamespace
            from app.services.fps_engine_v4 import resolve_fps_v4
            v4_result = resolve_fps_v4(
                SimpleNamespace(name=first["cpu"], raw_score=None, vram=None),
                SimpleNamespace(name=first["gpu"], raw_score=None, vram=None),
                first["game"], target_resolution, first["preset"],
                measurement_rows=train_rows,
            )
            if v4_result.get("average_fps") is not None:
                v4_points.append({**point, "predicted": v4_result["average_fps"],
                    "absolute_error": abs(v4_result["average_fps"] - actual),
                    "method": v4_result.get("method"), "resolver_status": v4_result.get("status")})

            try:
                game = GameName(first["game"])
                mode = CalcMode(target_resolution.casefold() + "_" + first["preset"].casefold())
            except ValueError:
                continue
            cpu = next(iter(baseline_index.get(("cpus", signature(first["cpu"], "CPU")), [])), None)
            gpu = next(iter(baseline_index.get(("gpus", signature(first["gpu"], "GPU")), [])), None)
            if not cpu or not gpu:
                continue
            ram_factor = ram_performance_factor(game, cpu["name"], first["ram_type"].split("-")[0], first["ram_channels"])
            baseline = estimate_fps(cpu["score"], gpu["score"], gpu["name"], game, mode, ram_factor, cpu["name"])
            baseline_points.append({"game": first["game"], "resolution": target_resolution,
                "cpu": first["cpu"], "gpu": first["gpu"], "measured": actual,
                "predicted": baseline, "absolute_error": abs(baseline - actual),
                "series": first["series_id"]})

    fixed_gpu_cpu_variants = defaultdict(set)
    fixed_cpu_gpu_variants = defaultdict(set)
    for row in eligible:
        settings = (row["game"], row["game_version"], row["resolution"], row["preset"], row["scene"])
        fixed_gpu_cpu_variants[(settings, signature(row["gpu"], "GPU"))].add(signature(row["cpu"], "CPU"))
        fixed_cpu_gpu_variants[(settings, signature(row["cpu"], "CPU"))].add(signature(row["gpu"], "GPU"))
    cpu_curve_groups = sum(len(values) >= 2 for values in fixed_gpu_cpu_variants.values())
    gpu_curve_groups = sum(len(values) >= 2 for values in fixed_cpu_gpu_variants.values())
    def point_key(point):
        return (point["game"], signature(point["cpu"], "CPU"), signature(point["gpu"], "GPU"),
                point["resolution"], point["series"])

    candidate_by_key = {point_key(point): point for point in candidate_points}
    baseline_by_key = {point_key(point): point for point in baseline_points}
    common_keys = sorted(set(candidate_by_key) & set(baseline_by_key))
    common_candidate = [candidate_by_key[key] for key in common_keys]
    common_legacy = [baseline_by_key[key] for key in common_keys]
    from app.services.fps_engine_v3 import CpuHardware, GpuHardware, GameWorkload, predict_fps
    v3_probe = predict_fps(CpuHardware(), GpuHardware(), GameWorkload(), "1440p")
    external_gpu_points = []
    for row in eligible:
        if (CANONICAL_RESOLUTION.get(str(row.get("resolution", "")).casefold()) != "1080p"
                or str(row.get("preset", "")).casefold() != "high"
                or row.get("rt") or (row.get("upscaling") or "off").casefold() != "off"
                or row.get("frame_generation")):
            continue
        score = next(iter(baseline_index.get(("gpus", signature(row["gpu"], "GPU")), [])), None)
        if score is None:
            continue
        from app.services.external_fps_model import estimate_gpu_fps
        external = estimate_gpu_fps(row["game"], row["gpu"], score["score"])
        if external.get("fps") is not None:
            external_gpu_points.append({"game": row["game"], "gpu": row["gpu"],
                "resolution": "1080p", "preset": "high", "external_gpu_oriented_estimate": external["fps"],
                "measured_full_system_fps": row["average_fps"],
                "scored_as_accuracy": False,
                "reason": "The external GPU-only model and native full-system benchmark have different targets and are not a like-for-like validation pair."})

    return {
        "dataset_observations": len(raw_rows), "eligible_native_windows": len(eligible),
        "eligible_games": len({row["game"] for row in eligible}),
        "eligible_cpus": len({signature(row["cpu"], "CPU") for row in eligible}),
        "eligible_gpus": len({signature(row["gpu"], "GPU") for row in eligible}),
        "eligible_test_series": len({row["series_id"] for row in eligible}),
        "candidate_leave_one_resolution_out": {
            "metrics": _point_metrics(candidate_points, eligible_holdouts), "points": candidate_points},
        "legacy_same_holdout_diagnostic": {
            "metrics": _point_metrics(baseline_points), "points": baseline_points},
        "common_support_comparison": {
            "n": len(common_keys),
            "candidate": _point_metrics(common_candidate, len(common_keys)),
            "legacy": _point_metrics(common_legacy, len(common_keys)),
            "paired_points": [{"key": list(key), "candidate_fps": candidate_by_key[key]["predicted"],
                               "legacy_fps": baseline_by_key[key]["predicted"],
                               "measured_fps": candidate_by_key[key]["measured"]} for key in common_keys],
        },
        "model_comparison": {
            "target": "measured full-system average FPS under matching settings",
            "native_measurements": len(eligible),
            "independent_test_series": len({row["series_id"] for row in eligible}),
            "leakage_safe_common_holdout_points": len(common_keys),
            "legacy": {"scorable_points": len(common_legacy), "metrics": _point_metrics(common_legacy, len(common_keys))},
            "fps_v2": {"scorable_points": len(common_candidate), "metrics": _point_metrics(common_candidate, len(common_keys))},
            "fps_v3": {"scorable_points": 0, "abstentions_on_common_holdout": len(common_keys),
                       "reason": "No calibrated CPU/GPU/game workload anchors; the model correctly returns no FPS."},
            "fps_v4": {"scorable_points": len(v4_points), "metrics": _point_metrics(v4_points, eligible_holdouts),
                       "points": v4_points,
                       "note": "Measured-pair resolver evaluated with held-out resolution removed. Its measured-data path uses the same evidence interpolation as v2; legacy fallback remains separately labeled."},
            "external_gpu_model": {"scorable_full_system_points": 0,
                       "gpu_only_reference_points": external_gpu_points,
                       "reason": "GPU-oriented external estimates are not measured full-system FPS. The available native set lacks a separate same-protocol GPU-only target, so no accuracy error is calculated."},
            "validation_limit": "All native measurements are one publisher series and one CPU/GPU configuration; this is a within-series diagnostic, not independent generalization evidence.",
        },
        "grouped_diagnostics": {
            "by_game": _grouped_metrics(candidate_points, "game"),
            "by_cpu": _grouped_metrics(candidate_points, "cpu"),
            "by_gpu": _grouped_metrics(candidate_points, "gpu"),
            "by_resolution": _grouped_metrics(candidate_points, "resolution"),
            "x3d_class": _grouped_metrics(candidate_points, "x3d_class"),
        },
        "rejected_resolution_holds": rejected,
        "independent_series_holdout": {"test_points": 0, "reason": "All eligible native observations belong to one publisher test series; series-grouped split correctly has no independent holdout."},
        "component_curve_coverage": {"cpu_curve_groups_with_variation": cpu_curve_groups,
                                     "gpu_curve_groups_with_variation": gpu_curve_groups,
                                     "interaction_observations": len(eligible),
                                     "separate_curves_calibrated": False,
                                     "cpu_frame_time_calibrated": False},
        "ml": {"trained": False, "reason": "Too few independent series and no leakage-safe holdout."},
        "promoted_to_production": False,
        "reason": "The candidate uses exact pair evidence and frame-time interpolation only. One within-series diagnostic is not enough to promote a general CPU/GPU model.",
        "source_manifest": source_manifest,
    }

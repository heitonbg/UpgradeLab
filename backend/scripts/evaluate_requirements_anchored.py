"""Read-only coverage and monotonicity evaluation for the experimental FPS scenario.

Example: python scripts/evaluate_requirements_anchored.py --database pc_upgrade.db
The source SQLite connection is always opened in read-only mode.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.external_fps_model import estimate_gpu_fps, gpu_device_class, package
from app.services.benchmark_estimates import fpshq_top50_rows
from app.services.benchmark_model_v2 import dataset as system_benchmark_dataset
from app.services.benchmark_data import native_cohort
from app.services.cpu_requirements import resolve_cpu_requirement
from app.services.game_catalog import catalog as game_catalog
from app.services.requirements_anchored_fps import (
    estimate_requirements_anchored_fps,
    minimum_log_curve_elasticity,
    requirements_anchored_coverage_summary,
    resolve_gpu_requirement,
)


def _read_hardware(database: Path) -> list[dict]:
    uri = "file:" + quote(str(database.resolve()).replace("\\", "/"), safe="/:\\") + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id, type, name, raw_score, vram FROM hardware "
            "WHERE type IN ('CPU', 'GPU') AND raw_score > 0 ORDER BY type, name"
        ).fetchall()
    return [dict(row) for row in rows]


def _percentile_rows(rows: list[dict], fractions=(0.20, 0.50, 0.80)) -> list[SimpleNamespace]:
    ordered = sorted(rows, key=lambda row: (float(row["raw_score"]), str(row["name"]).casefold()))
    if not ordered:
        return []
    selected = []
    for fraction in fractions:
        index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
        row = ordered[index]
        if not selected or row["id"] != selected[-1].id:
            selected.append(SimpleNamespace(**row))
    return selected


def run(database: Path, max_games: int = 100) -> dict:
    rows = _read_hardware(database)
    cpus = [SimpleNamespace(**row) for row in rows if row["type"] == "CPU"]
    gpu_rows = [row for row in rows if row["type"] == "GPU"
                and gpu_device_class(row["name"], row.get("vram")) == "desktop"]
    gpus = [SimpleNamespace(**row) for row in gpu_rows]
    summary = requirements_anchored_coverage_summary(cpus, gpus)
    profiles = list(package().get("profiles", []))
    ready = []
    for profile in profiles:
        for level in ("recommended", "minimum"):
            requirements = profile.get(f"{level}_requirements") or {}
            cpu_reference = resolve_cpu_requirement(requirements.get("cpu"), cpus)
            gpu_reference = resolve_gpu_requirement(requirements.get("gpu"), gpus)
            if (cpu_reference.get("status") == "resolved_exact_models"
                    and gpu_reference.get("status") == "resolved_exact_models"
                    and minimum_log_curve_elasticity(profile, "desktop") is not None):
                ready.append((profile, level, cpu_reference, gpu_reference))
                break

    cpu_probes = _percentile_rows([row for row in rows if row["type"] == "CPU"])
    gpu_probes = _percentile_rows(gpu_rows)
    scenario_count = 0
    monotonic_cpu_groups = 0
    monotonic_gpu_groups = 0
    monotonic_failures = []
    gpu_baseline_unavailable = 0
    games_tested = 0
    requirement_levels = Counter()
    for profile, level, _, _ in ready[:max_games]:
        requirement_levels[level] += 1
        per_gpu: dict[int, list[tuple[float, float]]] = {}
        per_cpu: dict[int, list[tuple[float, float]]] = {}
        for gpu in gpu_probes:
            base = estimate_gpu_fps(
                profile["game_id"], gpu.name, gpu.raw_score, getattr(gpu, "vram", None),
                resolution="1080p", preset="high", rt=False, upscaling="off",
                frame_generation=False,
            )
            if not base.get("available") or base.get("fps") is None:
                gpu_baseline_unavailable += len(cpu_probes)
                continue
            for cpu in cpu_probes:
                result = estimate_requirements_anchored_fps(
                    profile, cpu, gpu, cpus, gpus, base
                )
                if not result.get("available"):
                    continue
                scenario_count += 1
                per_gpu.setdefault(gpu.id, []).append((float(cpu.raw_score), result["scenario_fps"]))
                per_cpu.setdefault(cpu.id, []).append((float(gpu.raw_score), result["scenario_fps"]))
        for group_name, groups in (("cpu", per_gpu), ("gpu", per_cpu)):
            for group in groups.values():
                ordered = sorted(group)
                checks = [(left[1], right[1]) for left, right in zip(ordered, ordered[1:])]
                if not checks:
                    continue
                valid = all(left <= right + 1e-9 for left, right in checks)
                if group_name == "cpu":
                    monotonic_cpu_groups += 1
                else:
                    monotonic_gpu_groups += 1
                if not valid:
                    monotonic_failures.append({"game_id": profile["game_id"], "axis": group_name})
        games_tested += 1

    fpshq_rows = fpshq_top50_rows()
    system_rows, _ = system_benchmark_dataset()
    strict_system_rows = [row for row in system_rows if native_cohort(row)]
    coverage = summary
    report = {
        "report_type": "requirements_anchored_fps_coverage_and_monotonicity",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": str(database.resolve()),
        "database_access": "read_only_mode",
        "game_catalog_selectable_games": len(game_catalog()),
        "source": {key: (package().get("source") or {}).get(key) for key in (
            "dataset", "repository", "publisher", "attribution", "license", "license_url",
            "git_revision", "snapshot_date", "source_game_rows", "source_gpu_rows",
            "fps_reference_gpu_count", "fps_settings", "data_type")},
        "coverage": coverage,
        "available_data": {
            "pcgb_game_profiles": len(profiles),
            "pcgb_gpu_reference_points": sum(len(row.get("fps_by_reference_gpu") or {}) for row in profiles),
            "fpshq_gpu_rows": len(fpshq_rows),
            "fpshq_games": len({row.get("game") for row in fpshq_rows}),
            "fpshq_gpu_models": len({row.get("gpu") for row in fpshq_rows}),
            "fpshq_source_types": dict(Counter(str(row.get("source") or "unknown") for row in fpshq_rows)),
            "strict_system_measurements": len(strict_system_rows),
            "strict_system_games": len({row.get("game") for row in strict_system_rows}),
            "strict_system_test_series": len({row.get("series_id") for row in strict_system_rows if row.get("series_id")}),
        },
        "validation": {
            "requested_max_games": max_games,
            "eligible_games_found": len(ready),
            "eligible_games_tested": games_tested,
            "requirement_tiers_used": dict(requirement_levels),
            "cpu_probe_count": len(cpu_probes),
            "desktop_gpu_probe_count": len(gpu_probes),
            "experimental_scenarios_computed": scenario_count,
            "gpu_baseline_unavailable_cases": gpu_baseline_unavailable,
            "monotonic_cpu_groups": monotonic_cpu_groups,
            "monotonic_gpu_groups": monotonic_gpu_groups,
            "monotonicity_failures": monotonic_failures,
            "accuracy_validation": "Not scored as accuracy. Local strict system measurements do not provide a same-game, same-settings holdout for this 1080p High model.",
        },
        "interpretation": "Coverage and mathematical invariants only. The scenarios are not independent measurements, and successful monotonicity checks do not validate FPS accuracy.",
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=BACKEND / "pc_upgrade.db")
    parser.add_argument("--output", type=Path,
                        default=BACKEND / "app" / "data" / "benchmarks" / "fps_requirements_anchored_coverage.json")
    parser.add_argument("--games", type=int, default=100, choices=range(1, 1001))
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error(f"SQLite database not found: {args.database}")
    report = run(args.database, args.games)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

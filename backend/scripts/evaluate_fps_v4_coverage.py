from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from pathlib import Path
from collections import Counter
from urllib.parse import quote

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.cpu_requirements import (CpuRequirementResolver, parse_cpu_requirement,
    requirement_coverage_summary, requirement_resolution_summary)
from app.services.external_fps_model import estimate_gpu_fps, gpu_device_class, match_source_gpu, package, profiles_by_id, _points, _interpolate_log
from app.services.cpu_requirements import assess_cpu_adequacy


def old_class(name: str, vram: int | float | None) -> str:
    import re
    label = str(name or "")
    if re.search(r"\bintel\s+(?:iris|uhd|hd)\b|\biris\s+xe\b|\bradeon\s+(?:780m|graphics|vega\s*\d+)\b|\bapu\b", label, re.I):
        return "integrated"
    if re.search(r"\b(?:laptop|mobile|max[ -]?q)\b|\b(?:gtx|rtx|rx)\s*\d+(?:\s*(?:xt|ti|super))?\s*m\b", label, re.I):
        return "mobile"
    if re.search(r"\b(?:geforce|gtx|rtx|radeon\s+rx|intel\s+arc\s+[ab]\d|quadro|firepro)\b", label, re.I):
        return "desktop"
    if isinstance(vram, (int, float)) and vram >= 2:
        return "desktop"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only CPU/GPU coverage evaluation against the local Hardware catalog.")
    parser.add_argument("--sqlite-path", type=Path, required=True, help="Existing local SQLite file. It is opened with mode=ro and query_only=ON.")
    parser.add_argument("--output", type=Path, help="Optional path for a UTF-8 JSON coverage report.")
    args = parser.parse_args()
    path = args.sqlite_path.resolve(strict=True)
    uri = path.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(hardware)")}
        selected = [name for name in ("id", "type", "name", "raw_score", "vram") if name in columns]
        hardware = [dict(zip(selected, row)) for row in connection.execute(
            f"SELECT {', '.join(selected)} FROM hardware WHERE raw_score > 0")]
    finally:
        connection.close()

    document = package()
    profiles = list(profiles_by_id().values())
    profile = next((item for item in profiles if item.get("game_id") == "CS2"), profiles[0])
    gpu_rows = [row for row in hardware if row["type"] == "GPU"]
    baseline = Counter()
    current = Counter()
    classes = Counter()
    supported_by_class = Counter()
    inferred_source_matches = 0
    crosswalks = Counter()
    newly_supported = []
    newly_supported_count = 0
    lost_support = []
    old_supported_only_reasons = Counter()
    started = time.perf_counter()
    for gpu in gpu_rows:
        legacy_class = old_class(gpu["name"], gpu.get("vram"))
        if legacy_class in {"desktop", "integrated"}:
            legacy_points = _points(profile, legacy_class)
            old_fps, _, old_reason = _interpolate_log(legacy_points, float(gpu["raw_score"]))
        else:
            old_fps, old_reason = None, "unsupported_device_class"
        old_supported_row = old_fps is not None
        baseline["supported" if old_supported_row else old_reason] += 1

        device_class = gpu_device_class(gpu["name"], gpu.get("vram"))
        classes[device_class] += 1
        match = match_source_gpu(gpu["name"], device_class)
        crosswalks[match["status"]] += 1
        estimate = estimate_gpu_fps(profile["game_id"], gpu["name"], gpu["raw_score"], gpu.get("vram"))
        new_supported_row = estimate.get("fps") is not None
        current["supported" if new_supported_row else estimate.get("reason", "unknown")] += 1
        if new_supported_row:
            supported_by_class[device_class] += 1
        if (estimate.get("gpu_match") or {}).get("status") == "exact_source_model_device_type_inferred":
            inferred_source_matches += 1
        if new_supported_row and not old_supported_row:
            newly_supported_count += 1
            if len(newly_supported) < 20:
                newly_supported.append({"id": gpu["id"], "name": gpu["name"], "fps": estimate["fps"],
                                        "method": estimate["method"], "gpu_match": estimate.get("gpu_match"),
                                        "score_source": estimate.get("gpu_score_provenance")})
        if old_supported_row and not new_supported_row:
            old_supported_only_reasons[estimate.get("reason", "unknown")] += 1
            if len(lost_support) < 20:
                lost_support.append({"id": gpu["id"], "name": gpu["name"], "reason": estimate.get("reason"),
                                     "device_class": device_class})
    elapsed_gpu = time.perf_counter() - started

    cpu_rows = [row for row in hardware if row["type"] == "CPU"]
    resolver = CpuRequirementResolver(cpu_rows)
    parse_coverage = requirement_coverage_summary(profiles)
    resolver_counts = Counter()
    exact_fields = 0
    partial_fields = 0
    unresolved = 0
    exact_cpu_ids = set()
    family_cpu_ids = set()
    for item in profiles:
        for field in ("minimum_requirements", "recommended_requirements"):
            raw = (item.get(field) or {}).get("cpu")
            if not raw:
                continue
            result = resolver.resolve(raw)
            resolver_counts[result["status"]] += 1
            if result["status"] in {"resolved_exact_models", "partially_resolved"}:
                exact_cpu_ids.update(ref["id"] for ref in result.get("resolved_models", []) if ref.get("id") is not None)
            elif result["status"] == "resolved_family_range":
                family_cpu_ids.update(ref["id"] for ref in result.get("resolved_models", []) if ref.get("id") is not None)
            if result["status"] == "resolved_exact_models":
                exact_fields += 1
            elif result["status"] == "partially_resolved":
                partial_fields += 1
            elif result["status"] not in {"resolved_family_range"}:
                unresolved += 1
    sample_profiles = {item["game_id"]: item for item in profiles if item.get("game_id") in {"Cyberpunk 2077", "CS2"}}
    cpu_examples = []
    for wanted in ("AMD Ryzen 5 5600", "Intel Core i5-12400F", "AMD Ryzen 7 7800X3D"):
        cpu = next((row for row in cpu_rows if row["name"].casefold() == wanted.casefold()), None)
        game_profile = sample_profiles.get("Cyberpunk 2077")
        if cpu and game_profile:
            assessment = assess_cpu_adequacy(game_profile, type("CPU", (), cpu)(), cpu_rows)
            cpu_examples.append({"game": game_profile["catalog_name"], "cpu": cpu["name"],
                                 "cpu_mark": cpu["raw_score"], "status": assessment["status"],
                                 "minimum_index": (assessment.get("minimum") or {}).get("index_vs_reference_percent"),
                                 "recommended_index": (assessment.get("recommended") or {}).get("index_vs_reference_percent")})

    # Batch-check every external game using the same real catalog GPU. These
    # are model availability checks, not independent measurements or system FPS.
    reference_gpu = next((row for row in gpu_rows if row["name"].casefold() == "geforce rtx 3060"), None)
    batch_counts = Counter()
    batch_started = time.perf_counter()
    if reference_gpu:
        for game_profile in profiles:
            points = game_profile.get("fps_by_reference_gpu") or {}
            numeric_points = sum(isinstance(value, (int, float)) and value > 0 and math.isfinite(float(value))
                                 for value in points.values())
            batch_counts[f"reference_curve_{numeric_points}_of_12"] += 1
            prediction = estimate_gpu_fps(game_profile["game_id"], reference_gpu["name"],
                                          reference_gpu["raw_score"], reference_gpu.get("vram"))
            batch_counts["numeric_gpu_oriented_estimate" if prediction.get("fps") is not None
                         else prediction.get("reason", "unknown")] += 1
    batch_elapsed = time.perf_counter() - batch_started

    output = {
        "hardware_catalog": {"cpu_count": len(cpu_rows), "gpu_count": len(gpu_rows), "database_open_mode": "read-only"},
        "gpu_coverage": {"comparison_game": profile["catalog_name"], "supported_before_old_classifier": baseline["supported"],
                         "supported_after_safe_crosswalk": current["supported"],
                         "coverage_change_from_old_count": current["supported"] - baseline["supported"],
                         "reason_counts_before": dict(baseline), "reason_counts_after": dict(current),
                         "old_supported_but_now_abstained_reasons": dict(old_supported_only_reasons),
                         "classified_device_counts": dict(classes), "supported_by_device_class": dict(supported_by_class),
                         "source_crosswalk_counts": dict(crosswalks),
                         "exact_source_score_matches": crosswalks["exact_source_model_and_device_type"],
                         "inferred_exact_source_device_type_matches_used": inferred_source_matches,
                         "newly_supported_count": newly_supported_count,
                         "newly_supported_examples": newly_supported[:5], "no_longer_supported_examples": lost_support[:5],
                         "elapsed_seconds": round(elapsed_gpu, 3),
                         "interpretation": "Счёт охвата относится к GPU с достаточным сопоставимым G3D баллом для одной эталонной игровой кривой, а не к количеству подтверждённых FPS всей системы."},
        "cpu_requirements": {"source_parse_coverage": parse_coverage, "exactly_resolved_requirement_fields": exact_fields,
                              "partially_resolved_requirement_fields": partial_fields,
                              "family_or_abstract_unresolved_fields": unresolved,
                              "unique_exact_cpu_models_referenced": len(exact_cpu_ids),
                              "unique_generation_family_cpu_models_referenced": len(family_cpu_ids),
                              "resolved_game_coverage_against_local_catalog": requirement_resolution_summary(profiles, cpu_rows),
                              "resolver_status_counts": dict(resolver_counts), "sample_adequacy": cpu_examples,
                              "interpretation": "Adequacy сравнивает суммарный PassMark CPU Mark моделей из системных требований; это не Single Thread, FPS или CPU bottleneck."},
        "all_game_batch": {"external_profiles": len(profiles), "gpu_test_target": reference_gpu["name"] if reference_gpu else None,
                           "status_counts": dict(batch_counts), "elapsed_seconds": round(batch_elapsed, 3),
                           "interpretation": "Проверяет пакетно существующий GPU-ориентир для 1080p High по одной GPU каталога; не является 16k независимыми игровыми тестами и не оценивает FPS всей системы."},
        "source": {"url": document["source"]["repository"], "revision": document["source"]["git_revision"],
                   "gpu_rows": len(document["gpu_catalog"]),
                   "gpu_type_counts": dict(Counter(row["source_device_type"] for row in document["gpu_catalog"]))},
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()

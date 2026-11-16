"""Build a versioned PCGameBenchmarks FPS estimate package.

This script never opens or writes UpgradeLab's SQLite database. It preserves
catalog IDs and imports only auditable, unambiguous source matches.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = BACKEND_ROOT / "app" / "data" / "external_fps" / "pcgamebenchmarks" / "source"
DEFAULT_OUTPUT_DIR = DEFAULT_SOURCE_DIR.parent
SOURCE_URL = "https://github.com/emilioagustin83/pc-game-fps-dataset"
ATTRIBUTION = "PCGameBenchmarks — https://pcgamebenchmarks.com"
LICENSE = "CC BY 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
# Exact Steam AppID crosswalks verified from the official store pages. These
# IDs disambiguate display-name variants without merging remakes or editions.
VERIFIED_STEAM_APPID_CROSSWALK = {
    "Baldur's Gate 3": {"steam_app_id": "1086940", "evidence_url": "https://store.steampowered.com/app/1086940/Baldurs_Gate_3/"},
    "Overwatch 2": {"steam_app_id": "2357570", "evidence_url": "https://store.steampowered.com/app/2357570/Overwatch_2/"},
}

REFERENCE_COLUMNS = {
    "fps_1080p_high_iris_xe": ("Intel Iris Xe", "integrated"),
    "fps_1080p_high_radeon_780m": ("Radeon 780M", "integrated"),
    "fps_1080p_high_gtx_1650": ("GeForce GTX 1650", "desktop"),
    "fps_1080p_high_gtx_1660_super": ("GeForce GTX 1660 SUPER", "desktop"),
    "fps_1080p_high_rtx_3060": ("GeForce RTX 3060", "desktop"),
    "fps_1080p_high_rx_7600": ("Radeon RX 7600", "desktop"),
    "fps_1080p_high_rtx_4060": ("GeForce RTX 4060", "desktop"),
    "fps_1080p_high_rtx_5060": ("GeForce RTX 5060", "desktop"),
    "fps_1080p_high_rtx_4070": ("GeForce RTX 4070", "desktop"),
    "fps_1080p_high_rx_7800_xt": ("Radeon RX 7800 XT", "desktop"),
    "fps_1080p_high_rtx_5070": ("GeForce RTX 5070", "desktop"),
    "fps_1080p_high_rtx_4090": ("GeForce RTX 4090", "desktop"),
}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return False
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
        temp_path = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp_path, path)
    return True


def _load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader), list(reader.fieldnames or [])


def _number(value: Any, *, integer: bool = False) -> int | float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).strip())
    except (ValueError, TypeError):
        return None
    if not math.isfinite(number):
        return None
    if integer and number.is_integer():
        return int(number)
    return number


def _runtime_catalog(catalog_path: Path) -> list[dict[str, Any]]:
    # Keep catalog identity behavior aligned with game_catalog.catalog(), without
    # evaluating benchmark coverage or touching a database during import.
    import sys
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.schemas.calculate import GameName
    from app.services.game_catalog import ALIASES, key

    base = json.loads(catalog_path.read_text(encoding="utf-8"))["games"]
    alias_path = catalog_path.with_name("game_aliases.json")
    imported_aliases = json.loads(alias_path.read_text(encoding="utf-8")).get("aliases", {})
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for enum in GameName:
        aliases = list(dict.fromkeys([*ALIASES.get(enum.value, []), *imported_aliases.get(enum.value, [])]))
        result.append({"id": enum.value, "name": enum.value, "aliases": aliases,
                       "source_url": None, "release_year": None, "steam_app_id": None})
        seen.update(key(item) for item in [enum.value, *aliases])
    for item in base:
        if key(item.get("name", "")) in seen:
            continue
        seen.add(key(item.get("name", "")))
        result.append(item)
    for item in result:
        verified = VERIFIED_STEAM_APPID_CROSSWALK.get(item.get("name", ""))
        if verified:
            item["steam_app_id"] = verified["steam_app_id"]
            item["steam_app_id_evidence_url"] = verified["evidence_url"]
    return result


def _reference_anchors(gpu_rows: list[dict[str, str]], model_key) -> list[dict[str, Any]]:
    by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in gpu_rows:
        by_key[model_key(row.get("name", ""))].append(row)
    anchors = []
    for column, (expected_name, device_class) in REFERENCE_COLUMNS.items():
        candidates = by_key.get(model_key(expected_name), [])
        if len(candidates) != 1:
            raise ValueError(f"Reference GPU must map uniquely: {expected_name}; found {len(candidates)}")
        source = candidates[0]
        score = _number(source.get("g3d_mark"), integer=True)
        if score is None or score <= 0:
            raise ValueError(f"Invalid G3D score for reference GPU {expected_name}")
        if device_class == "desktop" and source.get("type") != "Desktop":
            raise ValueError(f"Unexpected source device class for {expected_name}: {source.get('type')}")
        anchors.append({"column": column, "name": expected_name, "g3d_mark": score,
                        "device_class": device_class, "source_device_type": source.get("type") or "Unknown",
                        "page_url": source.get("page_url") or None})
    if len({a["g3d_mark"] for a in anchors}) != len(anchors):
        raise ValueError("Reference GPU G3D scores must be unique")
    return anchors


def _match_game(game: dict[str, Any], indexes: dict[str, Any], key) -> tuple[dict[str, str] | None, str | None, float, str | None]:
    source_rows = indexes["rows"]
    app_id = game.get("steam_app_id") or game.get("appid")
    if app_id:
        matches = indexes["app_id"].get(str(app_id), [])
        if len(matches) == 1:
            return matches[0], "steam_app_id", 1.0, None
        if len(matches) > 1:
            return None, None, 0.0, "ambiguous_steam_app_id"

    # This catalog already carries an exact page URL from the same publisher's
    # earlier name-only snapshot; it is a stronger identity link than title text.
    source_url = (game.get("source_url") or "").rstrip("/").casefold()
    if source_url:
        matches = indexes["page_url"].get(source_url, [])
        if len(matches) == 1:
            return matches[0], "exact_source_url", 1.0, None
        if len(matches) > 1:
            return None, None, 0.0, "ambiguous_source_url"

    exact = indexes["name"].get(key(game.get("name", "")), [])
    if len(exact) == 1:
        return exact[0], "exact_name", 0.99, None
    if len(exact) > 1 and game.get("release_year") is not None:
        same_year = [row for row in exact if str(row.get("release_year") or "") == str(game["release_year"])]
        if len(same_year) == 1:
            return same_year[0], "name_release_year", 0.99, None

    aliases = list(dict.fromkeys(game.get("aliases") or []))
    alias_matches: dict[str, dict[str, str]] = {}
    alias_ambiguous = False
    for alias in aliases:
        candidates = indexes["name"].get(key(alias), [])
        if len(candidates) == 1:
            alias_matches[candidates[0].get("page_url", "")] = candidates[0]
        elif len(candidates) > 1:
            year = game.get("release_year")
            year_matches = [row for row in candidates if year is not None and str(row.get("release_year") or "") == str(year)]
            if len(year_matches) == 1:
                alias_matches[year_matches[0].get("page_url", "")] = year_matches[0]
            else:
                alias_ambiguous = True
    if len(alias_matches) == 1:
        return next(iter(alias_matches.values())), "confirmed_alias", 0.95, None
    if len(alias_matches) > 1 or alias_ambiguous:
        return None, None, 0.0, "ambiguous_alias"

    # Fuzzy candidates are recorded for review only and never auto-imported.
    candidates = {row.get("page_url", ""): row for title in [game.get("name", ""), *aliases]
                  for row in indexes["name"].get(key(title), [])}
    if candidates:
        return None, None, 0.0, "ambiguous_exact_title"
    return None, None, 0.0, "no_exact_or_confirmed_alias_match"


def _fuzzy_candidates(game: dict[str, Any], indexes: dict[str, Any], key) -> list[dict[str, Any]]:
    # Candidate generation only: candidates are emitted for review, never auto-matched.
    name_keys = indexes["name"].keys()
    candidates: dict[str, tuple[dict[str, str], float]] = {}
    for query in [game.get("name", ""), *(game.get("aliases") or [])]:
        normalized = key(query)
        if not normalized:
            continue
        for candidate_key in difflib.get_close_matches(normalized, name_keys, n=5, cutoff=0.78):
            ratio = difflib.SequenceMatcher(None, normalized, candidate_key).ratio()
            for row in indexes["name"].get(candidate_key, []):
                url = row.get("page_url", "")
                if url and (url not in candidates or ratio > candidates[url][1]):
                    candidates[url] = (row, ratio)
    return [{"name": row.get("name"), "release_year": row.get("release_year") or None,
             "steam_app_id": row.get("steam_appid") or None, "source_url": row.get("page_url"),
             "similarity_candidate_score": round(ratio, 3)}
            for row, ratio in sorted(candidates.values(), key=lambda item: item[1], reverse=True)[:5]]


def build_package(source_dir: Path, output_dir: Path, catalog_path: Path,
                  source_revision: str = "299e6f38ed48eda91235bbc451096f5e6fd62910",
                  retrieved_at: str = "2026-11-15") -> dict[str, Any]:
    import sys
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.services.hardware_matching import model_key
    from app.services.game_catalog import key

    game_rows, game_columns = _load_csv(source_dir / "games.csv")
    gpu_rows, _ = _load_csv(source_dir / "gpus.csv")
    required_fps_columns = set(REFERENCE_COLUMNS)
    missing_columns = required_fps_columns - set(game_columns)
    if missing_columns:
        raise ValueError(f"PCGameBenchmarks CSV is missing FPS columns: {sorted(missing_columns)}")

    anchors = _reference_anchors(gpu_rows, model_key)
    indexes: dict[str, Any] = {"rows": game_rows, "app_id": defaultdict(list),
                               "page_url": defaultdict(list), "name": defaultdict(list)}
    for row in game_rows:
        if row.get("steam_appid"):
            indexes["app_id"][str(row["steam_appid"])].append(row)
        if row.get("page_url"):
            indexes["page_url"][row["page_url"].rstrip("/").casefold()].append(row)
        indexes["name"][key(row.get("name", ""))].append(row)

    files = ["games.csv", "gpus.csv", "LICENSE", "README.md", "CITATION.cff"]
    source_manifest = {
        "dataset": "PC Game System Requirements & Estimated FPS by GPU",
        "repository": SOURCE_URL,
        "publisher": "PCGameBenchmarks",
        "attribution": ATTRIBUTION,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "git_revision": source_revision,
        "snapshot_date": "2026-11-01",
        "retrieved_at": retrieved_at,
        "files_sha256": {name: _hash(source_dir / name) for name in files},
        "source_game_rows": len(game_rows),
        "source_gpu_rows": len(gpu_rows),
        "fps_reference_gpu_count": len(anchors),
        "fps_settings": {"resolution": "1080p", "preset": "High", "ray_tracing": False,
                         "upscaling": "off", "frame_generation": False},
        "data_type": "external_model_estimate",
        "source_method_summary": "PCGameBenchmarks estimates GPU FPS from Steam requirements and reference GPU G3D scores; its README reports calibration against measured GameGPU/Notebookcheck results. These CSV values are not measurements.",
        "verified_steam_appid_crosswalk": VERIFIED_STEAM_APPID_CROSSWALK,
    }
    profile_records: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    method_counts: Counter[str] = Counter()
    fps_count = 0
    invalid_values = 0
    monotonic_rejected = 0
    seen_game_ids: set[str] = set()
    seen_source_urls: dict[str, str] = {}
    appid_coverage = min_req_coverage = rec_req_coverage = release_year_coverage = 0
    engine_cap_coverage = 0

    runtime_games = _runtime_catalog(catalog_path)
    for game in runtime_games:
        game_id = str(game.get("id", ""))
        if not game_id or game_id in seen_game_ids:
            raise ValueError(f"Catalog has a missing or duplicate internal ID: {game_id!r}")
        seen_game_ids.add(game_id)
        source, method, confidence, reason = _match_game(game, indexes, key)
        if source is None:
            review.append({"game_id": game_id, "catalog_name": game.get("name"),
                           "reason": reason, "candidate_titles": [game.get("name"), *(game.get("aliases") or [])],
                           "fuzzy_candidates_for_manual_review": _fuzzy_candidates(game, indexes, key)})
            continue
        source_url = (source.get("page_url") or "").rstrip("/")
        if not source_url:
            review.append({"game_id": game_id, "catalog_name": game.get("name"),
                           "reason": "source_page_url_missing", "candidate_titles": [game.get("name")]})
            continue
        if source_url in seen_source_urls and seen_source_urls[source_url] != game_id:
            review.append({"game_id": game_id, "catalog_name": game.get("name"),
                           "reason": "source_row_already_matched_to_another_game_id",
                           "candidate_titles": [source.get("name")]})
            continue

        fps_map: dict[str, int | float] = {}
        errors = []
        by_column = {anchor["column"]: anchor for anchor in anchors}
        for column in REFERENCE_COLUMNS:
            value = _number(source.get(column))
            if value is None or value <= 0:
                invalid_values += 1
                errors.append(column)
                continue
            fps_map[by_column[column]["name"]] = int(value) if value.is_integer() else value

        ordered = sorted((anchor for anchor in anchors if anchor["name"] in fps_map),
                         key=lambda anchor: anchor["g3d_mark"])
        fps_values = [fps_map[anchor["name"]] for anchor in ordered]
        if any(fps_values[index] > fps_values[index + 1] for index in range(len(fps_values) - 1)):
            monotonic_rejected += 1
            review.append({"game_id": game_id, "catalog_name": game.get("name"),
                           "reason": "non_monotonic_reference_gpu_order", "source_url": source_url})
            continue
        if not fps_map:
            review.append({"game_id": game_id, "catalog_name": game.get("name"),
                           "reason": "no_valid_fps_points", "source_url": source_url})
            continue

        minimum = {"gpu": source.get("min_gpu") or None, "cpu": source.get("min_cpu") or None,
                   "ram_gb": _number(source.get("min_ram_gb"), integer=True),
                   "gpu_g3d": _number(source.get("min_gpu_g3d"), integer=True)}
        recommended = {"gpu": source.get("rec_gpu") or None, "cpu": source.get("rec_cpu") or None,
                      "ram_gb": _number(source.get("rec_ram_gb"), integer=True),
                      "gpu_g3d": _number(source.get("rec_gpu_g3d"), integer=True)}
        year = _number(source.get("release_year"), integer=True)
        cap = _number(source.get("engine_fps_cap"), integer=True)
        record = {
            "game_id": game_id,
            "catalog_name": game.get("name"),
            "source_game_name": source.get("name"),
            "steam_app_id": str(source["steam_appid"]) if source.get("steam_appid") else None,
            "release_year": year,
            "source_url": source_url,
            "match_method": method,
            "match_confidence": confidence,
            "match_evidence_url": game.get("steam_app_id_evidence_url"),
            "minimum_requirements": minimum if any(value is not None for value in minimum.values()) else None,
            "recommended_requirements": recommended if any(value is not None for value in recommended.values()) else None,
            "engine_fps_cap": cap,
            "fps_resolution": "1080p",
            "fps_preset": "High",
            "ray_tracing": False,
            "upscaling": "off",
            "frame_generation": False,
            "data_type": "external_model_estimate",
            "fps_by_reference_gpu": fps_map,
            "invalid_fps_columns": errors,
        }
        profile_records.append(record)
        method_counts[method] += 1
        fps_count += len(fps_map)
        if record["steam_app_id"]: appid_coverage += 1
        if minimum["gpu"] or minimum["cpu"] or minimum["ram_gb"] is not None: min_req_coverage += 1
        if recommended["gpu"] or recommended["cpu"] or recommended["ram_gb"] is not None: rec_req_coverage += 1
        if year is not None: release_year_coverage += 1
        if cap is not None: engine_cap_coverage += 1
        seen_source_urls[source_url] = game_id

    manifest_bytes = (json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    gpu_catalog = []
    for row in gpu_rows:
        score = _number(row.get("g3d_mark"), integer=True)
        name = (row.get("name") or "").strip()
        if not name or score is None or score <= 0:
            continue
        gpu_catalog.append({"name": name, "g3d_mark": score,
                            "source_device_type": (row.get("type") or "Unknown").strip() or "Unknown",
                            "page_url": (row.get("page_url") or "").strip() or None})
    gpu_catalog.sort(key=lambda item: (item["name"].casefold(), item["source_device_type"], item["g3d_mark"]))
    gpu_type_counts = dict(Counter(item["source_device_type"] for item in gpu_catalog))
    package = {"source": source_manifest, "reference_gpus": sorted(anchors, key=lambda item: item["g3d_mark"]),
               "gpu_catalog": gpu_catalog, "profiles": profile_records}
    package_bytes = (json.dumps(package, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    from app.services.cpu_requirements import requirement_coverage_summary
    cpu_requirements = requirement_coverage_summary(profile_records)
    report = {
        "generated_at": retrieved_at,
        "cpu_requirement_parse_coverage": cpu_requirements,
        "source_revision": source_revision,
        "runtime_catalog_games": len(runtime_games),
        "source_games": len(game_rows),
        "source_reference_gpus": len(anchors),
        "source_gpu_catalog_rows": len(gpu_catalog),
        "source_gpu_catalog_type_counts": gpu_type_counts,
        "source_gpu_rows_without_positive_g3d_score": len(gpu_rows) - len(gpu_catalog),
        "matched_games": len(profile_records),
        "match_method_counts": dict(method_counts),
        "unmatched_or_review_games": len(review),
        "review_items": review,
        "external_model_estimate_records": fps_count,
        "games_with_external_fps": len(profile_records),
        "invalid_fps_points_skipped": invalid_values,
        "non_monotonic_games_rejected": monotonic_rejected,
        "steam_app_id_coverage": appid_coverage,
        "minimum_requirements_coverage": min_req_coverage,
        "recommended_requirements_coverage": rec_req_coverage,
        "release_year_coverage": release_year_coverage,
        "engine_fps_cap_coverage": engine_cap_coverage,
        "note": "Every imported FPS point is an external model estimate, not a real measurement. Unmatched/fuzzy candidates are not imported.",
    }
    report_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write(output_dir / "source_manifest.json", manifest_bytes)
    _atomic_write(output_dir / "profiles.json", package_bytes)
    _atomic_write(output_dir / "import_report.json", report_bytes)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR,
                        help="Directory containing the unmodified PCGameBenchmarks CSV/license snapshot")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--catalog", type=Path, default=BACKEND_ROOT / "app" / "data" / "game_catalog.json")
    parser.add_argument("--revision", default="299e6f38ed48eda91235bbc451096f5e6fd62910")
    parser.add_argument("--retrieved-at", default="2026-11-15")
    args = parser.parse_args()
    report = build_package(args.source_dir, args.output_dir, args.catalog, args.revision, args.retrieved_at)
    print(json.dumps({key: value for key, value in report.items() if key != "review_items"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

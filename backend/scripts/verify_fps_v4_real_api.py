"""Exercise the FPS API against a real local Hardware catalog, read-only.

Usage from backend/: .venv/Scripts/python.exe scripts/verify_fps_v4_real_api.py \
    --sqlite-path pc_upgrade.db --games 100
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.api.deps import get_db
from app.api.calculate import router as calculate_router
from app.api.games import router as games_router
from app.services.game_catalog import catalog
from app.services.external_fps_model import estimate_gpu_fps, gpu_device_class


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only FPS API check against the existing local SQLite catalog.")
    parser.add_argument("--sqlite-path", type=Path, required=True)
    parser.add_argument("--games", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.games <= 500:
        parser.error("--games must be in [1, 500]")
    path = args.sqlite_path.resolve(strict=True)

    read_connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, check_same_thread=False)
    read_connection.execute("PRAGMA query_only=ON")
    rows = read_connection.execute(
        "SELECT id, type, name, raw_score, vram FROM hardware WHERE raw_score > 0"
    ).fetchall()
    gpu_rows = [row for row in rows if row[1] == "GPU"]
    gpu_classes = Counter(gpu_device_class(row[2], row[4]) for row in gpu_rows)
    gpu_outcomes = Counter()
    for _, _, name, score, vram in gpu_rows:
        estimate = estimate_gpu_fps("CS2", name, score, vram)
        gpu_outcomes["numeric_gpu_only_estimate" if estimate.get("fps") is not None
                     else estimate.get("reason", "unknown_reason")] += 1
    by_name = {(kind, name.casefold()): (int(row_id), name, score, vram)
               for row_id, kind, name, score, vram in rows}
    cpu = by_name.get(("CPU", "amd ryzen 5 5600"))
    gpu = by_name.get(("GPU", "geforce rtx 3060"))
    if not cpu or not gpu:
        read_connection.close()
        raise SystemExit("Real API check needs catalog entries AMD Ryzen 5 5600 and GeForce RTX 3060.")

    engine = create_engine("sqlite://", creator=lambda: read_connection, poolclass=StaticPool)

    def readonly_session():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.dependency_overrides[get_db] = readonly_session
    app.include_router(games_router)
    app.include_router(calculate_router)
    games = [item for item in catalog() if item.get("external_gpu_estimate_available")][:args.games]
    if len(games) < args.games:
        engine.dispose()
        raise SystemExit(f"Requested {args.games} games but only found {len(games)} with external GPU estimates.")

    statuses = Counter()
    cpu_adequacy_available = 0
    error_responses = []
    examples = []
    measured_pair_example = None
    measured_4k_pair_example = None
    upgrader_examples = {}
    started = time.perf_counter()
    try:
        with TestClient(app) as client:
            for game in games:
                response = client.post("/api/fps/predict", json={
                    "cpu_id": cpu[0], "gpu_id": gpu[0], "game": game["name"],
                    "resolution": "1080p", "preset": "high",
                })
                if response.status_code != 200:
                    error_responses.append({"game": game["name"], "status": response.status_code,
                                            "detail": response.text[:240]})
                    continue
                result = response.json()["candidate_v4"]
                statuses[result.get("status", "missing_status")] += 1
                if result.get("cpu_adequacy", {}).get("available"):
                    cpu_adequacy_available += 1
                if result.get("gpu_oriented_fps") is not None and len(examples) < 3:
                    examples.append({"game": game["name"], "status": result["status"],
                                     "gpu_oriented_fps": result["gpu_oriented_fps"],
                                     "average_fps": result.get("average_fps"),
                                     "settings": result.get("settings"),
                                     "source": (result.get("source_evidence") or [{}])[0].get("url")})
            exact_cpu = by_name.get(("CPU", "amd ryzen 9 9950x3d"))
            exact_gpu = by_name.get(("GPU", "geforce rtx 5080"))
            if exact_cpu and exact_gpu:
                measured = client.post("/api/fps/predict", json={
                    "cpu_id": exact_cpu[0], "gpu_id": exact_gpu[0], "game": "Cyberpunk 2077",
                    "resolution": "1440p", "preset": "high",
                })
                if measured.status_code == 200:
                    data = measured.json()["candidate_v4"]
                    measured_pair_example = {key: data.get(key) for key in
                        ("status", "average_fps", "one_percent_low", "measurement_type", "confidence_level",
                         "sample_count", "independent_series", "settings", "source_evidence")}
                else:
                    error_responses.append({"case": "Cyberpunk measured pair", "status": measured.status_code,
                                            "detail": measured.text[:240]})
                measured_4k = client.post("/api/fps/predict", json={
                    "cpu_id": exact_cpu[0], "gpu_id": exact_gpu[0], "game": "Cyberpunk 2077",
                    "resolution": "4K", "preset": "high",
                })
                if measured_4k.status_code == 200:
                    data = measured_4k.json()["candidate_v4"]
                    measured_4k_pair_example = {key: data.get(key) for key in
                        ("status", "average_fps", "one_percent_low", "measurement_type", "confidence_level",
                         "sample_count", "independent_series", "settings", "source_evidence")}
                else:
                    error_responses.append({"case": "Cyberpunk measured 4K pair", "status": measured_4k.status_code,
                                            "detail": measured_4k.text[:240]})

            # Exercise the existing Upgrader route with price refresh disabled.
            # Its internal catalogue synchronization is a write path, so skip
            # only that sync here while keeping the calculation and all reads
            # against the query_only local database.
            upgrade_gpus = (gpu, by_name.get(("GPU", "geforce rtx 4060")))
            upgrade_cpus = (cpu, by_name.get(("CPU", "amd ryzen 7 7800x3d")))
            for label, replacement in (("gpu", upgrade_gpus[1]), ("cpu", upgrade_cpus[1])):
                if not replacement:
                    upgrader_examples[label] = {"status": "skipped", "reason": "replacement is not in local catalog"}
                    continue
                with patch("app.services.internal_offers.sync_internal", return_value=False):
                    upgrade = client.post("/api/calculate", json={
                        "cpu_id": cpu[0], "gpu_id": gpu[0], "game": "God of War",
                        "mode": "1080p_high", "budget": 30000,
                        "selected_upgrade_id": replacement[0], "refresh_avito_prices": False,
                    })
                if upgrade.status_code == 200:
                    body = upgrade.json()
                    v4 = body.get("fps_v4_evidence") or {}
                    upgrader_examples[label] = {"status": "ok", "current_fps": body.get("current_fps"),
                        "upgraded_fps": body.get("upgraded_fps"),
                        "v4_current_status": (v4.get("current") or {}).get("status"),
                        "v4_after_status": (v4.get("after") or {}).get("status"),
                        "v4_gain_fps": v4.get("gain_fps"),
                        "v4_gpu_oriented_gain_fps": v4.get("gpu_oriented_gain_fps"),
                        "cpu_adequacy_change": v4.get("cpu_adequacy_change"),
                        "replacement": replacement[1], "price_refresh_requested": False}
                else:
                    upgrader_examples[label] = {"status": "error", "http_status": upgrade.status_code,
                                                 "detail": upgrade.text[:240]}
                    error_responses.append({"case": f"Upgrader {label}", **upgrader_examples[label]})
            # Exercise the actual Builder API response/evidence integration with
            # real selected Hardware rows. Stub only the expensive/side-effecting
            # assembly and sync portions; the v4 resolver reads the readonly DB.
            from app.services.builds import BuildRequest
            builder_plan = {"parts": [
                {"type": "CPU", "id": cpu[0], "name": cpu[1]},
                {"type": "GPU", "id": gpu[0], "name": gpu[1]},
            ], "alternatives": []}
            builder_payload = {
                "scenario": "build", "budget": 100000, "target_fps": 60,
                "game": "Portal 2", "mode": "1080p_high", "socket": "AM4",
                "ram_type": "DDR4", "ram_capacity_gb": 16,
                "selected_cpu_id": cpu[0], "selected_gpu_id": gpu[0],
            }
            with (patch("app.services.internal_offers.sync_internal", return_value=False),
                  patch("app.services.builds._assemble", return_value=builder_plan),
                  patch("app.services.offer_geography.financial_evidence", side_effect=lambda result, *_: result)):
                builder_response = client.post("/api/assemble", json=builder_payload)
            if builder_response.status_code == 200:
                builder_body = builder_response.json()
                builder_example = {"status": "ok", "http_status": 200,
                    "fps_v4_status": (builder_body.get("fps_v4_evidence") or {}).get("status"),
                    "average_fps": (builder_body.get("fps_v4_evidence") or {}).get("average_fps"),
                    "gpu_oriented_fps": (builder_body.get("fps_v4_evidence") or {}).get("gpu_oriented_fps"),
                    "selected_cpu": cpu[1], "selected_gpu": gpu[1],
                    "assembly_selection_stubbed": True}
            else:
                builder_example = {"status": "error", "http_status": builder_response.status_code,
                                   "detail": builder_response.text[:240]}
                error_responses.append({"case": "Builder", **builder_example})

            coverage = client.get("/api/games/coverage")
            coverage_status = coverage.status_code
            coverage_body = coverage.json() if coverage.status_code < 400 else None
    finally:
        engine.dispose()

    print(json.dumps({
        "sqlite_path": str(path),
        "sqlite_open_mode": "mode=ro; PRAGMA query_only=ON",
        "selected_hardware": {"cpu": cpu[1], "cpu_id": cpu[0], "gpu": gpu[1], "gpu_id": gpu[0]},
        "api_requests": args.games,
        "successful_fps_requests": args.games - len(error_responses),
        "error_responses": error_responses,
        "v4_status_counts": dict(statuses),
        "cpu_adequacy_available_in_sample": cpu_adequacy_available,
        "measured_pair_api_example": measured_pair_example,
        "measured_4k_pair_api_example": measured_4k_pair_example,
        "cs2_gpu_catalog_coverage": {"gpu_rows": len(gpu_rows), "device_classes": dict(gpu_classes),
                                     "numeric_gpu_only_estimates": gpu_outcomes["numeric_gpu_only_estimate"],
                                     "abstention_reasons": {key: value for key, value in sorted(gpu_outcomes.items())
                                                            if key != "numeric_gpu_only_estimate"}},
        "builder_api_example": builder_example,
        "upgrader_api_examples": upgrader_examples,
        "coverage_endpoint_status": coverage_status,
        "coverage": ({
            "games": coverage_body.get("total_games"),
            "external_gpu_games": coverage_body.get("external_fps_coverage", {}).get("games_with_external_model_estimate"),
            "external_gpu_estimate_records": coverage_body.get("external_fps_coverage", {}).get("external_estimate_records"),
            "cpu_requirement_resolution": coverage_body.get("cpu_requirement_resolution"),
        } if coverage_body else None),
        "examples": examples,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }, ensure_ascii=False, indent=2))
    if error_responses or coverage_status != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

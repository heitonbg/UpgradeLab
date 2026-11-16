"""Idempotent storage for the checked-in, license-reviewed benchmark dataset."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import BenchmarkMeasurement, BenchmarkSource
from app.services.benchmark_data import Observation, deduplicate
from app.services.offers import signature

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "measurements.json"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _import_curated_benchmarks_once(db: Session, path: str | Path | None = None) -> dict:
    """Add validated measurements without modifying accounts or old observations.

    Existing IDs with changed contents are rejected. Corrections must arrive as
    new source records so old provenance remains auditable.
    """
    source_path = Path(path) if path else DATA_PATH
    document = json.loads(source_path.read_text(encoding="utf-8"))
    rows, duplicates = deduplicate(document.get("rows", []))
    manifests: dict[str, list[dict]] = {}
    for entry in document.get("sources", []):
        manifests.setdefault(entry["publisher"], []).append(entry)
    inserted_sources = inserted = unchanged = 0
    seen_sources: set[str] = set()
    seen_measurements: dict[str, str] = {}

    for row in rows:
        row = Observation.model_validate(row).model_dump()
        source_manifest = sorted(manifests.get(row["publisher"], []), key=lambda item: item["file"])
        provenance = {
            "publisher": row["publisher"], "source_url": row["source_url"],
            "license": row["license"], "attribution": row["attribution"],
            "snapshot_manifest": source_manifest,
        }
        source_fingerprint = _sha256(_json(provenance))
        if source_fingerprint not in seen_sources:
            source = db.get(BenchmarkSource, source_fingerprint)
            if source is None:
                db.add(BenchmarkSource(
                    fingerprint=source_fingerprint, publisher=row["publisher"],
                    source_url=row["source_url"], license=row["license"],
                    attribution=row["attribution"], snapshot_manifest=_json(source_manifest)))
                inserted_sources += 1
            seen_sources.add(source_fingerprint)

        payload = _json(row)
        fingerprint = _sha256(payload)
        if row["id"] in seen_measurements:
            if seen_measurements[row["id"]] != fingerprint:
                raise ValueError(f"Benchmark ID {row['id']} is duplicated with different values in the dataset")
            unchanged += 1
            continue
        seen_measurements[row["id"]] = fingerprint
        current = db.get(BenchmarkMeasurement, row["id"])
        if current:
            if current.fingerprint != fingerprint:
                raise ValueError(f"Benchmark ID {row['id']} already exists with different provenance or values")
            unchanged += 1
            continue
        db.add(BenchmarkMeasurement(
            id=row["id"], fingerprint=fingerprint, source_fingerprint=source_fingerprint,
            game=row["game"], cpu=row["cpu"], cpu_key=signature(row["cpu"] or "", "CPU"),
            gpu=row["gpu"], gpu_key=signature(row["gpu"] or "", "GPU"),
            resolution=row["resolution"], preset=row["preset"], data_type=row["data_type"],
            record_kind=row["record_kind"], average_fps=row["average_fps"],
            one_percent_low=row["one_percent_low"], series_id=row["series_id"], payload=payload))
        inserted += 1

    db.commit()
    return {"inserted": inserted, "unchanged": unchanged,
            "sources_inserted": inserted_sources, "duplicates_collapsed": len(duplicates),
            "total_records": db.scalar(select(func.count()).select_from(BenchmarkMeasurement)) or 0,
            "total_sources": db.scalar(select(func.count()).select_from(BenchmarkSource)) or 0,
            "dataset_schema_version": document.get("schema_version")}


def import_curated_benchmarks(db: Session, path: str | Path | None = None) -> dict:
    """Serialize concurrent idempotent imports through unique DB constraints."""
    for attempt in range(3):
        try:
            return _import_curated_benchmarks_once(db, path)
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                raise
        except Exception:
            db.rollback()
            raise

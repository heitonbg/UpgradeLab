"""Container entrypoint: optional local Regard bootstrap, then one Uvicorn worker."""
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import tempfile
import shutil
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, BadZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base, engine
from app.db.models import CatalogAccess, CatalogImport, CatalogSyncRun, Hardware
from app.schemas.catalog import CatalogRights
from app.services.catalog_access import validated_rights
from app.services.catalog_files import CatalogError
from app.services.catalog_import import digest, hardware_snapshot, load_schema, read_local, source_snapshot
from app.services.regard_feed import RegardFeedAdapter
from app.services.regard_sync import synchronize

LOG = logging.getLogger("regard_bootstrap")
FILES = ("price.xlsx", "regard-schema.json", "regard-rights.json")


def preflight(directory: Path):
    paths = [directory / name for name in FILES]
    for path in paths:
        if not path.is_file():
            raise CatalogError("missing_" + path.name.replace(".", "_"))
    source = read_local(paths[0], 8 * 1024 * 1024)
    schema = load_schema(paths[1])
    if schema.source != "regard" or schema.input_adapter != "regard-native-v1" or schema.fixture:
        raise CatalogError("native_regard_schema_required")
    try:
        rights = CatalogRights.model_validate_json(read_local(paths[2], 65536))
    except ValueError:
        raise CatalogError("invalid_rights_record") from None
    if rights.source != "regard" or not rights.development or not rights.public_display:
        raise CatalogError("public_permission_required")
    from app.core.price_time import as_utc, utc_now
    confirmed = as_utc(rights.confirmed_at)
    if not confirmed or confirmed > utc_now():
        raise CatalogError("invalid_rights_confirmation")
    try:
        with ZipFile(paths[0]) as archive:
            if archive.testzip() is not None:
                raise CatalogError("corrupt_xlsx")
    except (BadZipFile, OSError):
        raise CatalogError("corrupt_xlsx") from None
    native = RegardFeedAdapter(schema.source_utc_offset_minutes).read(source)
    if len(native.rows) < 1000:
        raise CatalogError("suspicious_small_feed")
    signature = digest([digest(source), digest(paths[1].read_bytes()), digest(paths[2].read_bytes())])
    return paths, rights.model_dump(), signature, digest(source), native.metadata


def backup(database: Path, file_sha: str):
    if not database.is_file():
        return None
    target_dir = database.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"regard-before-{stamp}-{file_sha[:12]}-{uuid4().hex[:8]}.db"
    if target.exists():
        raise CatalogError("backup_path_exists")
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(target)) as copy:
                source.backup(copy)
                if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise CatalogError("backup_integrity_failure")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def already_applied(signature: str, file_sha: str, schema_path: Path, supplied_rights: dict):
    with Session(engine) as db:
        row = db.scalar(select(CatalogSyncRun).where(
            CatalogSyncRun.source == "regard",
            CatalogSyncRun.status.in_(("succeeded", "unchanged"))
        ).order_by(CatalogSyncRun.finished_at.desc()).limit(1))
        if not row:
            return False
        try:
            report = json.loads(row.report)
            access = db.get(CatalogAccess, "regard")
            rights = validated_rights(access) if access else None
            return bool(report.get("bootstrap_inputs") == signature
                        and report.get("catalog_state") == digest(source_snapshot(db, "regard"))
                        and report.get("input_signature") == digest([file_sha, load_schema(schema_path).model_dump(), supplied_rights, "public-noncommercial", False, 1000, digest(hardware_snapshot(db))])
                        and db.get(CatalogImport, report.get("receipt", {}).get("import_key", "")) is not None
                        and access.public_enabled and not access.fixture
                        and rights and rights.public_display
                        and db.scalar(select(Hardware.id).limit(1)) is not None)
        except (ValueError, TypeError, KeyError):
            return False


def _bootstrap(directory: Path | None = None):
    directory = directory or Path(engine.url.database).parent
    paths, rights, signature, file_sha, metadata = preflight(directory)
    database = Path(engine.url.database)
    if engine.url.get_backend_name() != "sqlite" or not database.is_absolute():
        raise CatalogError("absolute_file_sqlite_required")
    # The background importer starts after Uvicorn is ready. Existing data is
    # backed up before create_all, seed or any import journal write.
    if database.is_file():
        from sqlalchemy import inspect
        if inspect(engine).has_table("catalog_sync_runs") and already_applied(signature, file_sha, paths[1], rights):
            LOG.info("regard_bootstrap status=unchanged sha256=%s", file_sha)
            return {"status": "unchanged", "sha256": file_sha}
    saved = backup(database, file_sha)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        needs_seed = db.scalar(select(Hardware.id).limit(1)) is None
    if needs_seed:
        from scripts.init_db import seed
        seed()
    result = synchronize(engine, paths[1], rights, file=paths[0],
                         audience="public-noncommercial", require_public_candidates=True)
    if result["receipt"].get("published", 0) <= 0:
        raise CatalogError("no_public_products")
    with Session(engine) as db:
        row = db.get(CatalogSyncRun, result["sync_id"])
        report = json.loads(row.report)
        report["bootstrap_inputs"] = signature
        row.report = json.dumps(report, ensure_ascii=False, default=str)
        db.commit()
    LOG.info("regard_bootstrap status=%s sha256=%s published=%s backup=%s source_date=%s",
             "unchanged" if result["receipt"].get("idempotent") else "succeeded",
             file_sha, result["receipt"]["published"],
             saved.name if saved else "new_database",
             metadata.get("source_updated_at", "from_xlsx"))
    return result


@contextmanager
def bootstrap_lock(database: Path):
    lock = open(str(database) + ".bootstrap.lock", "a+b")
    try:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            if Path(lock.name).stat().st_size == 0:
                lock.write(b"0")
                lock.flush()
                lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise CatalogError("bootstrap_already_running") from None
        else:
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise CatalogError("bootstrap_already_running") from None
        yield
    finally:
        lock.close()


def bootstrap(directory: Path | None = None):
    database = Path(engine.url.database)
    if engine.url.get_backend_name() != "sqlite" or not database.is_absolute():
        raise CatalogError("absolute_file_sqlite_required")
    database.parent.mkdir(parents=True, exist_ok=True)
    with bootstrap_lock(database):
        return _bootstrap(directory)


def network_refresh():
    """Download into a spool; publish the XLSX only after a successful import."""
    from app.services.regard_sync import download

    directory = Path(engine.url.database).parent
    with tempfile.TemporaryDirectory(prefix="regard-network-", dir=directory) as temporary:
        spool = Path(temporary)
        for name in FILES[1:]:
            shutil.copy2(directory / name, spool / name)
        rights = CatalogRights.model_validate_json(read_local(spool / FILES[2], 65536))
        downloaded = download(engine, spool, supplied_rights=rights.model_dump())
        result = bootstrap(spool)
        os.replace(downloaded, directory / FILES[0])
        LOG.info("regard_network status=succeeded sha256=%s", digest((directory / FILES[0]).read_bytes()))
        return result

def _daily_sync_loop():
    """Single scheduler across workers; imports remain protected and idempotent."""
    if not settings.regard_daily_sync_enabled:
        return
    interval = settings.regard_daily_sync_interval_seconds
    database = Path(engine.url.database)
    lock = open(str(database) + ".regard-scheduler.lock", "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if Path(lock.name).stat().st_size == 0:
                lock.write(b"0"); lock.flush(); lock.seek(0)
            try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                LOG.info("regard_scheduler status=skipped code=another_worker"); return
        else:
            import fcntl
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                LOG.info("regard_scheduler status=skipped code=another_worker"); return
        LOG.info("regard_scheduler status=started interval_seconds=%s", interval)
        delay = interval
        while True:
            time.sleep(delay)
            try:
                result = network_refresh()
                LOG.info("regard_scheduler status=%s", result.get("status", "completed"))
                delay = interval
            except Exception as exc:
                code = str(exc) if isinstance(exc, CatalogError) else type(exc).__name__
                LOG.error("regard_scheduler status=failed code=%s", code)
                delay = min(3600, interval)
    finally:
        lock.close()


def run_import():
    """Run after the HTTP application starts; failed imports never hide health."""
    enabled = os.getenv("REGARD_BOOTSTRAP_ON_START", "false").strip().lower() in ("1", "true", "yes")
    if enabled:
        local_ok = False
        try:
            bootstrap()
            local_ok = True
        except Exception as exc:
            code = str(exc) if isinstance(exc, CatalogError) else type(exc).__name__
            if code == "bootstrap_already_running":
                LOG.warning("regard_bootstrap status=skipped code=bootstrap_already_running")
                return
            LOG.error("regard_bootstrap status=failed code=%s; check /api/catalog/readiness", code)
        if settings.regard_download_enabled:
            try:
                network_refresh()
            except Exception as exc:
                code = str(exc) if isinstance(exc, CatalogError) else type(exc).__name__
                LOG.error("regard_network status=failed code=%s; existing catalog preserved", code)
    elif os.getenv("AMVERA") == "1":
        directory = Path(engine.url.database).parent
        present = [name for name in FILES if (directory / name).is_file()]
        LOG.warning("regard_bootstrap status=skipped code=disabled data_files=%s; set REGARD_BOOTSTRAP_ON_START=true after uploading all three files", ",".join(present) or "none")

    if os.getenv("AMVERA") == "1" and settings.regard_daily_sync_enabled:
        threading.Thread(target=_daily_sync_loop, name="regard-daily-sync", daemon=True).start()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    LOG.info("regard_bootstrap status=deferred; starting HTTP before catalog import")
    if os.getenv("AMVERA") == "1":
        database = Path(engine.url.database or "")
        if engine.url.get_backend_name() != "sqlite" or not database.is_absolute() or Path('/data') not in database.parents:
            raise RuntimeError('Amvera requires an absolute SQLite DATABASE_URL under /data')
    os.execvp("uvicorn", ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "1", "--timeout-graceful-shutdown", "30"])


if __name__ == "__main__":
    main()

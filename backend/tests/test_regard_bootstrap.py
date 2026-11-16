"""Offline startup and backup regression checks; no working SQLite or network."""
import json
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from app.services.catalog_files import CatalogError
from scripts.startup import backup, bootstrap_lock, main, network_refresh, preflight, run_import
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_regard_feed import BASE, xlsx
from scripts.regard_feed import schema


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "regard-schema.json").write_text(json.dumps(schema()), encoding="utf-8")
        self.rights = {
            "source": "regard", "development": True, "public_display": True,
            "commercial": False, "automatic_download": False,
            "basis": "Explicit owner permission for synthetic local tests",
            "owner_confirmed_by": "test owner",
            "confirmed_at": "2026-11-09T15:00:00Z",
        }
        (self.root / "regard-rights.json").write_text(json.dumps(self.rights), encoding="utf-8")

    def test_missing_file_does_not_create_database(self):
        with self.assertRaisesRegex(CatalogError, "missing_price_xlsx"):
            preflight(self.root)
        self.assertFalse((self.root / "pc_upgrade.db").exists())

    def test_corrupt_xlsx_is_rejected(self):
        (self.root / "price.xlsx").write_bytes(b"not an xlsx")
        with self.assertRaisesRegex(CatalogError, "corrupt_xlsx"):
            preflight(self.root)

    def test_public_permission_is_required(self):
        (self.root / "price.xlsx").write_bytes(xlsx(BASE))
        self.rights["public_display"] = False
        (self.root / "regard-rights.json").write_text(json.dumps(self.rights), encoding="utf-8")
        with self.assertRaisesRegex(CatalogError, "public_permission_required"):
            preflight(self.root)

    def test_backup_restores_existing_data(self):
        database = self.root / "pc_upgrade.db"
        with closing(sqlite3.connect(database)) as db:
            db.execute("create table saved_builds_test (id integer primary key, value text)")
            db.execute("insert into saved_builds_test values (1, 'kept')")
            db.commit()
        saved = backup(database, "abcdef")
        self.assertIsNotNone(saved)
        with closing(sqlite3.connect(database)) as db:
            db.execute("update saved_builds_test set value='changed'")
        with closing(sqlite3.connect(saved)) as restored:
            self.assertEqual(restored.execute("pragma integrity_check").fetchone()[0], "ok")
            self.assertEqual(restored.execute("select value from saved_builds_test").fetchone()[0], "kept")

    def test_second_bootstrap_is_locked(self):
        database = self.root / "pc_upgrade.db"
        with bootstrap_lock(database):
            with self.assertRaisesRegex(CatalogError, "bootstrap_already_running"):
                with bootstrap_lock(database):
                    pass

    def test_failed_import_does_not_stop_http_entrypoint(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START": "true"}):
            with patch("scripts.startup.bootstrap", side_effect=CatalogError("corrupt_xlsx")):
                with patch("scripts.startup.os.execvp") as execvp:
                    main()
                    run_import()
        execvp.assert_called_once()

    def test_concurrent_bootstrap_is_skipped_without_stopping_http(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START": "true"}):
            with patch("scripts.startup.bootstrap", side_effect=CatalogError("bootstrap_already_running")):
                with patch("scripts.startup.os.execvp") as execvp:
                    main()
                    run_import()
        execvp.assert_called_once()
    def test_disabled_bootstrap_starts_server_without_import(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START": "false"}):
            with patch("scripts.startup.bootstrap") as run, patch("scripts.startup.os.execvp") as execvp:
                main()
                run_import()
        run.assert_not_called()
        self.assertEqual(execvp.call_args.args[0], "uvicorn")

    def test_amvera_disabled_bootstrap_explains_empty_catalog(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START": "false", "AMVERA": "1"}):
            with patch("scripts.startup.bootstrap") as run:
                with self.assertLogs("regard_bootstrap", level="WARNING") as logs:
                    run_import()
        run.assert_not_called()
        self.assertIn("status=skipped code=disabled", logs.output[0])

    def test_network_refresh_replaces_price_only_after_import(self):
        price = self.root / "price.xlsx"
        price.write_bytes(b"previous")
        fake_engine = SimpleNamespace(url=SimpleNamespace(database=str(self.root / "pc_upgrade.db")))

        def fetch(_engine, directory, **kwargs):
            path = Path(directory) / "price.xlsx"
            path.write_bytes(b"new official bytes")
            return path

        with patch("scripts.startup.engine", fake_engine), patch("app.services.regard_sync.download", side_effect=fetch):
            with patch("scripts.startup.bootstrap", side_effect=CatalogError("import_failed")):
                with self.assertRaisesRegex(CatalogError, "import_failed"):
                    network_refresh()
            self.assertEqual(price.read_bytes(), b"previous")
            with patch("scripts.startup.bootstrap", return_value={"status": "succeeded"}):
                network_refresh()
        self.assertEqual(price.read_bytes(), b"new official bytes")

    def test_enabled_download_runs_after_local_bootstrap(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START": "true"}):
            with patch("scripts.startup.settings.regard_download_enabled", True):
                with patch("scripts.startup.bootstrap") as local, patch("scripts.startup.network_refresh") as network:
                    run_import()
        local.assert_called_once()
        network.assert_called_once()


if __name__ == "__main__":
    unittest.main()

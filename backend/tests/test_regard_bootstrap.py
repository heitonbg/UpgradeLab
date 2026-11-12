"""Offline startup and backup regression checks; no working SQLite or network."""
import json
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.catalog_files import CatalogError
from scripts.startup import backup, bootstrap_lock, main, preflight
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

    def test_invalid_bootstrap_still_starts_http_for_separate_readiness(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START": "true"}):
            with patch("scripts.startup.bootstrap", side_effect=CatalogError("corrupt_xlsx")):
                with patch("scripts.startup.os.execvp") as execvp:
                    main()
        execvp.assert_called_once()

    def test_concurrent_bootstrap_does_not_start_second_http(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START": "true"}):
            with patch("scripts.startup.bootstrap", side_effect=CatalogError("bootstrap_already_running")):
                with patch("scripts.startup.os.execvp") as execvp:
                    with self.assertRaises(SystemExit):
                        main()
        execvp.assert_not_called()
    def test_disabled_bootstrap_starts_server_without_import(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START": "false"}):
            with patch("scripts.startup.bootstrap") as run, patch("scripts.startup.os.execvp") as execvp:
                main()
        run.assert_not_called()
        self.assertEqual(execvp.call_args.args[0], "uvicorn")


if __name__ == "__main__":
    unittest.main()

"""Additive migration backup preserves pre-existing rows."""
import unittest,tempfile,sqlite3,sys
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.migrate_catalog_intelligence import migrate
class MigrationTests(unittest.TestCase):
 def test_backup_and_additive_schema_keep_legacy_rows(self):
  with tempfile.TemporaryDirectory() as directory:
   source=Path(directory)/'legacy.db';backup=Path(directory)/'backup.db'
   with closing(sqlite3.connect(source)) as db,db:db.execute('CREATE TABLE preserved (id INTEGER PRIMARY KEY, value TEXT)');db.execute("INSERT INTO preserved VALUES (1,'original')")
   result=migrate(source,backup);self.assertIn('catalog_daily_prices',result['added_tables'])
   for path in (source,backup):
    with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('SELECT value FROM preserved').fetchone()[0],'original')
   with self.assertRaises(ValueError):migrate(source,backup)
if __name__=='__main__':unittest.main()

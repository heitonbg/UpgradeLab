"""Additive catalogue/discovery schema preparation with an online SQLite backup.
Never runs implicitly; stop application writers before applying a migration.
"""
import argparse,sqlite3,json
from contextlib import closing
from pathlib import Path
from sqlalchemy import create_engine,inspect
from app.db.models import Base

def migrate(database,backup):
 source=Path(database).resolve();target=Path(backup).resolve()
 if not source.is_file():raise ValueError('existing SQLite database required')
 if source==target or target.exists():raise ValueError('backup must be a new separate path')
 target.parent.mkdir(parents=True,exist_ok=True)
 with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(target)) as copy:
  original.backup(copy)
  if copy.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('backup integrity failure')
 engine=create_engine('sqlite:///'+str(source));before=set(inspect(engine).get_table_names())
 Base.metadata.create_all(engine)
 after=set(inspect(engine).get_table_names());engine.dispose()
 return {'backup':str(target),'added_tables':sorted(after-before),'existing_rows_modified':False}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',required=True);p.add_argument('--backup',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
 if not a.apply:p.error('Explicit --apply required; application writers must be stopped')
 print(json.dumps(migrate(a.database,a.backup)))

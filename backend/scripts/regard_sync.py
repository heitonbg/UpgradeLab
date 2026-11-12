"""Privileged CLI. Explicit database; never schedules or downloads by default."""
import argparse,json
from pathlib import Path
from sqlalchemy import create_engine,select,inspect
from sqlalchemy.orm import Session
from app.db.models import Base,CatalogSyncRun
from app.services.regard_sync import synchronize
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',required=True);p.add_argument('--schema');p.add_argument('--rights');p.add_argument('--file');p.add_argument('--status',action='store_true');p.add_argument('--closed-analysis',action='store_true');p.add_argument('--audience',choices=['development','public-noncommercial','public-commercial'],default='development');a=p.parse_args()
    if a.status and not Path(a.database).is_file():p.error('existing database required for read-only status')
    engine=create_engine('sqlite:///'+str(Path(a.database).resolve()),connect_args={'timeout':10})
    if not a.status:Base.metadata.create_all(engine)
    if a.status and not inspect(engine).has_table('catalog_sync_runs'):
        print(json.dumps({'status':'migration_required'}))
    elif a.status:
        with Session(engine) as db:print(json.dumps([{'id':r.id,'status':r.status,'started_at':r.started_at.isoformat(),'report':json.loads(r.report)} for r in db.scalars(select(CatalogSyncRun).order_by(CatalogSyncRun.started_at.desc()).limit(10))],ensure_ascii=False))
    else:
        if not a.schema or not a.rights:p.error('--schema and --rights required')
        result=synchronize(engine,a.schema,json.loads(Path(a.rights).read_text(encoding='utf-8')),file=a.file,audience=a.audience,analysis=a.closed_analysis)
        print(json.dumps(result,ensure_ascii=False,default=str))

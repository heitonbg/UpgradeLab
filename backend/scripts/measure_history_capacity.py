"""Synthetic history capacity only: never imports fabricated store prices."""
import argparse,json,hashlib
from pathlib import Path
from datetime import date,timedelta
from sqlalchemy import create_engine,insert,select,func
from sqlalchemy.orm import Session
from app.db.models import CatalogDailyPrice
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--products',type=int,default=4991);p.add_argument('--output',required=True);a=p.parse_args();path=Path(a.output)
 if path.exists() or not 1<=a.products<=10000:p.error('new output file and 1..10000 products required')
 engine=create_engine('sqlite:///'+str(path.resolve()));CatalogDailyPrice.__table__.create(engine)
 with Session(engine) as db:
  for day in range(14):
   values=[dict(product_key=hashlib.sha256(f'fixture-{i}'.encode()).hexdigest(),source_day=(date(2026,11,10)-timedelta(days=day)).isoformat(),source='fixture',price_kopecks=100000,import_key='synthetic-capacity-only') for i in range(a.products)]
   db.execute(insert(CatalogDailyPrice),values)
  db.commit();count=db.scalar(select(func.count()).select_from(CatalogDailyPrice))
 engine.dispose();print(json.dumps({'synthetic':True,'actual_store_measurements':0,'products':a.products,'calendar_days':14,'rows':count,'sqlite_bytes':path.stat().st_size}))

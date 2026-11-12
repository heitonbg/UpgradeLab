"""Offline real-feed profile: explicit new output, no working DB access."""
import argparse,json
from pathlib import Path
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from app.db.models import Base,CatalogDailyPrice,CatalogProduct
from scripts.regard_feed import seed_hardware,schema
from app.services.regard_sync import synchronize
from app.core.price_time import iso_utc,utc_now

def run(file,output):
 root=Path(output);root.mkdir(parents=True,exist_ok=False)
 engine=create_engine('sqlite:///'+str((root/'regard.analysis.db').resolve()));Base.metadata.create_all(engine)
 with Session(engine) as db:seed_hardware(db)
 mapping=root/'schema.json';mapping.write_text(json.dumps(schema()),encoding='utf-8')
 rights={'source':'regard','development':True,'public_display':False,'commercial':False,'automatic_download':False,'basis':'Owner supplied XLSX, offline private analysis only; no external publication or download rights','owner_confirmed_by':'UpgradeLab owner task','confirmed_at':iso_utc(utc_now())}
 first=synchronize(engine,mapping,rights,file=file,analysis=True)
 second=synchronize(engine,mapping,rights,file=file,analysis=True)
 with Session(engine) as db:counts={'products':db.scalar(select(func.count()).select_from(CatalogProduct)),'daily_prices':db.scalar(select(func.count()).select_from(CatalogDailyPrice))}
 result={'real_file':True,'network_requests':0,'first':first,'repeat':second,'counts':counts,'working_database_touched':False}
 (root/'profile.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 engine.dispose();print(json.dumps({'output':str(root),'counts':counts,'seconds':first['elapsed_seconds'],'peak_mib':first['peak_working_set_mib'],'sqlite_bytes':first['sqlite_bytes'],'repeat_idempotent':second['receipt']['idempotent']}))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--file',required=True);p.add_argument('--output',required=True);a=p.parse_args();run(a.file,a.output)

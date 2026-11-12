"""Synthetic local catalogue demonstration, never real shop offers."""
import argparse
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import Base
from app.core.price_time import utc_now,iso_utc
from app.core.config import settings
from app.services.catalog_import import prepare_import,apply_import,canonical
from app.services.catalog_access import fixture_catalog
from app.schemas.offers import SearchOffers
from app.services.offers import search_offers
from app.services.builds import BuildRequest,assemble
from scripts.catalog_fixture import rows,schema,rights,csv_bytes,xlsx_bytes,seed

def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    database=output/'demo.fixture.db'
    if database.exists():raise ValueError('Use a new output directory; existing databases are never erased')
    engine=create_engine('sqlite:///'+database.as_posix());Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:seed(db)
        timestamp=iso_utc(utc_now());values=rows(timestamp)
        values.extend([
            ['9','GeForce RTX 5060 Ti','GPU','30000','RUB','yes',timestamp,'https://www.regard.ru/product/990000009/fixture-not-a-real-offer'],
            ['10','GeForce RTX 5060 8GB','GPU','','RUB','yes',timestamp,'https://www.regard.ru/product/990000010/fixture-not-a-real-offer'],
            ['11','AMD Ryzen 5 5600','CPU','5000','RUB','yes',timestamp,'']])
        permission=rights();permission['confirmed_at']=timestamp
        (output/'fixture-rights.json').write_text(canonical(permission)+'\n',encoding='utf-8')
        results={}
        for fmt,content in [('csv',csv_bytes(values)),('xlsx',xlsx_bytes(values))]:
            file=output/('fixture.'+fmt);file.write_bytes(content)
            configuration=output/(fmt+'-fixture-schema.json');configuration.write_text(canonical(schema(fmt))+'\n',encoding='utf-8')
            plan=prepare_import(engine,file,configuration)
            (output/(fmt+'-preview.json')).write_text(canonical(plan)+'\n',encoding='utf-8')
            applied=apply_import(engine,file,configuration,plan,permission,fixture=True,allow_rejected=True)
            replay=apply_import(engine,file,configuration,plan,permission,fixture=True,allow_rejected=True)
            results[fmt]={'preview':plan['report'],'apply':applied,'replay_idempotent':replay['idempotent']}
        old_live,old_feeds=settings.offers_live_search,settings.offers_feed_urls
        try:
            settings.offers_live_search=False;settings.offers_feed_urls='{}'
            with Session(engine) as db,fixture_catalog():
                query=SearchOffers(query='RTX 5060',category='GPU',sources=['regard']);query._catalog_only=True
                found=search_offers(db,query)
                built=assemble(BuildRequest(scenario='build',auto_parts=True,budget=60000,target_fps=60,
                    game='Red Dead Redemption 2',mode='1440p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,
                    price_sources=['regard'],allow_store_fallback=False,allow_platform_change=False),db)
            results.update(search=found,build=built,fixture=True)
        finally:settings.offers_live_search=old_live;settings.offers_feed_urls=old_feeds
        (output/'demo-result.json').write_text(canonical(results)+'\n',encoding='utf-8');return results
    finally:engine.dispose()
if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    result=run(args.output)
    print(canonical({'fixture':True,'csv':result['csv']['preview'],'xlsx':result['xlsx']['preview'],
        'found':len(result['search']['offers']),'build_status':result['build']['status'],
        'parts':len(result['build']['parts']),'total_price':result['build'].get('total_price')}))

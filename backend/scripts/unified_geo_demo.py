"""Offline synthetic unified-source demo; refuses existing destinations."""
import argparse,json,sys
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from app.db.models import Base,User,Listing,ListingOwner,StoreOffer
from app.services.cities import BY_ID
from app.services.offers import search_offers
from app.schemas.offers import SearchOffers
from app.services.builds import BuildRequest,assemble
from app.services.catalog_import import prepare_import,apply_import
from app.services.catalog_access import fixture_catalog
from app.services.technical_evidence import storage_status,psu_status
from scripts.catalog_fixture import seed,schema,rows,rights,csv_bytes
from app.core.price_time import iso_utc,db_now,utc_now

def run(output):
 root=Path(output).resolve();root.mkdir(parents=True,exist_ok=True);dbfile=root/'unified.fixture.db'
 if dbfile.exists():raise ValueError('Refusing to overwrite existing demo database')
 now=utc_now();stamp=iso_utc(now)
 kem=next(k for k,v in BY_ID.items() if v['name']=='Кемерово');mos=next(k for k,v in BY_ID.items() if v['name']=='Москва')
 engine=create_engine('sqlite:///'+dbfile.as_posix());Base.metadata.create_all(engine)
 slot={'applies_to':'ASRock B450M-HDV R4.0 DDR4','slots':[{'kind':'M.2','interfaces':['NVMe'],'sizes':[2280],'available':1},{'kind':'SATA','interfaces':['SATA'],'sizes':[],'available':2}], 'basis':'Synthetic fixture specification, not a shop claim','source_url':'fixture://reviewed-board'}
 power={'applies_to':'MSI MAG A650BN 650W','atx24':True,'eps_4plus4':1,'pcie_6plus2':2,'basis':'Synthetic fixture connector specification','source_url':'fixture://reviewed-psu'}
 geo={'city_id':kem,'location_kind':'store_stock','availability':'in_stock','checked_at':stamp,'basis':'Synthetic store location fixture'}
 config=schema();config.update(geography=geo,technical={'storage_slots':slot,'power_connectors':power,'system_connector_requirements':{'pcie_6plus2':1,'gpu_model':'GeForce RTX 5060','gpu_vram':8,'basis':'Synthetic GPU fixture requirement'}})
 permissions=rights();permissions['confirmed_at']=stamp
 file=root/'fixture.csv';file.write_bytes(csv_bytes(rows(stamp)));mapping=root/'schema.json';mapping.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
 (root/'rights.json').write_text(json.dumps(permissions,ensure_ascii=False,indent=2),encoding='utf-8')
 with Session(engine) as db:seed(db)
 apply_import(engine,file,mapping,prepare_import(engine,file,mapping),permissions,fixture=True)
 with Session(engine) as db:
  db.add(User(id=1,email='synthetic@example.invalid',name='Synthetic seller',password_hash='not-a-real-account'))
  for index,(city,price) in enumerate(((kem,'18000'),(mos,'17000')),1):
   item=Listing(id=index,title='GeForce RTX 5060 8GB',category='GPU',hardware_id=2,condition='Б/У',price=price,contact='fixture',description='Synthetic local offer',listing_type='sale',publication_status='active',city_id=city,created_at=db_now(),updated_at=db_now(),availability_confirmed_at=db_now())
   db.add(item);db.flush();db.add(ListingOwner(listing_id=index,user_id=1))
  # A separate retail fixture participates beside the imported catalogue.
  db.add(StoreOffer(source='oldi',name='MSI MAG A650BN 650W',category='psu',price_rub=3000,url='https://www.oldi.ru/catalog/element/999999991/',condition='new',observed_at=db_now(),origin='public_page',attributes=json.dumps({'geography':geo,'power_connectors':power,'system_connector_requirements':{'pcie_6plus2':1,'gpu_model':'GeForce RTX 5060','gpu_vram':8,'basis':'Synthetic GPU fixture requirement'}})))
  db.commit()
  result={'fixture':True,'city_id':kem,'other_city_id':mos,'searches':{}}
  with patch('socket.socket',side_effect=AssertionError('Offline demo forbids sockets')),fixture_catalog():
   for mode in ('all','local','delivery'):
    result['searches'][mode]=search_offers(db,SearchOffers(query='RTX 5060',category='GPU',sources=['upgradelab','regard','oldi'],city_id=kem,geo_mode=mode))
   payload=BuildRequest(scenario='build',auto_parts=True,budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['upgradelab','regard','oldi'],city_id=kem,geo_mode='local',allow_store_fallback=False,allow_platform_change=False)
   result['build']=assemble(payload,db)
   board=db.scalar(select(StoreOffer).where(StoreOffer.category=='motherboard'));drive=db.scalar(select(StoreOffer).where(StoreOffer.category=='storage'));supply=db.scalar(select(StoreOffer).where(StoreOffer.source=='oldi'))
   result['storage_compatibility']=storage_status(board,drive);result['psu_compatibility']=psu_status(supply)
  result['closed_import_search']=search_offers(db,SearchOffers(query='RTX 5060',category='GPU',sources=['regard']))['offers']
  assert len(result['build']['parts'])==8 and result['build']['status']=='draft'
  assert result['build']['total_price']<=80000 and not result['closed_import_search']
  result['network_requests']=0
 (root/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8');engine.dispose();return result
if __name__=='__main__':
 if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();r=run(args.output)
 print(json.dumps({'fixture':True,'offers':{k:len(v['offers']) for k,v in r['searches'].items()},'parts':len(r['build']['parts']),'status':r['build']['status'],'total':r['build']['total_price'],'closed_import_visible':bool(r['closed_import_search']),'network_requests':0},ensure_ascii=False))

"""Offline iteration-11 marketplace walkthrough. All offers are synthetic fixtures."""
import argparse,json
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from scripts.unified_geo_demo import run as seed_demo
from app.api import listings as api
from app.db.models import User,Listing,StoreOffer
from app.schemas.listing import ListingCreate,ListingUpdate,ListingOut
from app.schemas.listing_details import SellerDelivery
from app.schemas.offers import SearchOffers
from app.services.cities import BY_ID
from app.services.catalog_access import fixture_catalog
from app.services.offers import search_offers
from app.services.builds import BuildRequest,assemble
from app.services.result_access import current_result

PRODUCTS={
 'CPU':('AMD Ryzen 5 5600','4500',1,{'socket':'AM4'}),
 'motherboard':('ASRock B450M-HDV R4.0 DDR4','8000',None,{'socket':'AM4','ram_type':'DDR4','form_factor':'mATX'}),
 'memory':('DDR4 2x8GB','4000',None,{'ram_type':'DDR4','capacity_gb':16,'modules':2,'module_type':'DIMM'}),
 'storage':('Samsung 870 EVO 500GB','2800',None,{'interface':'SATA','capacity_gb':500,'form_factor':'2.5'}),
 'psu':('MSI MAG A650BN 650W','3000',None,{'watts':650,'form_factor':'ATX'}),
 'case':('DeepCool CC560','3000',None,{'board_formats':['mATX'],'psu_formats':['ATX'],'max_gpu_length_mm':400,'max_cooler_height_mm':200}),
 'cooler':('DeepCool AG400','1200',None,{'sockets':['AM4'],'height_mm':150})}

def run(output):
 root=Path(output).resolve()
 seed_demo(root)
 engine=create_engine('sqlite:///'+(root/'unified.fixture.db').as_posix())
 kem=next(k for k,v in BY_ID.items() if v['name']=='Кемерово')
 nsk=next(k for k,v in BY_ID.items() if v['name']=='Новосибирск')
 result={'fixture':True,'network_requests':0,'city_id':kem,'target_city_id':nsk}
 try:
  with Session(engine) as db,patch('socket.socket',side_effect=AssertionError('No external network')),fixture_catalog():
   db.add_all([User(id=2,email='seller2@example.invalid',name='Synthetic seller 2',password_hash='not-a-real-account'),User(id=3,email='buyer@example.invalid',name='Synthetic buyer',password_hash='not-a-real-account')]);db.commit()
   seller=db.get(User,1);seller2=db.get(User,2)
   gpu=db.get(Listing,1)
   api.update_listing(gpu.id,ListingUpdate(characteristics={'vram':8,'length_mm':250},delivery=SellerDelivery(mode='cities',city_ids=[nsk],cost_rub=700),confirm_availability=True),db,seller)
   ids={'GPU':gpu.id}
   for category,(title,price,hardware,specs) in PRODUCTS.items():
    city=nsk if category=='cooler' else kem
    row=api.create_listing(ListingCreate(title=title,price=price,hardware_id=hardware,characteristics=specs,category=category,city_id=city,condition='Новое',contact='@fixture_seller',contact_type='telegram',delivery=SellerDelivery(mode='russia',cost_rub=300 if category=='cooler' else 0),confirm_availability=True),db,seller2 if category=='cooler' else seller)
    ids[category]=row.id
   def find(city,mode):return search_offers(db,SearchOffers(query='RTX 5060',category='GPU',sources=['upgradelab'],city_id=city,geo_mode=mode))
   result['searches']={'kemerovo_local':find(kem,'local'),'novosibirsk_local':find(nsk,'local'),'novosibirsk_delivery':find(nsk,'delivery'),'all':find(nsk,'all')}
   api.declare_delivery(gpu.id,SellerDelivery(mode='cities',city_ids=[nsk],cost_rub=None),db,seller)
   result['unknown_cost_search']=find(nsk,'delivery')
   api.declare_delivery(gpu.id,SellerDelivery(mode='cities',city_ids=[nsk],cost_rub=700),db,seller)
   p=BuildRequest(scenario='build',auto_parts=True,budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['upgradelab','regard'],city_id=kem,geo_mode='delivery',allow_store_fallback=False,allow_platform_change=False)
   result['build']=assemble(p,db)
   assert len(result['build']['parts'])==8 and result['build']['status']=='draft'
   assert result['build']['total_price']<=80000
   result['public_listings']=[ListingOut.model_validate(v).model_dump(mode='json') for v in api.get_listings(db) if v.id in ids.values()]
   result['result_valid_before_edit']=current_result(db,result['build'])
   api.update_listing(ids['CPU'],ListingUpdate(publication_status='sold'),db,seller)
   result['result_valid_after_sale']=current_result(db,result['build'])
   assert result['result_valid_before_edit'] and not result['result_valid_after_sale']
  with Session(engine) as db:
   result['closed_import_search']=search_offers(db,SearchOffers(query='RTX 5060',category='GPU',sources=['regard']))['offers']
   assert not result['closed_import_search']
  public=json.dumps(result['public_listings'])
  assert 'example.invalid' not in public and 'not-a-real-account' not in public
  (root/'marketplace-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
  return result
 finally:engine.dispose()
if __name__=='__main__':
 import sys
 sys.stdout.reconfigure(encoding='utf-8')
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();r=run(args.output)
 print(json.dumps({'fixture':True,'categories':len(r['public_listings']),'parts':len(r['build']['parts']),'status':r['build']['status'],'total':r['build']['total_price'],'sources':sorted(set(p['price_source'] for p in r['build']['parts'])),'search_counts':{k:len(v['offers']) for k,v in r['searches'].items()},'invalidated_after_sale':not r['result_valid_after_sale'],'network_requests':0},ensure_ascii=False))

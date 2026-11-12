"""Unified query regressions; every external socket is forbidden."""
import sys,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from sqlalchemy import create_engine,select,delete
from sqlalchemy.orm import Session
from app.db.models import Base,StoreOffer,Hardware,Listing,ListingOwner,User,ListingDelivery,SearchJob
from app.services.cities import BY_ID
from app.core import price_time
from app.schemas.offers import SearchOffers
from app.services.offers import search_offers,available_offers,search_key,collect_source
from app.services.offer_geography import offer_scope,geo_details
from app.services.technical_evidence import storage_status,psu_status
from app.services.builds import BuildRequest,assemble
from app.services.source_permissions import network_allowed
from app.services.result_access import current_result,listing_revision
from scripts.catalog_fixture import seed,rows,schema,rights,csv_bytes
from app.services.catalog_import import prepare_import,apply_import
from app.services.catalog_access import fixture_catalog
NOW=datetime(2026,11,9,12,5,tzinfo=timezone.utc)
KEM=next(k for k,v in BY_ID.items() if v['name']=='Кемерово')
MOS=next(k for k,v in BY_ID.items() if v['name']=='Москва')

def geography(city=KEM):return {'city_id':city,'location_kind':'store_stock','availability':'in_stock','checked_at':NOW.isoformat(),'basis':'Synthetic reviewed stock fixture'}
def technical():return {'storage_slots':{'applies_to':'ASRock B450M-HDV R4.0 DDR4','slots':[{'kind':'SATA','interfaces':['SATA'],'sizes':[],'available':2},{'kind':'M.2','interfaces':['NVMe'],'sizes':[2280],'available':1}], 'basis':'Synthetic reviewed board fixture','source_url':'fixture://reviewed-board'},
    'power_connectors':{'applies_to':'MSI MAG A650BN 650W','atx24':True,'eps_4plus4':1,'pcie_6plus2':2,'basis':'Synthetic connector fixture','source_url':'fixture://reviewed-psu'},'system_connector_requirements':{'pcie_6plus2':1,'gpu_model':'GeForce RTX 5060','gpu_vram':8,'basis':'Synthetic GPU requirements'}}

class UnifiedGeoTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.engine=create_engine('sqlite:///'+(self.root/'test.fixture.db').as_posix());Base.metadata.create_all(self.engine)
  self.addCleanup(self.engine.dispose);self.db=Session(self.engine);self.addCleanup(self.db.close)
  seed(self.db);self.db.add(User(id=1,email='fixture@example.invalid',name='Fixture seller',password_hash='not-a-password'));self.db.commit()
  self.addCleanup(patch.stopall)
  patch('app.core.price_time.utc_now',return_value=NOW).start()
  self.socket=patch('socket.socket',side_effect=AssertionError('No external sockets')).start()
  patch('app.core.config.settings.source_permissions','{}').start()
 def listing(self,city=KEM,price='18000',title='GeForce RTX 5060 8GB',hardware_id=2,**changes):
  item=Listing(title=title,price=price,city_id=city,category='GPU',hardware_id=hardware_id,condition='Б/У',contact='fixture contact',description='',listing_type='sale',publication_status='active',created_at=NOW.replace(tzinfo=None),updated_at=NOW.replace(tzinfo=None),availability_confirmed_at=NOW.replace(tzinfo=None))
  for k,v in changes.items():setattr(item,k,v)
  self.db.add(item);self.db.flush();self.db.add(ListingOwner(listing_id=item.id,user_id=1));self.db.commit();return item
 def find(self,**kw):return search_offers(self.db,SearchOffers(query='RTX 5060',category='GPU',sources=['upgradelab'],**kw))
 def test_local_and_other_city(self):
  self.listing();self.listing(MOS)
  self.assertEqual(len(self.find(city_id=KEM,geo_mode='local')['offers']),1)
  self.assertEqual(len(self.find()['offers']),2)
 def test_unknown_city_is_all_only(self):
  self.listing(None)
  self.assertEqual(self.find()['offers'][0]['geography']['location_status'],'location_unknown')
  self.assertEqual(self.find(city_id=KEM,geo_mode='local')['offers'],[])
 def test_sold_withdrawn_broken_and_expired_excluded(self):
  for status in ('sold','withdrawn'):self.listing(publication_status=status)
  self.listing(condition='Неисправное');self.listing(availability_confirmed_at=NOW.replace(tzinfo=None)-timedelta(days=2))
  self.assertEqual(self.find()['offers'],[])
 def test_deleted_listing_disappears_and_cached_id_cannot_reveal_it(self):
  item=self.listing();r=self.find()['offers'][0];self.db.execute(delete(ListingOwner).where(ListingOwner.listing_id==item.id));self.db.delete(item);self.db.commit()
  self.assertEqual(self.find()['offers'],[]);self.assertFalse(current_result(self.db,{'offer_id':r['id']}))
 def test_price_city_and_model_changes_are_live_even_with_search_cache(self):
  item=self.listing();initial=self.find(city_id=KEM,geo_mode='local');revision=listing_revision(self.db)
  item.price='19000';self.db.commit();self.assertEqual(self.find(city_id=KEM,geo_mode='local')['offers'][0]['price_rub'],19000)
  self.assertNotEqual(revision,listing_revision(self.db));item.city_id=MOS;self.db.commit()
  self.assertEqual(self.find(city_id=KEM,geo_mode='local')['offers'],[])
  item.title='GeForce RTX 5060 Ti 16GB';self.db.commit();self.assertEqual(self.find()['offers'],[])
 def test_ambiguous_and_wrong_vram_cannot_borrow_hardware(self):
  self.listing(title='GeForce RTX 5060 Ti',hardware_id=3)
  self.listing(title='GeForce RTX 5060 Ti 16GB',hardware_id=3)
  self.listing(title='GeForce RTX 5060 8GB / RTX 5060 Ti',hardware_id=2)
  self.assertEqual(self.find()['offers'],[])
 def test_vram_variants_are_separate(self):
  self.listing(title='GeForce RTX 5060 Ti 8GB',hardware_id=3);self.listing(title='GeForce RTX 5060 Ti 16GB',hardware_id=4)
  r=search_offers(self.db,SearchOffers(query='RTX 5060 Ti 16GB',category='GPU',sources=['upgradelab']))
  self.assertEqual(len(r['offers']),1);self.assertEqual(r['offers'][0]['hardware_id'],4)
 def test_ownership_required(self):
  item=self.listing();self.db.execute(delete(ListingOwner));self.db.commit();self.assertEqual(self.find()['offers'],[])
 def test_seller_price_is_not_verified(self):
  self.listing();r=self.find()['offers'][0]
  self.assertEqual(r['price_trust'],'seller_declared');self.assertIsNone(r['price_verified_at']);self.assertEqual(r['seller_type'],'private')
  self.socket.assert_not_called()
 def test_local_requires_city(self):
  with self.assertRaises(ValueError):SearchOffers(query='RTX 5060',category='GPU',geo_mode='local')
 def test_city_keys_and_limits_are_distinct(self):
  base=SearchOffers(query='RTX 5060',category='GPU')
  keys={search_key(base.model_copy(update=changes)) for changes in ({},{'city_id':KEM},{'city_id':MOS},{'geo_mode':'local','city_id':KEM},{'max_price':19000},{'limit':1})}
  self.assertEqual(len(keys),6)
  self.listing(price='18000');self.listing(price='19000')
  self.assertEqual(len(self.find(max_price=18500,limit=1)['offers']),1)
 def test_delivery_must_have_target_and_fresh_evidence(self):
  item=self.listing(MOS)
  self.assertEqual(self.find(city_id=KEM,geo_mode='delivery')['offers'],[])
  self.db.add(ListingDelivery(listing_id=item.id,evidence=json.dumps({'city_ids':[KEM],'cost_rub':None,'checked_at':NOW.isoformat(),'kind':'seller_declared','basis':'Fixture seller delivery statement'})));self.db.commit()
  r=self.find(city_id=KEM,geo_mode='delivery')['offers'][0]
  self.assertIsNone(r['geography']['delivery_cost_rub']);self.assertTrue(r['geography']['delivery_cost_unknown'])
 def test_known_delivery_cost_is_used_for_ranking_and_budget(self):
  item=self.listing(MOS)
  self.db.add(ListingDelivery(listing_id=item.id,evidence=json.dumps({'city_ids':[KEM],'cost_rub':1500,'checked_at':NOW.isoformat(),'kind':'seller_declared','basis':'Fixture seller delivery statement'})));self.db.commit()
  r=self.find(city_id=KEM,geo_mode='delivery')['offers'][0]
  self.assertEqual(r['price_rub'],18000);self.assertEqual(r['total_known_cost_rub'],19500)
 def test_network_sources_default_deny_including_avito(self):
  with patch('app.services.offers.search_public') as fetch:
   for source in ('dns','regard','avito'):
    r=collect_source(source,SearchOffers(query='RTX 5060',category='GPU',sources=[source]),None,{}, {})
    self.assertEqual(r[4]['outcome'],'access_not_permitted')
   fetch.assert_not_called()
 def test_import_is_private_and_direct_id_stays_hidden(self):
  self.import_fixture()
  self.assertEqual(search_offers(self.db,SearchOffers(query='RTX 5060',category='GPU',sources=['regard']))['offers'],[])
  row=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='GPU'))
  self.assertFalse(current_result(self.db,{'offer_id':row.id}))
 def import_fixture(self):
  config=schema();config['geography']=geography();config['technical']=technical()
  f=self.root/'fixture.csv';f.write_bytes(csv_bytes(rows(NOW.isoformat())))
  s=self.root/'schema.json';s.write_text(json.dumps(config),encoding='utf-8')
  permission=rights();permission['confirmed_at']=NOW.isoformat()
  apply_import(self.engine,f,s,prepare_import(self.engine,f,s),permission,fixture=True)
 def test_mixed_eight_part_build_is_draft_and_within_80000(self):
  self.import_fixture();self.listing()
  request=BuildRequest(scenario='build',auto_parts=True,budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['upgradelab','regard'],city_id=KEM,geo_mode='local',allow_store_fallback=False,allow_platform_change=False)
  with fixture_catalog():r=assemble(request,self.db)
  self.assertEqual(len(r['parts']),8);self.assertLessEqual(r['total_price'],80000);self.assertEqual(r['status'],'draft');self.assertFalse(r['purchase_ready'])
  self.assertIn('seller_declared',[p['price_origin'] for p in r['parts']]);self.assertEqual(sum(p['price'] for p in r['parts']),r['total_price'])
  self.socket.assert_not_called()
 def test_m2_unknown_incompatible_and_confirmed_are_distinct(self):
  board=SimpleNamespace(name='Maxsun B450M',attributes='{}');drive=SimpleNamespace(name='Netac NV3000-Q 512GB',category='storage',condition='new',source='regard',url='fixture://ssd',attributes='{}')
  self.assertEqual(storage_status(board,drive)['status'],'unknown')
  board.name='ASRock B450M-HDV R4.0 DDR4';board.attributes=json.dumps({'storage_slots':technical()['storage_slots']});self.assertEqual(storage_status(board,drive)['status'],'compatible')
  data=technical()['storage_slots'];data['slots']=[{'kind':'M.2','interfaces':['SATA'],'sizes':[2242],'available':1}]
  board.attributes=json.dumps({'storage_slots':data});self.assertEqual(storage_status(board,drive)['status'],'incompatible')
 def test_no_free_storage_slot_is_incompatible(self):
  data=technical()['storage_slots'];data['slots'][1]['available']=0
  board=SimpleNamespace(name='ASRock B450M-HDV R4.0 DDR4',attributes=json.dumps({'storage_slots':data}));drive=SimpleNamespace(name='Netac NV3000-Q 512GB',category='storage',condition='new',source='regard',url='fixture://ssd',attributes='{}')
  self.assertEqual(storage_status(board,drive)['reason'],'no_free_storage_slot')
 def test_psu_revision_model_and_connectors_distinct(self):
  for name,reason in [('DeepCool PF550 550W','psu_model_unknown'),('DeepCool PK650D V2 650W','psu_revision_unknown'),('MSI MAG A650BN 650W','psu_connectors_unknown')]:
   row=SimpleNamespace(name=name,category='psu',condition='new',source='regard',attributes='{}')
   self.assertEqual(psu_status(row)['reason'],reason)
  row=SimpleNamespace(name='MSI MAG A650BN 650W',category='psu',condition='new',source='regard',attributes=json.dumps(technical()))
  self.assertEqual(psu_status(row)['status'],'compatible')

 def test_cached_job_drops_changed_or_closed_offers(self):
  from app.services.search_jobs import public_job
  item=self.listing();offer=self.find()['offers'][0]
  job=SimpleNamespace(id='a'*48,kind='assemble',status='completed',progress='done',created_at=NOW.replace(tzinfo=None),updated_at=NOW.replace(tzinfo=None),error=None,result=json.dumps({'parts':[{'offer_id':offer['id'],'price':18000}]}))
  self.assertIsNotNone(public_job(job,self.db)['result'])
  item.city_id=MOS;self.db.commit();self.assertIsNone(public_job(job,self.db)['result'])
 def test_job_keys_include_city_and_listing_revision(self):
  from app.services.search_jobs import create_job
  item=self.listing();payload={'city_id':KEM,'geo_mode':'local'}
  with patch('app.services.search_jobs.executor.submit'):
   first=create_job(self.db,'assemble',payload,'fixture-request-0001')
   same=create_job(self.db,'assemble',payload,'fixture-request-0001');self.assertEqual(first['id'],same['id'])
   other=create_job(self.db,'assemble',{'city_id':MOS,'geo_mode':'local'},'fixture-request-0001');self.assertNotEqual(first['id'],other['id'])
   item.price='19000';self.db.commit();changed=create_job(self.db,'assemble',payload,'fixture-request-0001')
   self.assertNotEqual(first['id'],changed['id'])
 def test_delivery_declaration_requires_listing_owner(self):
  from app.api.listings import declare_delivery,SellerDeliveryRequest
  from fastapi import HTTPException
  item=self.listing()
  with self.assertRaises(HTTPException):declare_delivery(item.id,SellerDeliveryRequest(city_ids=[MOS],cost_rub=None),self.db,SimpleNamespace(id=2))
  evidence=declare_delivery(item.id,SellerDeliveryRequest(city_ids=[MOS],cost_rub=None),self.db,SimpleNamespace(id=1))
  self.assertEqual(evidence['kind'],'seller_declared');self.assertIsNone(evidence['cost_rub'])
 def test_new_table_migrates_without_rewriting_legacy_records(self):
  from sqlalchemy import inspect
  target=create_engine('sqlite://')
  try:
   Base.metadata.create_all(target,tables=[t for t in Base.metadata.sorted_tables if t.name!='listing_delivery'])
   with Session(target) as old:
    old.add(User(id=17,email='legacy@example.invalid',name='Legacy',password_hash='legacy snapshot'));old.commit()
   self.assertNotIn('listing_delivery',inspect(target).get_table_names())
   ListingDelivery.__table__.create(target,checkfirst=True)
   with Session(target) as migrated:self.assertEqual(migrated.get(User,17).password_hash,'legacy snapshot')
   self.assertIn('listing_delivery',inspect(target).get_table_names())
  finally:target.dispose()
 def test_upgrade_uses_own_offer_in_the_selected_city(self):
  from app.api.calculate import post_calculate
  from app.schemas.calculate import CalculateRequest
  self.listing();self.db.add(Hardware(id=10,type='GPU',name='GeForce GTX 1650',vram=4,raw_score=8000,normalized_score=20));self.db.commit()
  payload=CalculateRequest(cpu_id=1,gpu_id=10,ram_manual={'type':'DDR4','capacity_gb':16,'channels':2},game='Red Dead Redemption 2',mode='1080p_high',budget=25000,price_sources=['upgradelab'],city_id=KEM,geo_mode='local')
  r=post_calculate(payload,self.db)
  self.assertEqual(r.upgrade_id,2);self.assertEqual(r.avg_price,18000)
  self.assertEqual(r.upgrade_price['price_origin'],'seller_declared');self.assertIsNone(r.upgrade_price['price_verified_at'])
  other=post_calculate(payload.model_copy(update={'city_id':MOS}),self.db)
  self.assertFalse(other.upgrade_price and other.upgrade_price.get('avg_price'))
 def test_known_local_prices_complete_but_unknown_connectors_draft(self):
  self.import_fixture()
  with fixture_catalog():
   for row in self.db.scalars(select(StoreOffer)):
    attrs=json.loads(row.attributes);attrs['price_verification']={'status':'verified','checked_at':NOW.isoformat()}
    dimensions={'motherboard':{'form_factor':'mATX'},'GPU':{'length_mm':250},'case':{'board_formats':['mATX'],'psu_formats':['ATX'],'max_gpu_length_mm':400,'max_cooler_height_mm':200},'psu':{'form_factor':'ATX'},'cooler':{'height_mm':150}}
    attrs.update(dimensions.get(row.category,{}));row.attributes=json.dumps(attrs);row.origin='product_page'
   self.db.commit()
   request=BuildRequest(scenario='build',auto_parts=True,budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['regard'],city_id=KEM,geo_mode='local',allow_store_fallback=False,allow_platform_change=False)
   r=assemble(request,self.db);self.assertEqual(r['status'],'complete');self.assertTrue(r['purchase_ready'])
   supply=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='psu'));attrs=json.loads(supply.attributes);attrs.pop('power_connectors');supply.attributes=json.dumps(attrs);self.db.commit()
   r=assemble(request,self.db);self.assertEqual(r['status'],'draft');self.assertFalse(r['purchase_ready']);self.assertEqual(r['compatibility_status'],'unknown')
 def test_psu_power_and_connector_incompatibility_are_explicit(self):
  row=SimpleNamespace(name='MSI MAG A650BN 650W',category='psu',condition='new',source='regard',attributes=json.dumps(technical()))
  cpu=SimpleNamespace(name='AMD Ryzen 5 5600');gpu=SimpleNamespace(name='GeForce RTX 4090')
  self.assertEqual(psu_status(row,cpu,gpu)['reason'],'psu_insufficient_power')
  data=technical();data['power_connectors']['atx24']=False;row.attributes=json.dumps(data)
  self.assertEqual(psu_status(row)['reason'],'psu_connectors_insufficient')
 def test_stale_store_stock_is_not_local_and_unavailable_is_excluded(self):
  row=StoreOffer(source='oldi',url='https://www.oldi.ru/catalog/element/990111/',name='GeForce RTX 5060 8GB',category='GPU',price_rub=19000,hardware_id=2,observed_at=NOW.replace(tzinfo=None),origin='public_page',condition='new',attributes=json.dumps({'geography':{**geography(),'checked_at':(NOW-timedelta(days=2)).isoformat()}}))
  self.db.add(row);self.db.commit()
  p=SearchOffers(query='RTX 5060',category='GPU',sources=['oldi'],city_id=KEM,geo_mode='local')
  self.assertEqual(search_offers(self.db,p)['offers'],[])
  row.attributes=json.dumps({'geography':{**geography(),'availability':'unavailable'}});self.db.commit()
  self.assertEqual(search_offers(self.db,p.model_copy(update={'geo_mode':'all'}))['offers'],[])

 def test_technical_configuration_cannot_inject_price_verification(self):
  from app.schemas.catalog import CatalogSchema
  config=schema();config['technical']={'price_verification':{'status':'verified','checked_at':NOW.isoformat()}}
  with self.assertRaises(ValueError):CatalogSchema.model_validate(config)
 def test_delivery_changes_invalidate_cached_snapshot(self):
  item=self.listing(MOS)
  delivery={'city_ids':[KEM],'cost_rub':1500,'checked_at':NOW.isoformat(),'kind':'seller_declared','basis':'Fixture delivery statement'}
  row=ListingDelivery(listing_id=item.id,evidence=json.dumps(delivery));self.db.add(row);self.db.commit()
  result=self.find(city_id=KEM,geo_mode='delivery')['offers'][0]
  snapshot={'offer_id':result['id'],'goods_price_rub':18000,'geography':result['geography']}
  self.assertTrue(current_result(self.db,snapshot))
  delivery['cost_rub']=2500;row.evidence=json.dumps(delivery);self.db.commit()
  self.assertFalse(current_result(self.db,snapshot))
  self.find(city_id=KEM,geo_mode='delivery');self.assertFalse(current_result(self.db,snapshot))

 def test_combined_cpu_gpu_title_cannot_borrow_single_hardware_id(self):
  self.listing(title='GeForce RTX 5060 8GB + Ryzen 5 5600',hardware_id=2)
  self.assertEqual(self.find()['offers'],[])

 def test_new_internal_offer_has_durable_id_even_on_search_cache_hit(self):
  self.listing();self.find()
  second=self.listing(price='19500');r=self.find()
  self.assertTrue(r['search_cached'])
  offer=next(o for o in r['offers'] if o['price_rub']==19500)
  with Session(self.engine) as reader:self.assertIsNotNone(reader.get(StoreOffer,offer['id']))

 def test_saved_local_price_does_not_stay_confirmed_after_location_change(self):
  from app.services.saved_prices import capture_snapshot,review_prices
  row=StoreOffer(source='oldi',url='https://www.oldi.ru/catalog/element/990222/',name='GeForce RTX 5060 8GB',category='GPU',price_rub=19000,hardware_id=2,observed_at=NOW.replace(tzinfo=None),origin='product_page',condition='new',attributes=json.dumps({'geography':geography(),'price_verification':{'status':'verified','checked_at':NOW.isoformat()}}))
  self.db.add(row);self.db.commit()
  payload=SearchOffers(query='RTX 5060',category='GPU',city_id=KEM,geo_mode='local')
  with offer_scope(payload):g=geo_details(row)
  result={'total_price':19000,'parts':[{'type':'GPU','name':row.name,'price':19000,'offer_id':row.id,'price_url':row.url,'geography':g,'delivery_cost_rub':0}]}
  data={'result':result,'price_snapshot':capture_snapshot(self.db,result)}
  self.assertEqual(review_prices(self.db,data)['current_total'],19000)
  attrs=json.loads(row.attributes);attrs['geography']=geography(MOS);row.attributes=json.dumps(attrs);self.db.commit()
  self.assertIsNone(review_prices(self.db,data)['current_total']);self.assertEqual(review_prices(self.db,data)['historical_total'],19000)

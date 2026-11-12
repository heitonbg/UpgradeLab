"""Eight-category marketplace/API/optimizer regressions, with no external network."""
import sys,json,unittest,sqlite3,socket
REAL_SOCKET=socket.socket
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timedelta
from unittest.mock import patch
from sqlalchemy import select,create_engine,inspect
from sqlalchemy.orm import Session
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
import test_unified_geo_offers as fixture
from app.api import listings as api
from app.schemas.listing import ListingCreate,ListingUpdate,ListingOut
from app.schemas.listing_details import SellerDelivery
from app.db.models import Base,Listing,ListingDetails,ListingOwner,User,StoreOffer,Hardware
from app.services.catalog_access import fixture_catalog
from app.services.offers import search_offers,available_offers
from app.schemas.offers import SearchOffers
from app.services.result_access import listing_revision,current_result
from app.services.listing_specs import assess_listing
from app.services.physical_fit import physical_fit

CASES={
 'CPU':('AMD Ryzen 5 5600',5000,1,{'manufacturer':'AMD','socket':'AM4'}),
 'GPU':('GeForce RTX 5060 8GB',18000,2,{'vram':8,'length_mm':250}),
 'motherboard':('ASRock B450M-HDV R4.0 DDR4',8000,None,{'socket':'AM4','ram_type':'DDR4','form_factor':'mATX','m2_free_slots':1}),
 'memory':('DDR4 2x8GB',4000,None,{'ram_type':'DDR4','capacity_gb':16,'modules':2,'module_type':'DIMM'}),
 'storage':('Samsung 870 EVO 500GB',3000,None,{'capacity_gb':500,'interface':'SATA','form_factor':'2.5'}),
 'psu':('MSI MAG A650BN 650W',3000,None,{'watts':650,'form_factor':'ATX','power_connectors':'2 x 6+2 pin'}),
 'case':('DeepCool CC560',3000,None,{'board_formats':['mATX'],'psu_formats':['ATX'],'max_gpu_length_mm':400,'max_cooler_height_mm':200}),
 'cooler':('DeepCool AG400',1000,None,{'sockets':['AM4'],'height_mm':150,'cooling_type':'air'})}
class MarketplaceCategoryTests(unittest.TestCase):
 def setUp(self):
  self.f=fixture.UnifiedGeoTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.db=self.f.db;self.engine=self.f.engine;self.user=self.db.get(User,1)
 def create(self,category='GPU',**extra):
  name,price,hardware,specs=CASES[category]
  payload=dict(title=name,category=category,price=str(price),hardware_id=hardware,characteristics=specs,condition='Новое',contact='@fixture_seller',contact_type='telegram',city_id=fixture.KEM,confirm_availability=True)
  payload.update(extra);return api.create_listing(ListingCreate(**payload),self.db,self.user)
 def search(self,category,query,city=None,mode='all'):
  return search_offers(self.db,SearchOffers(query=query,category=category,sources=['upgradelab'],city_id=city,geo_mode=mode))
 def test_create_cpu(self):self.assertEqual(self.create('CPU').category,'CPU')
 def test_create_gpu(self):self.assertEqual(self.create('GPU').hardware_id,2)
 def test_create_motherboard(self):self.assertEqual(self.create('motherboard').characteristics['socket'],'AM4')
 def test_create_ram(self):self.assertEqual(self.create('memory').characteristics['modules'],2)
 def test_create_ssd(self):self.assertEqual(self.create('storage').characteristics['interface'],'SATA')
 def test_create_psu(self):self.assertEqual(self.create('psu').characteristics['watts'],650)
 def test_create_case(self):self.assertEqual(self.create('case').characteristics['max_gpu_length_mm'],400)
 def test_create_cooler(self):self.assertEqual(self.create('cooler').characteristics['height_mm'],150)
 def test_all_categories_visible_and_untrusted_psu_not_optimized(self):
  for category in CASES:self.create(category)
  for category,(name,*_) in CASES.items():
   with self.subTest(category=category):self.assertEqual(len(self.search(category,name)['offers']),1)
  self.assertEqual(len(available_offers(self.db,['upgradelab'],'psu')),0)
  view=self.search('psu','MSI MAG A650BN')['offers'][0]
  self.assertFalse(view['optimizer_eligible']);self.assertEqual(view['price_trust'],'seller_declared')
 def test_no_characteristics_required_for_publication(self):
  row=self.create('psu',title='Блок питания 650W',characteristics={});self.assertEqual(row.publication_status,'active')
  self.assertEqual(row.technical_assessment['state'],'insufficient_data');self.assertFalse(row.technical_assessment['optimizer_eligible'])
 def test_seller_cannot_submit_verified_metadata(self):
  with self.assertRaises(ValueError):self.create(characteristics={'price_verification':{'status':'verified'}})
  with self.assertRaises(ValueError):SellerDelivery(city_ids=[fixture.KEM],kind='store_confirmed')
 def test_unknown_and_contradictory_specs_are_distinct(self):
  unknown=self.create('psu',title='Блок питания 650W',characteristics={})
  contradiction=self.create('motherboard',characteristics={'ram_type':'DDR5','socket':'AM5'})
  self.assertEqual(unknown.technical_assessment['state'],'insufficient_data')
  self.assertEqual(contradiction.technical_assessment['state'],'contradictory')
 def test_m2_not_derived_from_chipset(self):
  row=self.create('motherboard',title='Материнская плата Generic B450',characteristics={'socket':'AM4','ram_type':'DDR4','storage_interfaces':['NVMe']},description='M.2 2280 PCIe NVMe')
  self.assertFalse(row.technical_assessment['optimizer_eligible'])
 def test_nvme_and_sata_conflict(self):
  row=self.create('storage',characteristics={'interface':'NVMe','capacity_gb':500})
  self.assertEqual(row.technical_assessment['state'],'contradictory')
 def test_ram_ddr_and_kit_conflicts(self):
  for specs in ({'ram_type':'DDR5','capacity_gb':16,'modules':2},{'ram_type':'DDR4','capacity_gb':32,'modules':2}):
   with self.subTest(specs=specs):self.assertEqual(self.create('memory',characteristics=specs).technical_assessment['state'],'contradictory')
 def test_psu_revision_not_inherited(self):
  row=self.create('psu',title='DeepCool PK650D V2 650W',characteristics={'watts':650,'revision':'V2','power_connectors':'2x8'})
  self.assertFalse(row.technical_assessment['optimizer_eligible'])
 def test_catalog_model_mismatch_is_rejected(self):
  from fastapi import HTTPException
  with self.assertRaises(HTTPException):self.create('GPU',title='GeForce RTX 5060 Ti 16GB',hardware_id=2)
 def test_category_change_clears_old_hardware_and_specs(self):
  row=self.create();updated=api.update_listing(row.id,ListingUpdate(category='case',title='DeepCool CC560'),self.db,self.user)
  self.assertIsNone(updated.hardware_id);self.assertEqual(updated.characteristics,{})
 def test_title_only_edit_does_not_keep_old_hardware(self):
  row=self.create();api.update_listing(row.id,ListingUpdate(title='GeForce RTX 5060 Ti 16GB'),self.db,self.user)
  self.assertIsNone(row.hardware_id);self.assertIsNone(row.availability_confirmed_at)
 def test_specs_and_price_changes_invalidate_cache_and_confirmation(self):
  row=self.create('case');revision=listing_revision(self.db)
  api.update_listing(row.id,ListingUpdate(characteristics={'board_formats':['Mini-ITX']},price='3500'),self.db,self.user)
  self.assertNotEqual(revision,listing_revision(self.db));self.assertIsNone(row.availability_confirmed_at)
 def test_delivery_creation_edit_and_explicit_free(self):
  row=self.create(delivery={'mode':'cities','city_ids':[fixture.MOS],'cost_rub':700})
  self.assertEqual(row.delivery['cost_rub'],700)
  result=api.declare_delivery(row.id,SellerDelivery(mode='russia',cost_rub=0),self.db,self.user)
  self.assertEqual(result['cost_kind'],'free');self.assertEqual(result['kind'],'seller_declared')
 def test_unknown_delivery_not_zero_and_no_final_price(self):
  row=self.create(delivery={'mode':'russia','cost_rub':None})
  result=self.search('GPU','RTX 5060',fixture.MOS,'delivery')['offers'][0]
  self.assertIsNone(result['geography']['delivery_cost_rub']);self.assertTrue(result['geography']['delivery_cost_unknown'])
 def test_paid_delivery_added_exactly(self):
  row=self.create(delivery={'mode':'cities','city_ids':[fixture.MOS],'cost_rub':700})
  r=self.search('GPU','RTX 5060',fixture.MOS,'delivery')['offers'][0]
  self.assertEqual(r['price_rub'],18000);self.assertEqual(r['total_known_cost_rub'],18700)
 def test_pickup_does_not_promise_remote_shipping(self):
  self.create(delivery={'mode':'pickup'})
  self.assertEqual(len(self.search('GPU','RTX 5060',fixture.KEM,'local')['offers']),1)
  self.assertEqual(self.search('GPU','RTX 5060',fixture.MOS,'delivery')['offers'],[])
 def test_delivery_fractional_and_unknown_city_rejected(self):
  for data in ({'mode':'russia','cost_rub':1.5},{'mode':'cities','city_ids':['not-a-city']},{'mode':'russia','cost_rub':True}):
   with self.subTest(data=data),self.assertRaises(ValueError):SellerDelivery(**data)
 def test_foreign_owner_cannot_edit_specs_or_delivery(self):
  from fastapi import HTTPException
  row=self.create()
  for call in (lambda:api.update_listing(row.id,ListingUpdate(characteristics={'vram':16}),self.db,SimpleNamespace(id=2)),lambda:api.declare_delivery(row.id,SellerDelivery(mode='russia'),self.db,SimpleNamespace(id=2))):
   with self.assertRaises(HTTPException) as caught:call()
   self.assertEqual(caught.exception.status_code,404)
 def test_sold_withdrawn_deleted_not_returned(self):
  row=self.create()
  for state in ('sold','withdrawn'):
   api.update_listing(row.id,ListingUpdate(publication_status=state),self.db,self.user)
   self.assertEqual(self.search('GPU','RTX 5060')['offers'],[])
  api.delete_listing(row.id,self.db,self.user);self.assertEqual(api.get_listings(self.db),[])
 def test_legacy_without_details_or_delivery_remains_editable(self):
  row=self.f.listing();created=row.created_at
  api.update_listing(row.id,ListingUpdate(description='Legacy edited'),self.db,self.user)
  self.assertEqual(row.characteristics,{});self.assertIsNone(row.delivery);self.assertEqual(row.hardware_id,2);self.assertEqual(row.created_at,created)
 def test_dangerous_photo_and_spec_payload_rejected(self):
  for photo in ('javascript:alert(1)','https://user:secret@example.com/a.png','https://127.0.0.1/private'):
   with self.subTest(photo=photo),self.assertRaises(ValueError):self.create(photo_url=photo)
  with self.assertRaises(ValueError):self.create('case',characteristics={'model':'<script>alert(1)</script>'})
 def test_public_view_does_not_expose_private_user_data(self):
  row=self.create();view=ListingOut.model_validate(row).model_dump()
  text=json.dumps(view);self.assertNotIn(self.user.password_hash,text);self.assertNotIn(self.user.email,text);self.assertIn('Fixture seller',text)
 def test_atomic_create_rolls_back_on_delivery_failure(self):
  from sqlalchemy import func
  before=self.db.scalar(select(func.count()).select_from(Listing))
  with patch('app.api.listings.save_delivery',side_effect=RuntimeError('fixture failure')):
   with self.assertRaises(RuntimeError):self.create(delivery={'mode':'russia'})
  self.db.rollback();self.assertEqual(self.db.scalar(select(func.count()).select_from(Listing)),before)
 def test_trusted_profile_required_and_private_reference_not_leaked(self):
  self.f.import_fixture()
  row=self.create('psu');self.assertFalse(row.technical_assessment['optimizer_eligible']);self.assertEqual(row.technical_assessment['trusted_fields'],{})
  with fixture_catalog():
   valid=assess_listing(self.db,row);self.assertTrue(valid['assessment']['optimizer_eligible'])
  self.assertFalse(assess_listing(self.db,row)['assessment']['optimizer_eligible'])
 def test_all_eight_own_categories_can_form_a_draft(self):
  self.f.import_fixture()
  from app.services.builds import BuildRequest,assemble
  with fixture_catalog():
   for category in CASES:self.create(category)
   p=BuildRequest(scenario='build',auto_parts=True,budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['upgradelab'],city_id=fixture.KEM,geo_mode='local',allow_store_fallback=False,allow_platform_change=False)
   r=assemble(p,self.db)
  self.assertEqual(len(r['parts']),8);self.assertEqual(r['status'],'draft');self.assertFalse(r['purchase_ready']);self.assertLessEqual(r['total_price'],80000)
  self.assertTrue(all(part['price_origin']=='seller_declared' for part in r['parts']))
 def test_physical_case_and_cooler_constraints(self):
  def row(data):return SimpleNamespace(attributes=json.dumps(data),source='upgradelab')
  board=row({'form_factor':'mATX'});gpu=row({'length_mm':300});case=row({'board_formats':['mATX'],'psu_formats':['ATX'],'max_gpu_length_mm':200,'max_cooler_height_mm':160});psu=row({'form_factor':'ATX'});cooler=row({'height_mm':150})
  self.assertEqual(physical_fit(board,gpu,case,psu,cooler)['reason'],'case_gpu_length')
  gpu=row({'length_mm':190});cooler=row({'height_mm':170});self.assertEqual(physical_fit(board,gpu,case,psu,cooler)['reason'],'case_cooler_height')
 def test_additive_details_migration_keeps_legacy_model(self):
  target=create_engine('sqlite://')
  try:
   Base.metadata.create_all(target,tables=[t for t in Base.metadata.sorted_tables if t.name!='listing_details'])
   with target.begin() as c:c.exec_driver_sql("INSERT INTO listings (id,title,condition,price,contact,created_at,hardware_id) VALUES (1,'Legacy GPU','Б/У','100','legacy','2026-11-09',NULL)")
   Base.metadata.create_all(target)
   with Session(target) as db:self.assertEqual(db.get(Listing,1).title,'Legacy GPU');self.assertEqual(db.get(Listing,1).characteristics,{})
  finally:target.dispose()

 def test_atomic_price_and_delivery_edit_without_autoflush(self):
  row=self.create(delivery={'mode':'russia','cost_rub':700})
  self.db.autoflush=False
  updated=api.update_listing(row.id,ListingUpdate(price='19000',delivery=SellerDelivery(mode='russia',cost_rub=900),confirm_availability=True),self.db,self.user)
  self.assertEqual(updated.delivery['cost_rub'],900);self.assertEqual(updated.price,'19000')
 def test_incomplete_gpu_not_used_by_upgrade_estimates(self):
  from app.services.upgrade_prices import upgrade_market_rows
  self.create(title='GeForce RTX 5060',characteristics={})
  self.assertEqual(upgrade_market_rows(self.db,['upgradelab']),[])
 def test_internal_partial_search_has_no_external_site_links(self):
  from app.services.search_links import web_search_links
  self.assertEqual(web_search_links('upgradelab','SSD'),[])
 def test_anonymous_mutations_require_authentication(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from app.api.deps import get_db
  patch('socket.socket',REAL_SOCKET).start()
  app=FastAPI();app.include_router(api.router);app.dependency_overrides[get_db]=lambda:self.db
  with TestClient(app) as client:
   for method,path,body in [('post','/api/listings',{}),('patch','/api/listings/1',{}),('put','/api/listings/1/delivery',{'mode':'russia'}),('delete','/api/listings/1',None)]:
    with self.subTest(method=method):
     response=client.request(method,path,json=body);self.assertEqual(response.status_code,401)

 def test_declared_full_model_cannot_contradict_selected_hardware(self):
  row=self.create('GPU',characteristics={'vram':8,'model':'GeForce RTX 5060 Ti'})
  self.assertEqual(row.technical_assessment['state'],'contradictory')
 def test_declared_nvme_size_cannot_borrow_2280_profile(self):
  specs={'interface':'NVMe','form_factor':'M.2','m2_size':2280,'capacity_gb':512}
  good=self.create('storage',title='Kingston KC3000 512GB M.2 NVMe',characteristics=specs)
  self.assertTrue(good.technical_assessment['optimizer_eligible'])
  row=self.create('storage',title='Kingston KC3000 512GB M.2 NVMe',characteristics={**specs,'m2_size':2230})
  self.assertFalse(row.technical_assessment['optimizer_eligible'])
 def test_full_solver_excludes_case_gpu_and_cooler_size_conflicts(self):
  from app.services.automatic_builds import assemble_auto
  from app.services.builds import BuildRequest
  from fastapi import HTTPException
  self.f.import_fixture()
  with fixture_catalog():
   created={category:self.create(category) for category in CASES}
   p=BuildRequest(scenario='build',auto_parts=True,budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['upgradelab'],allow_platform_change=False)
   for specs in ({'board_formats':['mATX'],'psu_formats':['ATX'],'max_gpu_length_mm':200,'max_cooler_height_mm':200},{'board_formats':['mATX'],'psu_formats':['ATX'],'max_gpu_length_mm':400,'max_cooler_height_mm':100}):
    api.update_listing(created['case'].id,ListingUpdate(characteristics=specs,confirm_availability=True),self.db,self.user)
    with self.assertRaises(HTTPException):assemble_auto(p,self.db,observed=True)
 def test_saved_old_listing_keeps_history_after_sale(self):
  from app.services.saved_prices import capture_snapshot,review_prices
  row=self.create();offer=self.search('GPU','RTX 5060')['offers'][0]
  result={'total_price':18000,'parts':[{'type':'GPU','name':row.title,'price':18000,'offer_id':offer['id'],'price_url':offer['url']}]}
  data={'result':result,'price_snapshot':capture_snapshot(self.db,result)};before=json.dumps(data,default=str)
  api.update_listing(row.id,ListingUpdate(publication_status='sold'),self.db,self.user)
  review=review_prices(self.db,data)
  self.assertEqual(before,json.dumps(data,default=str));self.assertIsNone(review['current_total'])
 def test_reproducible_demo(self):
  from scripts.marketplace_categories_demo import run
  r=run(self.f.root/'demo')
  self.assertEqual(len(r['public_listings']),8);self.assertEqual(len(r['build']['parts']),8)
  self.assertEqual(r['build']['status'],'draft');self.assertFalse(r['result_valid_after_sale'])
  self.assertEqual(r['network_requests'],0)

import sys, unittest, tempfile, json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db.models import Base, AiDailyBudget, CatalogDailyPrice, CatalogPriceCorrection
from app.services import product_discovery as discovery
from app.services.catalog_history import source_day, record_prices
from app.schemas.product_discovery import DiscoveryQuery
from app.core.config import settings

class DatabaseCase(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.engine=create_engine('sqlite:///'+str(Path(self.temp.name)/'test.db'));Base.metadata.create_all(self.engine);self.addCleanup(self.engine.dispose)
  self.clock=patch('app.core.price_time.utc_now',return_value=datetime(2026,11,10,12,tzinfo=timezone.utc));self.clock.start();self.addCleanup(self.clock.stop)

class DiscoveryTests(DatabaseCase):
 def test_strict_json_and_no_price_invention(self):
  query=DiscoveryQuery(model='Ryzen 5 5600',category='CPU',sources=['dns'])
  output=discovery.parse_json('{"urls":["https://attacker.invalid/product/1"]}')
  self.assertEqual(discovery.grounded_candidates(query,output,[]),[])
  with self.assertRaises(discovery.DiscoveryFailure):discovery.parse_json('{"urls":[],"price":100}')
 def test_disabled_search_never_contacts_provider(self):
  with patch.object(settings,'openrouter_search_enabled',False),patch.object(discovery,'model_catalog',side_effect=AssertionError('network')):
   self.assertEqual(discovery.perform_search(DiscoveryQuery(model='Ryzen 5600',category='CPU',sources=['dns']),self.engine)['status'],'blocked')
 def test_contacts_rejected(self):
  for model in ['test@example.org','https://example.org','+7 (999) 123-45-67']:
   with self.assertRaises(ValueError):DiscoveryQuery(model=model,category='CPU',sources=['dns'])
 def test_budget_cannot_be_exceeded(self):
  with patch.object(settings,'openrouter_daily_requests',1),patch.object(settings,'openrouter_daily_tokens',100000),patch.object(settings,'openrouter_daily_web_microusd',14000):
   discovery.reserve(self.engine)
   with self.assertRaises(discovery.DiscoveryFailure):discovery.reserve(self.engine)
 def test_success_resets_consecutive_provider_errors(self):
  with Session(self.engine) as db:
   db.add(AiDailyBudget(day='2026-11-10',requests=1,reserved_tokens=1,reserved_microusd=1,used_tokens=0,used_microusd=0,errors=2));db.commit()
  discovery.settle(self.engine,'2026-11-10',status=200)
  with Session(self.engine) as db:self.assertEqual(db.get(AiDailyBudget,'2026-11-10').errors,0)
 def test_429_sets_durable_cooldown(self):
  with patch.object(settings,'openrouter_daily_requests',10),patch.object(settings,'openrouter_daily_tokens',100000),patch.object(settings,'openrouter_daily_web_microusd',14000):
   day=discovery.reserve(self.engine);discovery.settle(self.engine,day,status=429,retry_after=90)
   with self.assertRaisesRegex(discovery.DiscoveryFailure,'provider_cooldown'):discovery.reserve(self.engine)

 def test_parallel_reservations_share_one_limit(self):
  from concurrent.futures import ThreadPoolExecutor
  def attempt(_):
   try:discovery.reserve(self.engine);return True
   except discovery.DiscoveryFailure:return False
  with patch.object(settings,'openrouter_daily_requests',2),patch.object(settings,'openrouter_daily_tokens',100000),patch.object(settings,'openrouter_daily_web_microusd',14000),ThreadPoolExecutor(max_workers=5) as pool:
   self.assertEqual(sum(pool.map(attempt,range(8))),2)
 def test_grounded_link_is_never_verified(self):
  url='https://www.dns-shop.ru/product/abcdef123456/protsessor-amd-ryzen-5-5600/'
  q=DiscoveryQuery(model='Ryzen 5 5600',category='CPU',sources=['dns'])
  annotations=[{'type':'url_citation','url_citation':{'url':url,'title':'AMD Ryzen 5 5600','content':'Цена 5000 рублей'}}]
  rows=discovery.grounded_candidates(q,discovery.parse_json(json.dumps({'urls':[url,url]})),annotations)
  self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['price_rub']);self.assertFalse(rows[0]['optimizer_eligible'])
  self.assertEqual(rows[0]['verification_status'],'search_discovered')
 def test_mismatched_cpu_is_not_returned(self):
  url='https://www.dns-shop.ru/product/abcdef123456/protsessor/'
  q=DiscoveryQuery(model='Ryzen 5 5600',category='CPU',sources=['dns'])
  self.assertEqual(discovery.grounded_candidates(q,discovery.parse_json(json.dumps({'urls':[url]})),[{'type':'url_citation','url_citation':{'url':url,'title':'Ryzen 5 5500'}}]),[])
 def test_jobs_are_cached_per_owner(self):
  from app.db.models import User,ExternalSearchJob
  q=DiscoveryQuery(model='Ryzen 5 5600',category='CPU',sources=['dns'])
  with Session(self.engine) as db:
   db.add_all([User(id=i,email=f'{i}@test.invalid',name='test',password_hash='unused') for i in (1,2)]);db.commit()
   a=discovery.create_job(db,1,q,submit=False);b=discovery.create_job(db,1,q,submit=False);c=discovery.create_job(db,2,q,submit=False)
   self.assertEqual(a['id'],b['id']);self.assertNotEqual(a['id'],c['id']);self.assertIsNone(a['result'])
 def test_explicit_paid_tool_caps_and_usage(self):
  from contextlib import ExitStack
  from types import SimpleNamespace
  class Transport:
   def post(inner,url,**kwargs):
    inner.body=json.loads(kwargs['data']);return SimpleNamespace(status_code=200,headers={},json=lambda:{'usage':{'total_tokens':100,'cost':0.007},'choices':[{'message':{'content':'{"urls":[]}','annotations':[]}}]})
  transport=Transport();model='test/model:free'
  with ExitStack() as stack:
   from pydantic import SecretStr
   for field,value in dict(openrouter_api_key=SecretStr('test-not-a-real-key'),openrouter_search_enabled=True,openrouter_allow_paid_web=True,openrouter_daily_web_microusd=7000,openrouter_daily_tokens=100000,openrouter_daily_requests=5,openrouter_primary_model=model,openrouter_fallback_model='').items():stack.enter_context(patch.object(settings,field,value))
   result=discovery.perform_search(DiscoveryQuery(model='Ryzen 5600',category='CPU',sources=['dns']),self.engine,transport=transport,catalog={model:{'pricing':{'prompt':'0','completion':'0'},'supported_parameters':['tools']}})
  self.assertEqual(result['status'],'completed');self.assertEqual(transport.body['max_tool_calls'],1)
  params=transport.body['tools'][0]['parameters'];self.assertEqual(params['max_uses'],1);self.assertEqual(params['engine'],'exa')
  self.assertNotIn('response_format',transport.body)
  with Session(self.engine) as db:self.assertEqual(db.get(AiDailyBudget,'2026-11-10').used_microusd,7000)

class HistoryTests(DatabaseCase):
 def plan(self,date,price):return {'source':'regard','rows':[{'key':'product','source_updated_at':date,'price':price}]}
 def write(self,date,price,receipt):
  with Session(self.engine) as db:record_prices(db,self.plan(date,price),receipt,180,None);db.commit()
 def test_source_calendar_uses_explicit_offset(self):self.assertEqual(source_day('2026-11-09T22:30:00Z',180),'2026-11-10')
 def test_same_day_correction_one_final_value(self):
  self.write('2026-11-10T08:00:00Z','100','one');self.write('2026-11-10T09:00:00Z','110','two')
  with Session(self.engine) as db:
   rows=list(db.scalars(select(CatalogDailyPrice)));self.assertEqual(len(rows),1);self.assertEqual(rows[0].price_kopecks,11000)
   self.assertEqual(len(list(db.scalars(select(CatalogPriceCorrection)))),1)
 def test_unchanged_price_still_observed_next_day(self):
  self.write('2026-11-09T08:00:00Z','100','one');self.write('2026-11-10T08:00:00Z','100','two')
  with Session(self.engine) as db:self.assertEqual(len(list(db.scalars(select(CatalogDailyPrice)))),2)
 def test_fourteen_calendar_days_only(self):
  self.write('2026-10-27T08:00:00Z','100','old');self.write('2026-10-28T08:00:00Z','100','boundary')
  with Session(self.engine) as db:self.assertEqual([r.source_day for r in db.scalars(select(CatalogDailyPrice))],['2026-10-28'])

if __name__=='__main__':unittest.main()

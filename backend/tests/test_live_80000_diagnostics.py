"""Offline regressions found while auditing the saved 80,000 RUB run."""
import json,sys,unittest,ssl,time
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from sqlalchemy import select,delete
import test_automatic_policy
from app.db.models import StoreOffer
from app.services.builds import BuildRequest,assemble
from app.services.store_providers import money
from app.services.offers import collect_source
from app.schemas.offers import SearchOffers
from app.services.safe_http import SafeSession
from app.services.network_policy import validate_url

class LiveBuildDiagnosticTests(unittest.TestCase):
 def setUp(self):
  from tests.source_grants import grant_network
  grant_network(self)
  self.fixture=test_automatic_policy.AutomaticPolicyTests();self.fixture.setUp();self.db=self.fixture.db
  self.addCleanup(self.fixture.tearDown)
  self.addCleanup(patch.stopall)
  patch('socket.socket',side_effect=AssertionError('No real network')).start()
  patch('app.services.builds.search_offers',return_value={}).start()
  self.payload={**self.fixture.payload,'budget':80000,'price_sources':['regard'],'allow_store_fallback':False,'selected_cpu_id':1,'selected_gpu_id':4}
 def add(self,category,name,price):
  self.fixture.add(category,name,price)
  self.next_id=getattr(self,'next_id',990000)+1
  next(r for r in self.db.new if isinstance(r,StoreOffer)).url=f'https://www.regard.ru/product/{self.next_id}/fixture'
 def storage(self,price):
  self.db.execute(delete(StoreOffer).where(StoreOffer.category=='storage'));self.add('storage','Samsung 870 EVO 500GB',price);self.db.commit()
 def build(self,**changes):return assemble(BuildRequest(**{**self.payload,**changes}),self.db)
 def test_9920_ssd_fits_whole_budget(self):
  self.storage(9920);r=self.build();self.assertEqual(r['status'],'draft');self.assertTrue(r['prices_confirmed']);self.assertEqual(len(r['parts']),8)
  self.assertEqual(sum(p['price'] for p in r['parts']),r['total_price']);self.assertLessEqual(r['total_price'],80000)
 def test_flexible_ssd_is_not_cut_before_total_budget_check(self):
  self.storage(18000);r=self.build();self.assertEqual(r['status'],'draft');self.assertTrue(r['prices_confirmed']);self.assertEqual(len(r['parts']),8)
  self.assertLessEqual(r['total_price'],80000)
 def test_missing_psu_remains_partial(self):
  self.storage(9920);self.db.execute(delete(StoreOffer).where(StoreOffer.category=='psu'));self.db.commit()
  r=self.build();self.assertEqual(r['status'],'partial');self.assertNotIn('psu',[p['type'] for p in r['parts']])
 def test_rejected_psu_is_not_reported_as_no_offers(self):
  self.storage(9920);self.db.execute(delete(StoreOffer).where(StoreOffer.category=='psu'));self.add('psu','DeepCool PF550 V2 550W',3726);self.db.commit()
  r=self.build();gap=next(g for g in r['missing_parts'] if g['type']=='psu')
  self.assertEqual(gap['blocking_reason'],'model_unconfirmed');self.assertEqual(gap['candidate_count'],1)
 def test_nvme_incompatibility_is_not_reported_as_budget_failure(self):
  self.db.execute(delete(StoreOffer).where(StoreOffer.category=='storage'));self.add('storage','Netac NV3000-Q 512GB M.2 NVMe',9920)
  for r in self.db.scalars(select(StoreOffer).where(StoreOffer.category=='motherboard')):r.name='Maxsun Challenger B450M';r.attributes='{}'
  self.db.commit()
  # Use the low-level compatibility diagnostic independently of CPU platform selection.
  from app.services.assembly_diagnostics import missing_diagnostic
  drive=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='storage'))
  d=missing_diagnostic('storage',[drive],[drive],8112,lambda row:False)
  self.assertEqual(d['blocking_reason'],'compatibility')
 def test_unconfirmed_prices_stay_draft(self):
  self.storage(9920)
  for r in self.db.scalars(select(StoreOffer)):r.origin='public_page'
  self.db.commit()
  with patch('app.services.price_verification.fetch',side_effect=RuntimeError('fixture unavailable')):
   r=self.build()
  self.assertEqual(r['status'],'draft');self.assertFalse(r['purchase_ready']);self.assertEqual(len(r['parts']),8)
 def test_insufficient_budget_does_not_create_complete(self):
  self.storage(9920);r=self.build(budget=20000);self.assertEqual(r['status'],'partial')
 def test_fractional_live_prices_are_not_silently_rounded(self):
  for value in ('1234.56',1234.56,'1 234,56','1e5'):
   with self.subTest(value=value),self.assertRaises(ValueError):money(value)
 def test_avito_automatic_collection_is_disabled_without_fetch(self):
  with patch('app.services.offers.search_public') as fetch:
   result=collect_source('avito',SearchOffers(query='RTX 5060',category='GPU',sources=['avito']),time.monotonic()+5,{}, {})
  fetch.assert_not_called();self.assertEqual(result[4]['outcome'],'access_not_permitted')

class TransportDiagnosticTests(unittest.TestCase):
 def test_tls_and_certificate_failures_are_distinct_and_sanitized(self):
  cases=[(ssl.SSLCertVerificationError('private-path secret'),'certificate_error'),(ssl.SSLError('private-path secret'),'tls_error'),(ConnectionRefusedError('private-path secret'),'connection_error')]
  for error,code in cases:
   with self.subTest(code=code),patch('app.services.safe_http.PinnedHTTPSConnection') as connection:
    connection.return_value.request.side_effect=error
    try:SafeSession()._once('GET',validate_url('https://www.regard.ru/product/123/'),(),{},None,time.monotonic()+5,1024)
    except Exception as observed:
     self.assertEqual(getattr(observed,'outcome',None),code);self.assertNotIn('private-path',str(observed))
    else:self.fail('transport failure was swallowed')

 def test_dns_failure_has_separate_outcome(self):
  import socket
  from app.services.network_policy import resolve_public
  with patch('socket.getaddrinfo',side_effect=socket.gaierror('private host diagnostic')):
   with self.assertRaises(Exception) as caught:resolve_public(validate_url('https://www.kns.ru/'),time.monotonic()+5)
  self.assertEqual(caught.exception.outcome,'dns_error');self.assertNotIn('private host',str(caught.exception))
 def test_typed_failure_reaches_public_source_diagnostics(self):
  from tests.source_grants import grant_network
  grant_network(self)
  from app.services.network_policy import NetworkTransportError
  with patch('app.services.offers.search_public',side_effect=NetworkTransportError('certificate_error','Сертификат не прошёл проверку')):
   response=collect_source('kns',SearchOffers(query='RTX 5060',category='GPU',sources=['kns']),time.monotonic()+5,{}, {})
  self.assertEqual(response[4]['outcome'],'certificate_error')

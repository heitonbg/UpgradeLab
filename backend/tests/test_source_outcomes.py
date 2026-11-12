"""Provider diagnostics are separate from offer origin and price freshness."""
import json,sys,time,unittest,socket
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import Base,OfferSearch
from app.schemas.offers import SearchOffers
from app.core.config import settings
from app.services.offers import collect_source,search_offers,search_key
from app.services.store_providers import parse_html,fetch
from app.services.safe_http import SafeResponse
from app.services.network_policy import Address
from requests.structures import CaseInsensitiveDict

NOW=datetime(2026,11,9,12,tzinfo=timezone.utc)
class SourceOutcomeTests(unittest.TestCase):
    def setUp(self):
        from tests.source_grants import grant_network
        grant_network(self)
        self.engine=create_engine('sqlite://');Base.metadata.create_all(self.engine);self.db=Session(self.engine)
        self.addCleanup(self.engine.dispose);self.addCleanup(self.db.close)
        self.addCleanup(patch.stopall)
        patch('app.core.price_time.utc_now',return_value=NOW).start()
        patch.object(settings,'offers_live_search',True).start()
        patch('app.services.store_providers._blocked_until',{}).start()
        patch('socket.socket',side_effect=AssertionError('No real network')).start()
        patch('app.services.safe_http.resolve_public',return_value=(Address(socket.AF_INET,'93.184.216.34'),)).start()
        self.payload=SearchOffers(query='RTX 4060',category='GPU',sources=['kns'])
    def response(self,status,body='<html/>'):
        return SafeResponse(status,CaseInsensitiveDict({'Content-Type':'text/html; charset=utf-8'}),body.encode(),'https://www.kns.ru/search.html')
    def run_response(self,status,body='<html/>'):
        with patch('app.services.safe_http.SafeSession._once',return_value=self.response(status,body)):
            return collect_source('kns',self.payload,time.monotonic()+10,{}, {})
    def test_http_errors_have_distinct_codes_without_changing_legacy_status(self):
        for http,code in [(401,'unauthorized'),(403,'blocked'),(429,'rate_limited'),(439,'blocked'),(503,'unavailable')]:
            with self.subTest(http=http),patch('app.services.store_providers._blocked_until',{}):
                result=self.run_response(http)
                self.assertEqual(result[2],'unavailable')
                self.assertEqual(result[4]['outcome'],code)
    def test_timeout_is_not_empty_result(self):
        with patch('app.services.offers.search_public',side_effect=TimeoutError()):
            result=collect_source('kns',self.payload,time.monotonic()+10,{}, {})
        self.assertEqual(result[4]['outcome'],'timeout')
    def test_network_failure_is_not_parser_drift(self):
        import requests
        with patch('app.services.offers.search_public',side_effect=requests.ConnectionError('fixture')):
            result=collect_source('kns',self.payload,time.monotonic()+10,{}, {})
        self.assertEqual(result[4]['outcome'],'network_error')
    def test_unknown_document_is_not_claimed_as_no_results(self):
        result=self.run_response(200,'<html><main>Unknown markup</main></html>')
        self.assertEqual(result[4]['outcome'],'parser_drift')
    def test_captcha_html_is_blocked(self):
        result=self.run_response(200,'<h1>Подтвердите, что вы не робот</h1>')
        self.assertEqual(result[4]['outcome'],'blocked')
    def test_valid_empty_feed_is_no_results(self):
        with patch('app.services.offers.fetch',return_value='{"offers":[]}'):
            result=collect_source('kns',self.payload,time.monotonic()+10,{'kns':'https://feed.example.com/'},{})
        self.assertEqual(result[2],'feed');self.assertEqual(result[4]['outcome'],'no_results')
    def test_invalid_feed_json_and_schema_are_parse_errors(self):
        for body in ['not json','{"other":[]}','{"offers":[{"price_rub":null}]}']:
            with self.subTest(body=body),patch('app.services.offers.fetch',return_value=body):
                result=collect_source('kns',self.payload,time.monotonic()+10,{'kns':'https://feed.example.com/'},{})
                self.assertEqual(result[4]['outcome'],'parse_error')
    def test_success_has_monotonic_duration_and_result_count(self):
        url='https://www.kns.ru/product/fixture/'
        body='<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'GeForce RTX 4060 8GB',
            'url':url,'offers':{'price':30000,'priceCurrency':'RUB'}})+'</script>'
        result=self.run_response(200,body)
        self.assertEqual(result[2],'public_page');self.assertEqual(result[4]['outcome'],'success')
        self.assertEqual(result[4]['result_count'],1);self.assertGreaterEqual(result[4]['elapsed_ms'],0)
    def test_expired_deadline_never_starts_transport(self):
        with patch('app.services.offers.search_public') as network:
            result=collect_source('kns',self.payload,time.monotonic()-1,{}, {})
        network.assert_not_called()
        self.assertFalse(result[4]['attempted']);self.assertEqual(result[4]['outcome'],'timeout')
    def test_disabled_search_does_not_claim_network_attempt(self):
        with patch.object(settings,'offers_live_search',False):
            result=collect_source('kns',self.payload,time.monotonic()+10,{}, {})
        self.assertEqual(result[4]['outcome'],'disabled');self.assertFalse(result[4]['attempted'])
    def test_browser_remains_disabled_and_not_attempted(self):
        self.payload.method='browser'
        result=collect_source('kns',self.payload,time.monotonic()+10,{}, {})
        self.assertEqual(result[4]['outcome'],'disabled');self.assertFalse(result[4]['attempted'])
    def test_cached_legacy_failure_stays_unknown_and_does_not_refresh_time(self):
        checked=NOW.replace(tzinfo=None)
        statuses=[{'source':'kns','label':'KNS','status':'unavailable','message':'Old failure',
                   'checked_at':'2026-11-09T12:00:00Z'}]
        entry=OfferSearch(key=search_key(self.payload),checked_at=checked,statuses=json.dumps(statuses))
        self.db.add(entry);self.db.commit();original=entry.statuses
        with patch('app.services.offers.collect_source') as network:
            result=search_offers(self.db,self.payload)
        network.assert_not_called()
        self.assertEqual(entry.statuses,original);self.assertEqual(entry.checked_at,checked)
        outcome=result['source_outcomes'][0]
        self.assertEqual(outcome['outcome'],'unavailable');self.assertTrue(outcome['cached'])
        self.assertIsNone(outcome['elapsed_ms'])
    def test_outcomes_persist_without_promoting_prices(self):
        with patch('app.services.safe_http.SafeSession._once',return_value=self.response(429)):
            result=search_offers(self.db,self.payload)
        row=self.db.get(OfferSearch,search_key(self.payload))
        self.assertEqual(json.loads(row.statuses)[0]['outcome'],'rate_limited')
        self.assertEqual(result['offers'],[]);self.assertEqual(result['sources'][0]['status'],'unavailable')
        self.assertFalse(result['source_outcomes'][0]['cached'])
    def test_parallel_outcomes_do_not_share_error_state(self):
        # Feed work uses distinct deterministic inputs; no shared DB in workers.
        def worker(index):
            return collect_source('kns',self.payload,time.monotonic()-1 if index%2 else time.monotonic()+10,
                                  {},{}) if index%2 else collect_source('kns',self.payload,time.monotonic()+10,
                                  {'kns':'https://feed.example.com/'},{})
        with patch('app.services.offers.fetch',return_value='{"offers":[]}'),ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(worker,range(12)))
        self.assertEqual([result[4]['outcome'] for result in results],['no_results' if i%2==0 else 'timeout' for i in range(12)])
    def test_new_failure_message_never_contains_feed_token_or_raw_body(self):
        with patch('app.services.offers.fetch',return_value='secret-fixture-token'):
            result=collect_source('kns',self.payload,time.monotonic()+10,{'kns':'https://feed.example.com/'},{'kns':'secret-fixture-token'})
        self.assertNotIn('secret-fixture-token',result[3]);self.assertEqual(result[4]['outcome'],'parse_error')


    def test_partial_discovery_retains_rows_and_legacy_origin(self):
        from app.schemas.offers import OfferInput
        row=OfferInput(source='kns',name='GeForce RTX 4060 8GB',category='GPU',price_rub=30000,
                       url='https://www.kns.ru/product/fixture/',observed_at=NOW)
        self.payload.method='web'
        with patch('app.services.public_discovery.discover_public_offers',return_value=([row],{'error':'Other search engine failed'})):
            result=collect_source('kns',self.payload,time.monotonic()+10,{}, {})
        self.assertEqual(result[4]['outcome'],'partial')
        self.assertEqual(result[2],'product_page');self.assertEqual(len(result[1]),1)

    def test_one_rate_limited_source_does_not_discard_other_feed(self):
        feed={'offers':[{'source':'kns','category':'GPU','name':'GeForce RTX 4060 8GB','price_rub':30000,
             'url':'https://www.kns.ru/product/fixture/','observed_at':NOW.isoformat()}]}
        self.payload.sources=['kns','dns']
        with patch.object(settings,'offers_feed_urls',json.dumps({'kns':'https://feed.example.com/'})),patch(
                'app.services.offers.fetch',return_value=json.dumps(feed)),patch(
                'app.services.safe_http.SafeSession._once',return_value=self.response(429)):
            result=search_offers(self.db,self.payload)
        self.assertEqual(len(result['offers']),1);self.assertTrue(result['partial_result'])
        self.assertEqual([item['outcome'] for item in result['source_outcomes']],['success','rate_limited'])
        self.assertIsNone(result['offers'][0]['price_verified_at'])

    def test_ambiguous_product_prices_are_parse_error_not_confirmation(self):
        from app.services.source_outcomes import SourceFailure
        url='https://www.kns.ru/product/fixture/'
        product={'@type':'Product','name':'GeForce RTX 4060 8GB','url':url,
                 'offers':[{'price':30000,'url':url},{'price':32000,'url':url}]}
        body='<script type="application/ld+json">'+json.dumps(product)+'</script>'
        with self.assertRaises(SourceFailure) as error:parse_html('kns',body,'GPU',url,require_single_price=True)
        self.assertEqual(error.exception.outcome,'parse_error')

    def test_missing_or_invalid_price_never_becomes_zero(self):
        for value in [None,'unknown',-1,0]:
            with self.subTest(value=value):
                product={'@type':'Product','name':'GeForce RTX 4060 8GB','url':'https://www.kns.ru/product/fixture/',
                         'offers':{'price':value}}
                result=self.run_response(200,'<script type="application/ld+json">'+json.dumps(product)+'</script>')
                self.assertEqual(result[1],[])
                self.assertNotEqual(result[4]['outcome'],'no_results')

    def test_legacy_success_without_typed_evidence_does_not_invent_new_metrics(self):
        from app.services.source_outcomes import public_outcome
        result=public_outcome({'source':'kns','status':'public_page','message':'Old page'},cached=True)
        self.assertEqual(result['outcome'],'not_tested')
        self.assertIsNone(result['result_count'])


    def test_task_cancellation_is_not_converted_to_empty_success(self):
        import asyncio
        with patch('app.services.offers.search_public',side_effect=asyncio.CancelledError()):
            with self.assertRaises(asyncio.CancelledError):
                collect_source('kns',self.payload,time.monotonic()+10,{}, {})

    def test_outcome_time_uses_existing_utc_normalization(self):
        from app.services.source_outcomes import public_outcome
        record={'source':'kns','status':'unavailable','checked_at':'2026-11-09T15:00:00+03:00'}
        self.assertEqual(public_outcome(record,cached=True)['checked_at'],'2026-11-09T12:00:00Z')
        record['checked_at']='invalid'
        self.assertIsNone(public_outcome(record)['checked_at'])

    def test_unknown_runtime_failure_does_not_expose_private_url_or_secret(self):
        failure=RuntimeError('secret-fixture-token https://feed.example.com/?token=secret-fixture-token')
        with patch('app.services.offers.search_public',side_effect=failure):
            result=collect_source('kns',self.payload,time.monotonic()+10,{}, {})
        self.assertNotIn('secret-fixture-token',result[3])
        self.assertNotIn('https://',result[3])

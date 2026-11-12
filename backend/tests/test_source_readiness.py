"""Synthetic fixtures only: adapter contracts, not live availability."""
import json, socket, sys, time, unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import Base, StoreOffer
from app.core.config import settings
from app.core.stores import STORES
from app.schemas.offers import SearchOffers
from app.services.offers import collect_source, search_offers, upsert
from app.services.safe_http import SafeResponse
from requests.structures import CaseInsensitiveDict

PATHS={'ozon':'/product/test-123/','avito':'/moskva/test_123456789','wb':'/catalog/123/detail.aspx',
'yandex':'/product/test/123','dns':'/product/123/test/','citilink':'/product/test-123/',
'regard':'/product/123/test','oldi':'/catalog/element/123/','kns':'/product/test/',
'xcom':'/product/test/','onlinetrade':'/catalogue/test-1/test.html','nix':'/autocatalog/test/test.html'}
CASES=[('CPU','AMD Ryzen 5 5600',10000),('GPU','GeForce RTX 4060 8GB',30000),
('memory','Оперативная память Kingston DDR4 16GB',4000),
('motherboard','Материнская плата MSI B550-A PRO',10000)]
NOW=datetime(2026,11,9,12,tzinfo=timezone.utc)

class SourceReadinessTests(unittest.TestCase):
    def setUp(self):
        from tests.source_grants import grant_network
        grant_network(self)
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.addCleanup(self.engine.dispose); self.addCleanup(self.db.close)
        self.addCleanup(patch.stopall)
        patch('app.core.price_time.utc_now',return_value=NOW).start()
        patch('socket.socket',side_effect=AssertionError('No real network')).start()
        patch('app.services.store_providers._blocked_until',{}).start()

    def test_all_twelve_sources_and_four_categories_through_http_transport(self):
        for source,store in STORES.items():
            for category,name,price in CASES:
                with self.subTest(source=source,category=category):
                    url='https://www.'+store['domain']+PATHS[source]
                    html='<script type="application/ld+json">'+json.dumps({
                        '@type':'Product','name':name,'url':url,
                        'offers':{'price':price,'priceCurrency':'RUB'}})+'</script>'
                    response=SafeResponse(200,CaseInsensitiveDict({'Content-Type':'text/html; charset=utf-8'}),html.encode(),url)
                    payload=SearchOffers(query=name,category=category,sources=[source])
                    with patch.object(settings,'offers_live_search',True),patch(
                        'app.services.store_providers.resolved_search_url',return_value=store['search']),patch(
                        'app.services.safe_http.resolve_public',return_value=()),patch(
                        'app.services.safe_http.SafeSession._once',return_value=response):
                        result=collect_source(source,payload,time.monotonic()+5,{}, {})
                    if source=='avito':
                        self.assertEqual(result[4]['outcome'],'access_not_permitted')
                        self.assertFalse(result[4]['attempted']);self.assertEqual(result[1],[])
                        continue
                    self.assertEqual(result[2],'public_page',result[3])
                    self.assertEqual([(r.name,r.price_rub,r.category) for r in result[1]],[(name,price,category)])
                    upsert(self.db,result[1],result[2])
                    self.db.query(StoreOffer).delete();self.db.commit()

    def test_declared_single_byte_encoding_is_respected(self):
        text='Carte graphique café'
        response=SafeResponse(200,CaseInsensitiveDict({'Content-Type':'text/html; charset=iso-8859-1'}),text.encode('iso-8859-1'),'https://www.kns.ru/')
        self.assertEqual(response.text,text)

    def test_blocked_source_is_not_empty_success(self):
        payload=SearchOffers(query='Ryzen 5 5600',category='CPU',sources=['kns'])
        with patch.object(settings,'offers_live_search',True),patch(
            'app.services.offers.search_public',side_effect=RuntimeError('HTTP 403')):
            result=collect_source('kns',payload,time.monotonic()+5,{}, {})
        self.assertEqual(result[2],'unavailable');self.assertIn('403',result[3])

    def test_disabled_browser_has_explicit_reason_for_each_source(self):
        for source in STORES:
            with self.subTest(source=source):
                payload=SearchOffers(query='Ryzen 5 5600',category='CPU',sources=[source],method='browser')
                result=collect_source(source,payload,time.monotonic()+5,{}, {})
                if source=='avito':
                    self.assertEqual(result[4]['outcome'],'access_not_permitted');self.assertFalse(result[4]['attempted'])
                else:
                    self.assertEqual(result[2],'unavailable');self.assertIn('изоляц',result[3])

    def test_cached_outage_reports_cache_and_partial_result_without_new_confirmation(self):
        url='https://www.kns.ru/product/test/'
        from app.schemas.offers import OfferInput
        upsert(self.db,[OfferInput(source='kns',category='CPU',name='AMD Ryzen 5 5600',
            price_rub=10000,url=url,observed_at=NOW)],'public_page')
        payload=SearchOffers(query='Ryzen 5 5600',category='CPU',sources=['kns','dns'])
        with patch('app.services.offers.collect_source',side_effect=lambda source,*args:
                   (source,[],'unavailable','HTTP 403',{})) as collect:
            first=search_offers(self.db,payload)
            second=search_offers(self.db,payload)
        self.assertEqual(collect.call_count,2)
        self.assertFalse(first['search_cached']);self.assertTrue(second['search_cached'])
        self.assertTrue(second['partial_result']);self.assertEqual(second['unavailable_sources'],['kns','dns'])
        self.assertIsNone(second['offers'][0]['price_verified_at'])
        self.assertIn('наблюдения',second['note'])

    def test_search_rejects_nearby_gpu_variant(self):
        from app.schemas.offers import OfferInput
        rows=[OfferInput(source='kns',category='GPU',name=name,price_rub=30000+i*1000,
              url='https://www.kns.ru/product/fixture-'+str(i)+'/',observed_at=NOW)
              for i,name in enumerate(['GeForce RTX 4060 8GB','GeForce RTX 4060 Ti 8GB'])]
        upsert(self.db,rows,'public_page')
        payload=SearchOffers(query='RTX 4060',category='GPU',sources=['kns'])
        with patch('app.services.offers.collect_source',return_value=('kns',[],'disabled','off',{})):
            result=search_offers(self.db,payload)
        self.assertEqual([r['name'] for r in result['offers']],['GeForce RTX 4060 8GB'])

    def test_authorized_feed_still_works_without_browser_or_live_search(self):
        source='regard'; category,name,price=CASES[0]
        feed={'offers':[{'source':source,'category':category,'name':name,'price_rub':price,
            'url':'https://www.regard.ru/product/123/test','observed_at':NOW.isoformat()}]}
        payload=SearchOffers(query=name,category=category,sources=[source])
        with patch.object(settings,'offers_live_search',False),patch(
            'app.services.offers.fetch',return_value=json.dumps(feed)) as fetch:
            result=collect_source(source,payload,time.monotonic()+5,
                {source:'https://feed.example.com/catalog'},{source:'fixture-only'})
        self.assertEqual(result[2],'feed');self.assertEqual(len(result[1]),1)
        self.assertEqual(fetch.call_args.args[2],'fixture-only')

    def test_browser_import_returns_specific_service_unavailable_without_transport(self):
        from app.api.offers import from_url
        from app.schemas.offers import OfferLink
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:
            from_url(OfferLink(source='kns',category='CPU',
                url='https://www.kns.ru/product/test/',method='browser'),self.db,object())
        self.assertEqual(error.exception.status_code,503)
        self.assertIn('изоляц',error.exception.detail)

    def test_status_does_not_assert_live_availability(self):
        from app.api.offers import status
        with patch('app.services.browser_offers.browser_diagnostics',return_value={'enabled':False}):
            result=status(self.db)
        self.assertEqual(len(result['sources']),13)
        self.assertTrue(all(item['live_status']=='not_checked' and not item['browser_enabled']
                            for item in result['sources']))

if __name__=='__main__':unittest.main()

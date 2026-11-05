"""Outages should preserve an honest draft and respect one network deadline."""
import sys,json,time,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_adaptive_builds
from app.db.models import StoreOffer
from app.schemas.offers import SearchOffers
from app.services.builds import BuildRequest,assemble
from app.services.assembly_draft import draft_build
from app.services.price_verification import verify_build_prices
from app.services.search_time import request_timeout
from app.services.store_providers import fetch
from app.core.config import settings
from sqlalchemy import select,delete


class SearchOutageTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_adaptive_builds.AdaptiveBuildTests();self.fixture.setUp()
        self.db=self.fixture.db;self.payload=self.fixture.payload
        for row in self.db.scalars(select(StoreOffer)):
            row.origin='public_page'
            row.attributes=json.dumps({'price_verification':{'status':'unavailable','checked_at':datetime.utcnow().isoformat(),
                                                           'message':'HTTP 429'}})
        self.db.commit()

    def tearDown(self):self.fixture.tearDown()

    def test_full_observed_pc_survives_store_failures_and_is_not_called_verified(self):
        with patch('app.services.builds.search_offers',side_effect=RuntimeError('403')),patch.object(settings,'offers_browser_enabled',False):
            result=assemble(BuildRequest(**self.payload),self.db)
        self.assertEqual(result['status'],'draft')
        self.assertFalse(result['purchase_ready'])
        self.assertEqual(len(result['parts']),8)
        self.assertLessEqual(result['total_price'],self.payload['budget'])
        self.assertTrue(all(part['price_status']=='unconfirmed' and part['price_verified_at'] is None for part in result['parts']))
        self.assertTrue(result['price_note'])
        self.assertEqual(result['search_report']['result_mode'],'draft')

    def test_an_old_successful_page_check_remains_labelled_as_historical(self):
        checked=(datetime.utcnow()-timedelta(minutes=20)).isoformat()
        for row in self.db.scalars(select(StoreOffer)):
            row.origin='product_page'
            row.attributes=json.dumps({'price_verification':{'status':'verified','checked_at':checked}})
        self.db.commit()
        result=draft_build(BuildRequest(**self.payload),self.db,'avito')
        self.assertIsNotNone(result)
        self.assertTrue(all(part['price_status']=='previously_verified' for part in result['parts']))
        self.assertTrue(all(part['price_last_verified_at']==checked+'Z' for part in result['parts']))

    def test_deadline_does_not_start_http_or_mark_unread_products_unavailable(self):
        with patch('app.services.store_providers.requests.get') as request:
            with self.assertRaises(TimeoutError):fetch('https://www.regard.ru/product/123/test',store='regard',deadline=time.monotonic()-1)
            request.assert_not_called()
        row=self.db.scalar(select(StoreOffer))
        row.attributes='{}';self.db.commit()
        with patch('app.services.price_verification.fetch') as request:
            verify_build_prices(self.db,{'parts':[{'offer_id':row.id}]},deadline=time.monotonic()-1)
            request.assert_not_called()
        self.assertEqual(json.loads(row.attributes),{})

    def test_deadline_is_internal_and_every_auto_search_receives_it(self):
        deadlines=[]
        def search(db,payload):
            deadlines.append(payload._deadline)
            self.assertNotIn('_deadline',payload.model_dump())
            return {}
        with patch('app.services.builds.search_offers',side_effect=search),patch.object(settings,'offers_browser_enabled',False):
            assemble(BuildRequest(**self.payload),self.db)
        self.assertTrue(deadlines)
        self.assertTrue(all(deadline is not None for deadline in deadlines))
        self.assertLessEqual(max(deadlines)-min(deadlines),45)

    def test_zero_observations_does_not_invent_a_configuration(self):
        self.db.execute(delete(StoreOffer));self.db.commit()
        with patch('app.services.builds.search_offers',return_value={}),patch.object(settings,'offers_browser_enabled',False):
            result=assemble(BuildRequest(**self.payload),self.db)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['parts'],[])
        self.assertNotIn('total_price',result)

    def test_partial_result_keeps_ryzen_without_an_incompatible_intel_board(self):
        self.db.execute(delete(StoreOffer).where(StoreOffer.category.in_(['motherboard','storage'])))
        self.db.add(StoreOffer(source='oldi',category='motherboard',name='Материнская плата MSI PRO H610M-E DDR4',
            price_rub=4780,url='https://www.oldi.ru/catalog/element/123456/',hardware_id=None,
            condition='new',observed_at=datetime.utcnow(),origin='public_page',attributes='{}'))
        self.db.commit()
        with patch('app.services.builds.search_offers',return_value={}),patch.object(settings,'offers_browser_enabled',False):
            result=assemble(BuildRequest(**{**self.payload,'price_sources':['avito','oldi']}),self.db)
        self.assertEqual(result['status'],'partial')
        self.assertTrue(any(part['type']=='CPU' for part in result['parts']))
        self.assertFalse(any(part['type']=='motherboard' for part in result['parts']))

    def test_old_known_cooler_price_is_preferred_to_a_dubious_search_price(self):
        row=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='cooler'))
        row.source='yandex';row.price_rub=846;row.url='https://market.yandex.ru/card/cooler/99000'
        self.db.add(StoreOffer(source='oldi',category='cooler',name='DeepCool AG400',price_rub=1420,
            condition='new',observed_at=datetime.utcnow(),origin='product_page',
            attributes=json.dumps({'price_verification':{'status':'verified','checked_at':(datetime.utcnow()-timedelta(minutes=20)).isoformat()}}),
            url='https://www.oldi.ru/catalog/element/99001/'))
        self.db.commit()
        result=draft_build(BuildRequest(**{**self.payload,'price_sources':['avito','oldi','yandex']}),self.db,'avito')
        self.assertIsNotNone(result)
        cooler=next(part for part in result['parts'] if part['type']=='cooler')
        self.assertEqual(cooler['price'],1420)
        self.assertEqual(cooler['price_status'],'previously_verified')


if __name__=='__main__':unittest.main()

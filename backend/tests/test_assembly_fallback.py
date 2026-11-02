"""Store outages must not discard a ready PC or terminate replacement search."""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select, delete
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_automatic_policy
from app.core.config import settings
from app.db.models import StoreOffer
from app.services.builds import assemble, BuildRequest


class AssemblyFallbackTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_automatic_policy.AutomaticPolicyTests()
        self.fixture.setUp()
        self.db=self.fixture.db
        self.payload=self.fixture.payload

    def tearDown(self):
        self.fixture.tearDown()

    def test_selected_shop_can_fall_back_to_another_shop_without_restarting(self):
        payload=BuildRequest(**{**self.payload,'price_sources':['yandex']})
        with patch('app.services.builds.search_offers',return_value={}), patch.object(settings,'offers_browser_enabled',False):
            result=assemble(payload,self.db)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(len(result['parts']),8)
        self.assertIn('regard',result['search_report']['additional_sources'])
        self.assertTrue(any(part['price_source']=='Регард' for part in result['parts']))
        self.assertLessEqual(result['total_price'],payload.budget)

    def test_failed_product_is_replaced_from_another_store(self):
        for row in self.db.scalars(select(StoreOffer)):
            row.source='yandex'
            row.url=f'https://market.yandex.ru/card/fixture/{row.id}'
        coolers=list(self.db.scalars(select(StoreOffer).where(StoreOffer.category=='cooler')))
        for row in coolers:
            if row is not coolers[0]: self.db.delete(row)
        coolers[0].origin='public_page'
        self.db.commit()
        def search(db,request):
            if request.category=='cooler' and 'regard' in request.sources:
                db.add(StoreOffer(source='regard',category='cooler',name='DeepCool AG400',price_rub=1500,
                    condition='new',attributes='{}',observed_at=datetime.utcnow(),origin='feed',
                    url='https://www.regard.ru/product/9999/replacement'))
                db.commit()
            return {}
        payload=BuildRequest(**{**self.payload,'price_sources':['yandex']})
        with patch('app.services.builds.search_offers',side_effect=search), patch(
                'app.services.price_verification.fetch',side_effect=RuntimeError('403')) as fetch, patch.object(settings,'offers_browser_enabled',False):
            result=assemble(payload,self.db)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(fetch.call_count,1)
        cooler=next(part for part in result['parts'] if part['type']=='cooler')
        self.assertEqual(cooler['price_source'],'Регард')
        self.assertEqual(cooler['price'],1500)
        self.assertEqual(result['search_report']['rejected_offers'],1)

    def test_unverified_alternatives_cannot_block_a_confirmed_build(self):
        self.db.add(StoreOffer(source='regard',category='cooler',name='DeepCool AG400',price_rub=300,
            condition='new',attributes='{}',observed_at=datetime.utcnow(),origin='public_page',
            url='https://www.regard.ru/product/9999/unconfirmed'))
        self.db.commit()
        with patch('app.services.builds.search_offers',return_value={}), patch('app.services.price_verification.fetch') as fetch:
            result=assemble(BuildRequest(**self.payload),self.db)
        self.assertEqual(result['status'],'complete')
        fetch.assert_not_called()
        self.assertTrue(all(part['price']!=300 for part in result['parts']))

    def test_more_than_five_failed_candidates_do_not_end_the_search(self):
        self.db.execute(delete(StoreOffer).where(StoreOffer.category=='cooler'))
        for index in range(8):
            self.db.add(StoreOffer(source='regard',category='cooler',name='DeepCool AG400',price_rub=500+index*100,
                condition='new',attributes='{}',observed_at=datetime.utcnow(),origin='public_page',
                url=f'https://www.regard.ru/product/{9000+index}/cooler'))
        self.db.commit()
        def fetch(url,**kwargs):
            if '/9007/' not in url: raise RuntimeError('Unavailable product')
            product={'@type':'Product','name':'DeepCool AG400','url':url,'offers':{'price':1752,'priceCurrency':'RUB'}}
            return '<script type="application/ld+json">'+json.dumps(product)+'</script>'
        with patch('app.services.builds.search_offers',return_value={}), patch(
                'app.services.price_verification.fetch',side_effect=fetch) as reader, patch.object(settings,'offers_browser_enabled',False):
            result=assemble(BuildRequest(**self.payload),self.db)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(reader.call_count,8)
        self.assertEqual(next(part for part in result['parts'] if part['type']=='cooler')['price'],1752)

    def test_no_stores_answer_returns_a_useful_partial_result(self):
        self.db.execute(delete(StoreOffer));self.db.commit()
        with patch('app.services.builds.search_offers',side_effect=RuntimeError('offline')), patch.object(settings,'offers_browser_enabled',False):
            result=assemble(BuildRequest(**self.payload),self.db)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(len(result['missing_parts']),8)
        self.assertTrue(result['missing_parts'][0]['links'])
        self.assertNotIn('total_price',result)
        self.assertNotIn('fps',result)

    def test_optional_store_restriction_is_respected(self):
        payload=BuildRequest(**{**self.payload,'price_sources':['dns'],'allow_store_fallback':False})
        with patch('app.services.builds.search_offers',return_value={}) as search, patch.object(settings,'offers_browser_enabled',False):
            result=assemble(payload,self.db)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['search_report']['additional_sources'],[])
        self.assertTrue(all(call.args[1].sources==['dns'] for call in search.call_args_list))


if __name__=='__main__':unittest.main()

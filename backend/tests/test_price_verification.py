import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db.base import Base
from app.db.models import StoreOffer
from app.schemas.offers import OfferInput
from app.services.offers import available_offers, upsert
from app.services.price_verification import verify_build_prices
from app.services.store_providers import parse_html


class QuoteVerificationTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.url='https://market.yandex.ru/card/id-cooling-se-214-xt/123456'
        self.db.add(StoreOffer(id=1,source='yandex',name='ID-COOLING SE-214-XT',category='cooler',price_rub=846,
                               url=self.url,condition='new',observed_at=datetime.utcnow(),origin='public_page',attributes='{}'))
        self.db.commit()
        self.result={'alternatives':[{'parts':[{'offer_id':1}]}]}

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def markup(self,price):
        return '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'ID-COOLING SE-214-XT',
            'url':self.url,'offers':{'price':price,'priceCurrency':'RUB','url':self.url}})+'</script>'

    def test_product_price_replaces_snippet_and_a_search_cannot_revert_it(self):
        with patch('app.services.price_verification.fetch',return_value=self.markup(1752)) as fetch:
            self.assertTrue(verify_build_prices(self.db,self.result))
            self.assertFalse(verify_build_prices(self.db,self.result))
            self.assertEqual(fetch.call_count,1)
        self.assertEqual(self.db.get(StoreOffer,1).price_rub,1752)
        stale=OfferInput(source='yandex',name='ID-COOLING SE-214-XT',category='cooler',price_rub=846,
                         url=self.url,observed_at=datetime.utcnow())
        upsert(self.db,[stale],'public_page')
        self.assertEqual(self.db.get(StoreOffer,1).price_rub,1752)

    def test_inaccessible_product_is_not_left_in_the_automatic_price_pool(self):
        with patch('app.services.price_verification.fetch',side_effect=RuntimeError('403')):
            self.assertTrue(verify_build_prices(self.db,self.result))
        self.assertEqual(available_offers(self.db,['yandex'],'cooler'),[])
        self.assertEqual(self.db.get(StoreOffer,1).price_rub,846) # Retain evidence, exclude it from selection.

    def test_multiple_prices_for_one_url_are_not_treated_as_a_confirmed_purchase_price(self):
        html=self.markup(846)+self.markup(1752)
        with self.assertRaises(RuntimeError):
            parse_html('yandex',html,'cooler',self.url,require_single_price=True)

    def test_product_schema_without_url_is_bound_to_the_page_only_when_the_title_matches(self):
        product={'@type':'Product','name':'ID-COOLING SE-214-XT','offers':{'price':1752,'priceCurrency':'RUB'}}
        markup='<h1>ID-COOLING SE-214-XT</h1><script type="application/ld+json">'+json.dumps(product)+'</script>'
        rows=parse_html('yandex',markup,'cooler',self.url,require_single_price=True)
        self.assertEqual(rows[0].price_rub,1752)
        with self.assertRaises(RuntimeError):
            parse_html('yandex',markup.replace('<h1>ID-COOLING SE-214-XT</h1>','<h1>Other related cooler</h1>'),
                       'cooler',self.url,require_single_price=True)

    def test_a_successful_product_read_can_replace_a_recent_access_failure(self):
        with patch('app.services.price_verification.fetch',side_effect=RuntimeError('403')):
            verify_build_prices(self.db,self.result)
        checked = OfferInput(source='yandex',name='ID-COOLING SE-214-XT',category='cooler',price_rub=1752,
                             url=self.url,observed_at=datetime.utcnow(),attributes={'price_verification':{
                                 'status':'verified','checked_at':datetime.utcnow().isoformat(),'method':'browser_product_page'}})
        upsert(self.db,[checked],'browser_page')
        self.assertEqual(available_offers(self.db,['yandex'],'cooler')[0].price_rub,1752)
        with patch('app.services.price_verification.fetch') as fetch:
            self.assertFalse(verify_build_prices(self.db,self.result))
            fetch.assert_not_called()

    def test_avito_verification_can_use_a_readable_browser_page_after_http_fails(self):
        row=self.db.get(StoreOffer,1);row.source='avito'
        row.url='https://www.avito.ru/moskva/tovary_dlya_kompyutera/cooler_123456789'
        self.db.commit()
        candidate=OfferInput(source='avito',category='cooler',name='Новый ID-COOLING SE-214-XT',
            price_rub=1752,url=row.url,condition='new',observed_at=datetime.utcnow(),
            attributes={'price_verification':{'status':'verified','checked_at':datetime.utcnow().isoformat(),
                                              'method':'browser_product_page'}})
        with patch('app.services.price_verification.fetch',side_effect=RuntimeError('403')),patch(
                'app.services.browser_offers.read_browser_product',return_value=[candidate]) as browser:
            self.assertTrue(verify_build_prices(self.db,self.result,browser_sources={'avito'}))
        self.assertEqual(browser.call_count,1)
        self.assertEqual(self.db.get(StoreOffer,1).price_rub,1752)
        self.assertEqual(len(available_offers(self.db,['avito'],'cooler')),1)


if __name__=='__main__':unittest.main()

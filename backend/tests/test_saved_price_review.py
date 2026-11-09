"""Historical snapshots never become current quotes merely by reopening."""
import json, sys, unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import Response, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import Base, SavedBuild, StoreOffer, User
from app.api.account import builds
NOW=datetime(2026,11,9,12,tzinfo=timezone.utc)

class SavedPriceReviewTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine); self.db=Session(self.engine)
        self.addCleanup(self.engine.dispose);self.addCleanup(self.db.close)
        clock=patch('app.core.price_time.utc_now',return_value=NOW);self.clock=clock.start();self.addCleanup(clock.stop)
        self.user=User(id=1,email='saved@example.test',name='Fixture',password_hash='fixture-only')
        self.row=StoreOffer(id=1,source='kns',category='CPU',name='AMD Ryzen 5 5600',price_rub=10000,
            url='https://www.kns.ru/product/test/',condition='new',origin='product_page',
            observed_at=NOW.replace(tzinfo=None),
            attributes=json.dumps({'price_verification':{'status':'verified','checked_at':NOW.isoformat()}}))
        result={'status':'complete','total_price':10000,'parts':[{'type':'CPU','name':self.row.name,
            'price':10000,'offer_id':1,'price_url':self.row.url,'price_date':NOW.isoformat(),
            'price_verified_at':NOW.isoformat()}]}
        self.saved=SavedBuild(id=1,user_id=1,created_at=NOW.replace(tzinfo=None),
            data=json.dumps({'config':{'scenario':'build'},'result':result}))
        self.db.add_all([self.user,self.row,self.saved]);self.db.commit()
        self.original=self.saved.data

    def review(self):
        output=builds(self.db,self.user,Response())[0]
        self.assertEqual(self.saved.data,self.original)
        self.assertEqual(output['result'],json.loads(self.original)['result'])
        return output['price_review']

    def age(self,**delta):
        self.clock.return_value=NOW+timedelta(**delta)

    def test_just_saved_separates_history_and_confirmed_total(self):
        review=self.review()
        self.assertEqual(review['historical_total'],10000)
        self.assertEqual(review['current_total'],10000)
        self.assertEqual(review['items'][0]['latest_price'],10000)

    def test_exact_fifteen_minute_boundary_is_not_current(self):
        self.age(minutes=15)
        self.assertIsNone(self.review()['current_total'])

    def test_older_than_twenty_four_hours_keeps_historical_cost(self):
        self.age(hours=25);review=self.review()
        self.assertEqual(review['historical_total'],10000)
        self.assertIsNone(review['current_total'])
        self.assertEqual(review['items'][0]['latest_price'],10000)

    def test_unavailable_shop_preserves_history_and_last_observation(self):
        self.row.attributes=json.dumps({'price_verification':{'status':'unavailable','checked_at':NOW.isoformat()}})
        self.db.commit();review=self.review()
        self.assertIsNone(review['current_total'])
        self.assertEqual(review['items'][0]['latest_price'],10000)

    def test_changed_price_does_not_rewrite_saved_total(self):
        self.row.price_rub=12000;self.db.commit();review=self.review()
        self.assertEqual(review['historical_total'],10000)
        self.assertEqual(review['current_total'],12000)
        self.assertTrue(review['items'][0]['changed'])

    def test_deleted_offer_does_not_make_empty_set_confirmed(self):
        self.db.delete(self.row);self.db.commit()
        self.assertIsNone(self.review()['current_total'])
        self.assertEqual(self.review()['items'][0]['state'],'missing')

    def test_manual_component_remains_user_estimate(self):
        data=json.loads(self.saved.data);data['result']['parts'][0].pop('offer_id')
        data['result']['parts'][0].pop('price_url')
        data['result']['parts'][0].pop('price_date')
        data['result']['parts'][0].pop('price_verified_at')
        self.saved.data=json.dumps(data);self.db.commit();self.original=self.saved.data
        self.assertIsNone(self.review()['current_total'])
        self.assertEqual(self.review()['items'][0]['state'],'manual')

    def test_zero_user_cost_is_not_repriced(self):
        data=json.loads(self.saved.data);part=data['result']['parts'][0]
        part.pop('offer_id');part.pop('price_url');part['price']=0
        data['result']['total_price']=0
        self.saved.data=json.dumps(data);self.db.commit();self.original=self.saved.data
        review=self.review()
        self.assertEqual(review['items'][0]['state'],'user_zero_cost')
        self.assertEqual(review['current_total'],0)

    def test_legacy_record_without_parts_has_unknown_current_price(self):
        self.saved.data=json.dumps({'config':{},'result':{'avg_price':5000}})
        self.db.commit();self.original=self.saved.data
        self.assertEqual(self.review()['historical_total'],5000)
        self.assertIsNone(self.review()['current_total'])

    def test_upgrade_uses_purchase_quote_not_sale_estimate(self):
        self.saved.data=json.dumps({'config':{},'result':{'avg_price':10000,'current_component_price':3000,
            'upgrade_name':self.row.name,'upgrade_price':{'offer_id':1,'avg_price':10000,
                'price_url':self.row.url,'price_date':NOW.isoformat()}}})
        self.db.commit();self.original=self.saved.data
        self.assertEqual(self.review()['current_total'],10000)

    def test_reopening_and_reload_recalculate_without_touching_snapshot(self):
        self.assertEqual(self.review()['current_total'],10000)
        self.age(minutes=16)
        self.assertIsNone(self.review()['current_total'])
        self.assertIsNone(self.review()['current_total'])

    def test_reused_offer_id_with_different_product_is_not_current(self):
        self.row.url='https://www.kns.ru/product/other/';self.db.commit()
        self.assertIsNone(self.review()['current_total'])

    def test_owner_only_local_recheck_never_fetches_shop(self):
        from app.api.account import check_saved_prices
        with patch('app.services.store_providers.fetch',side_effect=AssertionError('No network')):
            result=check_saved_prices(1,self.db,self.user,Response())
        self.assertEqual(result['price_review']['check_method'],'local_observations')
        with self.assertRaises(HTTPException) as error:
            check_saved_prices(1,self.db,User(id=99),Response())
        self.assertEqual(error.exception.status_code,404)


    def test_feed_unavailable_never_confirms_even_when_observation_is_recent(self):
        self.row.origin='feed'
        self.row.attributes=json.dumps({'price_verification':{'status':'unavailable','checked_at':NOW.isoformat()}})
        self.db.commit()
        self.assertIsNone(self.review()['current_total'])

    def test_reused_url_for_another_cpu_is_not_the_saved_model(self):
        self.row.name='AMD Ryzen 7 5700X';self.db.commit()
        self.assertIsNone(self.review()['current_total'])

    def test_feed_keeps_existing_observation_ttl(self):
        self.row.origin='feed';self.row.attributes='{}';self.db.commit()
        self.age(hours=24)
        self.assertEqual(self.review()['current_total'],10000)
        self.age(hours=24,seconds=1)
        self.assertIsNone(self.review()['current_total'])

    def test_new_save_captures_evidence_and_does_not_mutate_it_on_reload(self):
        from app.services.saved_prices import capture_snapshot
        data=json.loads(self.saved.data)
        data['price_snapshot']=capture_snapshot(self.db,data['result'])
        self.saved.data=json.dumps(data);self.db.commit();self.original=self.saved.data
        self.row.price_rub=12000;self.db.commit()
        review=self.review()
        self.assertEqual(review['items'][0]['historical_price'],10000)
        self.assertEqual(review['items'][0]['latest_price'],12000)
        self.assertEqual(json.loads(self.saved.data)['price_snapshot'],data['price_snapshot'])

    def test_partial_price_coverage_does_not_confirm_whole_saved_total(self):
        data=json.loads(self.saved.data);data['result']['total_price']=20000
        self.saved.data=json.dumps(data);self.db.commit();self.original=self.saved.data
        self.assertIsNone(self.review()['current_total'])

    def test_owned_zero_cost_and_missing_purchase_offer_keep_history(self):
        data=json.loads(self.saved.data)
        data['result']['parts'].append({'type':'case','name':'Свой корпус','price':0})
        self.saved.data=json.dumps(data);self.db.commit();self.original=self.saved.data
        self.assertEqual(self.review()['current_total'],10000)
        self.db.delete(self.row);self.db.commit()
        review=self.review()
        self.assertIsNone(review['current_total'])
        self.assertEqual(review['items'][1]['confirmed_price'],0)


    def test_save_api_adds_evidence_without_changing_result(self):
        from app.api.account import save_build
        from app.services.builds import BuildRequest
        result=json.loads(self.original)['result']
        payload=BuildRequest(scenario='build',budget=20000,game='CS2',mode='1080p_low',
            socket='AM4',ram_type='DDR4',ram_capacity_gb=16,auto_parts=True)
        with patch('app.api.account.assemble',return_value=result):
            output=save_build(payload,self.db,self.user)
        saved=self.db.get(SavedBuild,output['id'])
        data=json.loads(saved.data)
        self.assertEqual(data['result'],result)
        self.assertEqual(data['price_snapshot']['version'],1)
        self.assertEqual(data['price_snapshot']['items'][0]['historical_price'],10000)
        before=saved.data
        self.age(minutes=16)
        from app.api.account import check_saved_prices
        checked=check_saved_prices(saved.id,self.db,self.user,Response())
        self.assertIsNone(checked['price_review']['current_total'])
        self.assertEqual(saved.data,before)

    def test_invalid_or_future_confirmation_does_not_confirm_saved_price(self):
        for value in (None,'invalid','2026-11-09T12:00:01Z'):
            with self.subTest(value=value):
                self.row.attributes=json.dumps({'price_verification':{'status':'verified','checked_at':value}})
                self.db.commit()
                self.assertIsNone(self.review()['current_total'])

    def test_deleted_offer_retains_last_known_snapshot_observation(self):
        self.db.delete(self.row);self.db.commit()
        item=self.review()['items'][0]
        self.assertEqual(item['latest_price'],10000)
        self.assertEqual(item['latest_observed_at'],'2026-11-09T12:00:00Z')
        self.assertIsNone(item['confirmed_price'])


    def test_corrupt_offer_metadata_does_not_break_saved_history(self):
        self.row.attributes='not-json';self.db.commit()
        review=self.review()
        self.assertEqual(review['historical_total'],10000)
        self.assertIsNone(review['current_total'])

    def test_bad_verification_metadata_is_not_confirmation(self):
        self.row.attributes=json.dumps({'price_verification':None});self.db.commit()
        self.assertIsNone(self.review()['current_total'])

if __name__=='__main__':unittest.main()




"""Offline regressions for price timestamps, cache age and build state."""
import json
import sys
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.models import Hardware, HardwarePrice, OfferSearch, SavedBuild, StoreOffer, User
from app.schemas.offers import OfferInput, SearchOffers
from app.services import offers, prices
from app.services.assembly_draft import quote_evidence
from app.services.assembly_search import confirmed
from app.services.price_verification import recent_check, pending_build_prices, verify_build_prices

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
NAIVE = NOW.replace(tzinfo=None)

class ClockFixture:

    def setUp(self):
        self.cleanup = ExitStack()
        self.addCleanup(self.cleanup.close)
        self.cleanup.enter_context(patch('app.core.price_time.utc_now', return_value=NOW))


class PriceTimeTests(ClockFixture, unittest.TestCase):
    def check(self, value):
        return recent_check({'checked_at': value})

    def test_current_z_is_recent(self):
        self.assertTrue(self.check('2026-11-09T11:59:00Z'))

    def test_offset_is_converted_to_utc(self):
        self.assertTrue(self.check('2026-11-09T14:59:00+03:00'))

    def test_expired_check_is_not_recent(self):
        self.assertFalse(self.check('2026-11-09T11:44:59Z'))

    def test_future_check_is_not_recent(self):
        self.assertFalse(self.check('2026-11-10T12:00:00'))

    def test_even_small_future_confirmation_is_not_recent(self):
        self.assertFalse(self.check('2026-11-09T12:00:01'))

    def test_exact_verification_ttl_is_expired(self):
        self.assertFalse(self.check('2026-11-09T11:45:00'))

    def test_missing_check_is_not_recent(self):
        self.assertFalse(recent_check({}))
        self.assertFalse(recent_check(None))

    def test_invalid_check_is_not_recent(self):
        for value in ('bad', '', None, 1234, '2026-11-09', '99999-01-01T00:00:00Z'):
            with self.subTest(value=value):
                self.assertFalse(self.check(value))

    def test_legacy_naive_check_is_utc(self):
        self.assertTrue(self.check('2026-11-09T11:59:00'))

    def test_datetime_metadata_is_accepted(self):
        self.assertTrue(self.check(NOW - timedelta(minutes=1)))

    def offer(self, checked, observed=NAIVE, origin='product_page'):
        return SimpleNamespace(id=1,source='regard',name='DeepCool AG400',category='cooler',
                               price_rub=1000,url='https://www.regard.ru/product/1/test',condition='new',
                               observed_at=observed,origin=origin,hardware_id=None,
                               attributes=json.dumps({'price_verification':{'status':'verified','checked_at':checked}}))

    def test_public_offer_emits_one_z(self):
        value=offers.public_offer(self.offer('2026-11-09T11:59:00Z'))['price_verified_at']
        self.assertEqual(value, '2026-11-09T11:59:00Z')

    def test_public_offer_normalizes_offset(self):
        value=offers.public_offer(self.offer('2026-11-09T14:59:00+03:00'))['price_verified_at']
        self.assertEqual(value, '2026-11-09T11:59:00Z')

    def test_expired_or_future_check_is_not_exposed_as_current(self):
        for value in ('2026-11-09T11:40:00', '2026-11-10T12:00:00', 'bad', None):
            with self.subTest(value=value):
                self.assertIsNone(offers.public_offer(self.offer(value))['price_verified_at'])

    def test_observation_offset_is_converted_not_relabelled(self):
        row=self.offer(None, NOW.astimezone(timezone(timedelta(hours=3))))
        self.assertEqual(offers.public_offer(row)['observed_at'], NOW)
        self.assertTrue(offers.fresh(row))

    def test_observation_ttl_and_existing_five_minute_skew(self):
        for offset, expected in [(timedelta(hours=-24),True),
                                 (timedelta(hours=-24,microseconds=-1),False),
                                 (timedelta(minutes=5),True),
                                 (timedelta(minutes=5,microseconds=1),False)]:
            with self.subTest(offset=offset):
                self.assertEqual(offers.fresh(self.offer(None,NAIVE+offset)),expected)

    def test_draft_history_normalizes_offset_without_current_confirmation(self):
        evidence=quote_evidence(self.offer('2026-11-09T14:40:00+03:00'))
        self.assertEqual(evidence['price_last_verified_at'],'2026-11-09T11:40:00Z')
        self.assertIsNone(evidence['price_verified_at'])

    def test_invalid_history_is_not_promoted_to_historical_verification(self):
        for value in ('bad','2026-11-10T12:00:00'):
            with self.subTest(value=value):
                evidence=quote_evidence(self.offer(value))
                self.assertEqual(evidence['price_status'],'unconfirmed')
                self.assertIsNone(evidence['price_last_verified_at'])

    def test_feed_confirmation_requires_fresh_observation(self):
        self.assertFalse(confirmed(self.offer(None,NAIVE-timedelta(hours=25),origin='feed')))
        self.assertFalse(confirmed(self.offer(None,NAIVE+timedelta(minutes=6),origin='feed')))


class StoredPriceTimeTests(ClockFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.db.add(Hardware(id=1,type='CPU',name='AMD Ryzen 5 5600',socket='AM4',raw_score=21000,normalized_score=50))
        self.db.commit()

    def add(self, checked='2026-11-09T11:40:00', observed=NAIVE):
        row=StoreOffer(id=1,source='regard',name='DeepCool AG400',category='cooler',price_rub=1000,
                       url='https://www.regard.ru/product/1/test',condition='new',observed_at=observed,
                       origin='product_page',attributes=json.dumps({'price_verification':{'status':'verified','checked_at':checked}}))
        self.db.add(row);self.db.commit()
        return row

    def test_new_observation_or_search_cache_does_not_refresh_old_confirmation(self):
        row=self.add()
        self.db.add(OfferSearch(key='fixture',checked_at=NAIVE,statuses='[]'));self.db.commit()
        self.assertFalse(confirmed(row))
        self.assertEqual([x.id for x in pending_build_prices(self.db,{'parts':[{'offer_id':1}]})],[1])
        self.assertIsNone(offers.public_offer(row)['price_verified_at'])

    def test_changed_price_is_rechecked_and_replaces_old_amount(self):
        row=self.add()
        html='<script type="application/ld+json">'+json.dumps({'@type':'Product','name':row.name,'url':row.url,'offers':{'price':1752,'priceCurrency':'RUB'}})+'</script>'
        with patch('app.services.price_verification.fetch',return_value=html) as fetch:
            self.assertTrue(verify_build_prices(self.db,{'parts':[{'offer_id':1}]}))
            self.assertFalse(verify_build_prices(self.db,{'parts':[{'offer_id':1}]}))
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(row.price_rub,1752)
        self.assertTrue(confirmed(row))
        checked=json.loads(row.attributes)['price_verification']['checked_at']
        self.assertEqual(datetime.fromisoformat(checked.replace('Z','+00:00')).replace(tzinfo=None),NAIVE)

    def test_unavailable_store_keeps_evidence_without_confirmation(self):
        row=self.add()
        with patch('app.services.price_verification.fetch',side_effect=RuntimeError('offline fixture')):
            verify_build_prices(self.db,{'parts':[{'offer_id':1}]})
        self.assertEqual(row.price_rub,1000)
        self.assertFalse(confirmed(row))
        self.assertEqual(offers.available_offers(self.db),[])
        self.assertIsNotNone(quote_evidence(row)['price_last_verified_at'])

    def test_refreshing_cache_does_not_restore_expired_observation(self):
        self.add(observed=NAIVE-timedelta(hours=25))
        request=SearchOffers(query='DeepCool AG400',category='cooler',sources=['regard'])
        self.db.add(OfferSearch(key=offers.search_key(request),checked_at=NAIVE,statuses='[]'));self.db.commit()
        with patch('app.services.offers.collect_source') as network:
            result=offers.search_offers(self.db,request)
        network.assert_not_called()
        self.assertEqual(result['offers'],[])

    def test_future_search_cache_is_refreshed(self):
        request=SearchOffers(query='DeepCool AG400',category='cooler',sources=['regard'])
        self.db.add(OfferSearch(key=offers.search_key(request),checked_at=NAIVE+timedelta(days=1),statuses='[]'));self.db.commit()
        with patch('app.services.offers.collect_source',return_value=('regard',[],'unavailable','offline fixture',{})) as network:
            offers.search_offers(self.db,request)
        self.assertEqual(network.call_count,1)

    def test_search_cache_boundary_preserves_ten_minute_inclusive_rule(self):
        request=SearchOffers(query='DeepCool AG400',category='cooler',sources=['regard'])
        row=OfferSearch(key=offers.search_key(request),checked_at=NAIVE-timedelta(minutes=10),statuses='[]')
        self.db.add(row);self.db.commit()
        with patch('app.services.offers.collect_source') as network:
            offers.search_offers(self.db,request)
            network.assert_not_called()
        row.checked_at-=timedelta(microseconds=1);self.db.commit()
        with patch('app.services.offers.collect_source',return_value=('regard',[],'unavailable','offline fixture',{})) as network:
            offers.search_offers(self.db,request)
        self.assertEqual(network.call_count,1)

    def test_future_hardware_price_does_not_enter_budget(self):
        self.db.add(HardwarePrice(hardware_id=1,source='retailer_feed',price_rub=1000,market='retail_ru',
                                 source_url='https://example.test/fixture',observed_at=NAIVE+timedelta(days=1)))
        self.db.commit()
        self.assertNotIn(1,prices.price_map(self.db))

    def test_naive_hardware_price_survives_and_keeps_original_timestamp(self):
        observed=NAIVE-timedelta(days=1)
        self.db.add(HardwarePrice(hardware_id=1,source='retailer_feed',price_rub=1000,market='retail_ru',
                                 source_url='https://example.test/fixture',observed_at=observed))
        self.db.commit()
        quote=prices.price_map(self.db)[1]
        self.assertEqual(quote.observed_at,observed)
        self.assertEqual(prices.public_price(quote)['price_date'],observed.replace(tzinfo=timezone.utc))

    def test_saved_build_created_at_is_utc_and_does_not_refresh_price_check(self):
        from app.api.account import builds
        user=User(id=1,email='fixture@example.test',name='Fixture',password_hash='not-a-real-password')
        result={'status':'complete','parts':[{'price_verified_at':'2026-11-08T12:00:00Z'}]}
        saved=SavedBuild(id=1,user_id=1,created_at=NAIVE,data=json.dumps({'config':{'scenario':'build'},'result':result}))
        self.db.add_all([user,saved]);self.db.commit()
        output=builds(self.db,user,Response())[0]
        self.assertEqual(output['result'],result)
        self.assertEqual(output['created_at'],'2026-11-09T12:00:00Z')
        self.assertEqual(self.db.get(SavedBuild,1).created_at,NAIVE)


    def test_cache_import_normalizes_offsets_and_skips_invalid_future_missing_dates(self):
        import tempfile
        quote={'type':'CPU','name':'AMD Ryzen 5 5600','price_rub':1000,'market':'retail_ru',
               'source_url':'https://example.test/fixture','sample_count':1}
        data={'quotes':[{**quote,'source':'retailer_feed','observed_at':'2026-11-09T14:59:00+03:00'},
                        {**quote,'source':'bad','observed_at':'bad'},
                        {**quote,'source':'future','observed_at':'2026-11-10T12:00:00Z'},
                        {**quote,'source':'missing'}]}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'price_data.json').write_text(json.dumps(data),encoding='utf-8')
            with patch('app.services.prices.__file__',str(root/'app/services/prices.py')):
                prices.load_price_cache(self.db)
        rows=list(self.db.scalars(select(HardwarePrice)))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0].observed_at,NAIVE-timedelta(minutes=1))

    def test_batch_search_rejects_future_cache(self):
        request=SearchOffers(query='DeepCool AG400',category='cooler',sources=['regard'])
        self.db.add(OfferSearch(key=offers.search_key(request),checked_at=NAIVE+timedelta(days=1),statuses='[]'));self.db.commit()
        with patch('app.services.offers.collect_source',return_value=('regard',[],'unavailable','offline fixture',{})) as network:
            offers.batch_search_offers(self.db,[request])
        self.assertEqual(network.call_count,1)

    def test_hardware_price_ttl_boundary_remains_inclusive(self):
        row=HardwarePrice(hardware_id=1,source='retailer_feed',price_rub=1000,market='retail_ru',
                          source_url='https://example.test/fixture',observed_at=NAIVE-timedelta(days=7))
        self.db.add(row);self.db.commit()
        self.assertIn(1,prices.price_map(self.db))
        row.observed_at-=timedelta(microseconds=1);self.db.commit()
        self.assertNotIn(1,prices.price_map(self.db))

    def test_input_normalizes_zone_and_keeps_five_minute_observation_skew(self):
        from pydantic import ValidationError
        payload=dict(source='regard',name='DeepCool AG400',category='cooler',price_rub=1000,
                     url='https://www.regard.ru/product/1/test')
        self.assertEqual(OfferInput(**payload,observed_at='2026-11-09T15:00:00+03:00').observed_at,NAIVE)
        self.assertEqual(OfferInput(**payload,observed_at=NAIVE+timedelta(minutes=5)).observed_at,NAIVE+timedelta(minutes=5))
        with self.assertRaises(ValidationError):
            OfferInput(**payload,observed_at=NAIVE+timedelta(minutes=5,microseconds=1))


    def test_future_existing_offer_does_not_block_a_valid_price_refresh(self):
        row=self.add(observed=NAIVE+timedelta(days=1))
        incoming=OfferInput(source=row.source,name=row.name,category=row.category,price_rub=1752,
                            url=row.url,observed_at=NAIVE,attributes={'price_verification':{
                                'status':'verified','checked_at':'2026-11-09T12:00:00Z'}})
        offers.upsert(self.db,[incoming],'product_page')
        self.assertEqual(row.price_rub,1752)
        self.assertEqual(row.observed_at,NAIVE)

    def test_future_existing_hardware_quote_does_not_block_valid_cache_import(self):
        import tempfile
        row=HardwarePrice(hardware_id=1,source='retailer_feed',price_rub=1000,market='retail_ru',
                          source_url='https://example.test/fixture',observed_at=NAIVE+timedelta(days=1))
        self.db.add(row);self.db.commit()
        quote={'type':'CPU','name':'AMD Ryzen 5 5600','price_rub':1752,'market':'retail_ru',
               'source':'retailer_feed','source_url':'https://example.test/fixture','sample_count':1,
               'observed_at':'2026-11-09T11:59:00Z'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'price_data.json').write_text(json.dumps({'quotes':[quote]}),encoding='utf-8')
            with patch('app.services.prices.__file__',str(root/'app/services/prices.py')):
                prices.load_price_cache(self.db)
        self.assertEqual(row.price_rub,1752)
        self.assertEqual(row.observed_at,NAIVE-timedelta(minutes=1))

    def test_old_observation_with_new_confirmation_is_not_shown_as_current_price(self):
        quote=SimpleNamespace(price_rub=1000,source='regard',market='retail_ru',
                              source_url='https://example.test/fixture',observed_at=NAIVE-timedelta(days=2),
                              verified_at='2026-11-09T11:59:00Z')
        self.assertIsNone(prices.public_price(quote)['price_verified_at'])

    def test_snapshot_import_normalizes_offsets_and_skips_bad_future_records(self):
        import sqlite3
        import tempfile
        from scripts import refresh_prices
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with sqlite3.connect(root/'avito_prices.db') as snapshot:
                snapshot.execute('CREATE TABLE current_prices (title TEXT, price INTEGER, last_updated TEXT, item_id TEXT)')
                snapshot.executemany('INSERT INTO current_prices VALUES (?,?,?,?)',[
                    ('AMD Ryzen 5 5600',1000,'2026-11-09T14:59:00+03:00','123456'),
                    ('AMD Ryzen 5 5600',9999,'bad','234567'),
                    ('AMD Ryzen 5 5600',9999,'2026-11-10T12:00:00Z','345678')])
            snapshot.close()
            with patch.object(refresh_prices,'ROOT',root):
                self.assertEqual(refresh_prices.import_avito_snapshot(self.db,list(self.db.scalars(select(Hardware)))),1)
        row=self.db.get(HardwarePrice,(1,'avito_snapshot'))
        self.assertEqual(row.price_rub,1000)
        self.assertEqual(row.observed_at,NAIVE-timedelta(minutes=1))


class BuildTimeStateTests(ClockFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        import test_adaptive_builds
        self.fixture=test_adaptive_builds.AdaptiveBuildTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db=self.fixture.db
        self.payload=self.fixture.payload

    def build(self, checked, age=timedelta(0)):
        from app.services.builds import BuildRequest, assemble
        from app.core.config import settings
        for row in self.db.scalars(select(StoreOffer)):
            row.observed_at=NAIVE-age
            row.origin='product_page'
            row.attributes=json.dumps({'price_verification':{'status':'verified','checked_at':checked}})
        self.db.commit()
        with patch('app.services.builds.search_offers',return_value={}), patch.object(settings,'offers_browser_enabled',False), patch(
                'app.services.price_verification.fetch',side_effect=RuntimeError('offline store fixture')):
            return assemble(BuildRequest(**self.payload),self.db)

    def test_current_z_check_produces_complete(self):
        result=self.build('2026-11-09T11:59:00Z')
        self.assertEqual(result['status'],'complete')
        self.assertTrue(result['purchase_ready'])
        self.assertEqual(len(result['parts']),8)

    def test_stale_check_with_store_outage_produces_historical_draft(self):
        result=self.build('2026-11-09T11:40:00Z')
        self.assertEqual(result['status'],'draft')
        self.assertFalse(result['purchase_ready'])
        self.assertTrue(all(p['price_verified_at'] is None and p['price_status']=='previously_verified' for p in result['parts']))

    def test_future_check_never_produces_complete(self):
        result=self.build('2026-11-10T12:00:00')
        self.assertEqual(result['status'],'draft')
        self.assertFalse(result['purchase_ready'])
        self.assertTrue(all(p['price_status']=='unconfirmed' for p in result['parts']))

    def test_expired_observation_produces_partial_without_full_price_or_fps(self):
        result=self.build('2026-11-09T11:59:00Z',age=timedelta(hours=25))
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['parts'],[])
        self.assertNotIn('total_price',result)
        self.assertNotIn('fps',result)



if __name__=='__main__':
    unittest.main()

"""Upgrade choices should use game-specific CPU comparisons and honest prices."""
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.models import Hardware, HardwarePrice, StoreOffer
from app.schemas.calculate import CalculateRequest, CalcMode, GameName
from app.api.calculate import post_calculate
from app.services.performance import cpu_capacity, cs2_gpu_reference
from app.services.prices import public_price
from app.services.upgrade_prices import upgrade_price_map, refresh_upgrade_prices, upgrade_search_candidates, upgrade_search_summary
from app.core.config import settings


class UpgradeRecommendationsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            Hardware(id=1, type='CPU', name='AMD Ryzen 5 5600X', raw_score=21819, normalized_score=50, socket='AM4'),
            Hardware(id=2, type='GPU', name='GeForce RTX 5060', raw_score=20607, normalized_score=50, vram=8),
            Hardware(id=3, type='CPU', name='AMD Ryzen 7 5700X3D', raw_score=27000, normalized_score=55, socket='AM4'),
            Hardware(id=4, type='CPU', name='AMD Ryzen 7 5800X', raw_score=28000, normalized_score=55, socket='AM4'),
            Hardware(id=5, type='CPU', name='AMD Ryzen 9 5950X', raw_score=46000, normalized_score=70, socket='AM4'),
            Hardware(id=6, type='CPU', name='AMD Ryzen 7 5800X3D', raw_score=28000, normalized_score=55, socket='AM4'),
        ])
        self.db.commit()
        self.now = datetime.utcnow()
        for item, price in ((3, 12000), (4, 8000), (5, 25000), (6, 20000)):
            self.db.add(HardwarePrice(hardware_id=item, source='avito_snapshot', price_rub=price,
                market='used_ru', source_url='https://www.avito.ru/example', sample_count=5, observed_at=self.now))
        self.db.commit()
        self.payload = CalculateRequest(cpu_id=1, gpu_id=2, game='CS2', mode='1080p_low',
                                        budget=30000, target_fps=600, price_sources=['avito'])

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def offer(self, ident, title, price, hardware_id=3, age=0, condition='used'):
        self.db.add(StoreOffer(id=ident, source='avito', category='CPU', name=title,
            price_rub=price, url=f'https://www.avito.ru/example_{ident}', condition=condition,
            hardware_id=hardware_id, observed_at=self.now-timedelta(hours=age), origin='public_page', attributes='{}'))

    def test_cs2_balanced_pair_prefers_cpu_and_rejects_multicore_score_trap(self):
        result = post_calculate(self.payload, self.db)
        self.assertEqual(result.bottleneck.value, 'CPU')
        self.assertIn('близки', result.limiting_explanation)
        self.assertTrue(result.alternatives)
        names = [option['name'] for option in result.alternatives]
        self.assertTrue(any('5800X' in name or '5700X3D' in name for name in names))
        self.assertFalse(any('5950X' in name for name in names))
        self.assertGreater(cpu_capacity(27000, 'AMD Ryzen 7 5700X3D', GameName.CS2, CalcMode.MODE_1080P_LOW),
                           cpu_capacity(46000, 'AMD Ryzen 9 5950X', GameName.CS2, CalcMode.MODE_1080P_LOW))
        dual_payload = CalculateRequest(**{**self.payload.model_dump(), 'ram_manual': {'type':'DDR4', 'capacity_gb':16, 'channels':2}})
        dual = post_calculate(dual_payload, self.db)
        self.assertEqual(dual.bottleneck.value, 'CPU')

    def test_selected_card_is_recalculated_and_preserved(self):
        first = post_calculate(self.payload, self.db)
        selected = first.alternatives[-1]
        result = post_calculate(self.payload.model_copy(update={'selected_upgrade_id': selected['id']}), self.db)
        self.assertEqual(result.upgrade_id, selected['id'])
        self.assertEqual(result.upgraded_fps, selected['fps'])
        self.assertIn('Выбранный', result.recommendation)

    def test_average_uses_several_safe_current_used_ads_not_one_or_old_or_broken(self):
        for ident, price in enumerate((10000, 11000, 12000, 1000), start=1):
            self.offer(ident, 'AMD Ryzen 7 5700X3D', price)
        self.offer(5, 'AMD Ryzen 7 5700X3D под восстановление', 5000)
        self.offer(6, 'AMD Ryzen 7 5700X3D', 50000, age=24*8)
        self.offer(7, 'AMD Ryzen 7 5700X3D', 50000, condition='new')
        self.db.add(StoreOffer(id=8,source='avito',category='CPU',name='AMD Ryzen 7 5700X3D',
            price_rub=10000,url='https://www.avito.ru/example_1?context=another-search',condition='used',
            hardware_id=3,observed_at=self.now,origin='public_page',attributes='{}'))
        self.db.commit()
        quote = public_price(upgrade_price_map(self.db, ['avito'])[3])
        self.assertEqual(quote['avg_price'], 11000)
        self.assertEqual(quote['sample_count'], 3)
        self.assertEqual(quote['average_method'], 'mean')
        self.assertIsNone(quote['price_verified_at'])

    def test_single_observation_is_labeled_limited_and_other_sources_stay_separate(self):
        self.offer(1, 'AMD Ryzen 7 5700X3D', 13000)
        self.db.commit()
        avito = public_price(upgrade_price_map(self.db, ['avito'])[3])
        self.assertEqual(avito['average_method'], 'one_offer')
        self.assertEqual(avito['sample_count'], 1)
        self.assertNotIn(3, upgrade_price_map(self.db, ['dns']))

    def test_invalid_or_unaffordable_selection_is_rejected(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            post_calculate(self.payload.model_copy(update={'selected_upgrade_id': 999}), self.db)

    def test_missing_prices_show_options_without_claiming_they_fit_budget(self):
        self.db.query(HardwarePrice).delete()
        self.db.commit()
        result = post_calculate(self.payload, self.db)
        self.assertTrue(result.alternatives)
        self.assertFalse(result.within_budget)
        self.assertIn('соответствие бюджету не подтверждено', result.recommendation)
        self.assertTrue(all(card['price'] is None for card in result.alternatives))

    def test_target_already_met_does_not_hide_optional_comparison(self):
        result = post_calculate(self.payload.model_copy(update={'target_fps': 60}), self.db)
        self.assertIsNone(result.upgrade_id)
        self.assertTrue(result.alternatives)
        selected = post_calculate(self.payload.model_copy(update={
            'target_fps': 60, 'selected_upgrade_id': result.alternatives[0]['id']}), self.db)
        self.assertEqual(selected.upgrade_id, result.alternatives[0]['id'])

    def test_upgrade_goal_is_central_fps_not_either_edge_of_the_range(self):
        reached = post_calculate(self.payload.model_copy(update={'target_fps':420}), self.db)
        self.assertGreaterEqual(reached.upgraded_fps, 420)
        self.assertLess(reached.upgraded_fps_outlook['minimum'], 420)
        self.assertTrue(reached.target_reached)
        self.assertTrue(all(card['target_reached'] == (card['fps'] >= 420) for card in reached.alternatives))
        missed = post_calculate(self.payload.model_copy(update={'target_fps':550}), self.db)
        self.assertFalse(missed.target_reached)
        self.assertGreaterEqual(missed.upgraded_fps_outlook['maximum'],550)
        self.assertIn('Цель 550 FPS не достигнута',missed.recommendation)

    def test_cs2_gpu_estimate_does_not_flatten_x3d_and_non_x3d_into_old_420_cap(self):
        result=post_calculate(self.payload,self.db)
        self.assertGreater(result.upgraded_fps,420)
        non_x3d=next(card for card in result.alternatives if card['id']==4)
        x3d=next(card for card in result.alternatives if card['id'] in (3,6))
        self.assertGreater(x3d['fps'],non_x3d['fps'])
        self.assertEqual(result.upgraded_fps_outlook['method'],'benchmark_settings_estimate')
        self.assertIn('Medium',result.upgraded_fps_outlook['sources'][0]['settings'])
        self.assertIsNone(cs2_gpu_reference('GeForce RTX 3050 6GB',10000))

    def test_resale_is_independent_of_purchase_sources_and_can_use_recent_market_history(self):
        self.offer(1,'AMD Ryzen 5 5600X',7000,hardware_id=1,age=48)
        self.db.add(StoreOffer(id=2, source='dns', category='CPU', name='AMD Ryzen 7 5700X3D',
            price_rub=18000, url='https://www.dns-shop.ru/product/test/', condition='new',
            hardware_id=3, observed_at=self.now, origin='public_page', attributes='{}'))
        self.db.commit()
        result = post_calculate(self.payload.model_copy(update={
            'budget':12000, 'sell_mode':'budget_plus_sell', 'price_sources':['dns']}),self.db)
        self.assertEqual(result.current_component_price,7000)
        self.assertEqual(result.total_budget,19000)
        self.assertEqual(result.upgrade_id,3)
        self.assertEqual(result.net_upgrade_cost,11000)
        self.assertTrue(result.within_budget)
        self.assertEqual(result.resale_price['sample_count'],1)
        self.assertEqual(result.resale_price['price_window_days'],7)

    def test_manual_resale_value_is_counted_once_and_only_when_enabled(self):
        enabled=self.payload.model_copy(update={'budget':12000,'sell_mode':'budget_plus_sell','expected_sale_price':7000})
        result=post_calculate(enabled,self.db)
        self.assertEqual(result.total_budget,19000)
        self.assertEqual(result.resale_price['price_origin'],'manual')
        disabled=post_calculate(enabled.model_copy(update={'sell_mode':'budget_only'}),self.db)
        self.assertEqual(disabled.total_budget,12000)
        self.assertEqual(disabled.current_component_price,0)
        zero=post_calculate(enabled.model_copy(update={'expected_sale_price':0}),self.db)
        self.assertEqual(zero.total_budget,12000)

    def test_price_above_combined_budget_is_visible_and_not_selectable(self):
        result=post_calculate(self.payload.model_copy(update={'budget':10000,'sell_mode':'budget_plus_sell','expected_sale_price':1000}),self.db)
        extra=next(card for card in result.alternatives if card['budget_shortfall']>0)
        self.assertFalse(extra['selection_allowed'])
        self.assertEqual(extra['budget_shortfall'],extra['price']-11000)

    def test_upgrade_queries_cover_cpu_gpu_and_replacements_before_browser_fallback(self):
        from sqlalchemy import select
        hardware=list(self.db.scalars(select(Hardware)))
        calls=[]
        clock=[100.0]
        def search(db, request):
            calls.append((request.method,request.hardware_id,request._deadline))
            clock[0]=min(clock[0]+2,request._deadline)
            return {'offers':[], 'sources':[{'source':source,'status':'unavailable','message':'no cards'}
                                           for source in request.sources]}
        with patch('time.monotonic',side_effect=lambda:clock[0]),patch.object(settings,'offers_browser_enabled',True):
            refresh_upgrade_prices(self.db,hardware,hardware[0],hardware[1],145,search,
                                   ['avito','regard'],GameName.CS2,CalcMode.MODE_1080P_LOW)
        first_browser=next(index for index,call in enumerate(calls) if call[0]!='http')
        direct_ids={call[1] for call in calls[:first_browser]}
        self.assertTrue({1,2}.issubset(direct_ids))
        self.assertTrue(direct_ids.intersection({3,4,6}))
        self.assertTrue(all(call[0]=='http' for call in calls[:first_browser]))
        self.assertLessEqual(max(call[2] for call in calls),145)

    def test_newer_expensive_quote_does_not_hide_a_cheaper_current_retail_offer(self):
        for ident,source,price,age in [(101,'regard',15000,1),(102,'dns',41000,0)]:
            self.db.add(StoreOffer(id=ident,source=source,category='GPU',name='GeForce RTX 5060',
                price_rub=price,hardware_id=2,url=f'https://www.{"regard.ru/product" if source=="regard" else "dns-shop.ru/product"}/{ident}/gpu',
                condition='new',observed_at=self.now-timedelta(hours=age),origin='public_page',attributes='{}'))
        self.db.commit()
        self.assertEqual(upgrade_price_map(self.db,['regard','dns'])[2].price_rub,15000)

    def test_cs2_search_includes_x3d_instead_of_only_nearby_multicore_scores(self):
        from sqlalchemy import select
        hardware=list(self.db.scalars(select(Hardware)))
        candidates, limiting=upgrade_search_candidates(hardware,hardware[0],hardware[1],
            GameName.CS2,CalcMode.MODE_1080P_LOW,550,'DDR4',2)
        self.assertEqual(limiting.id,1)
        self.assertTrue({3,6}.issubset({item.id for item in candidates}))
        self.assertNotIn(5,{item.id for item in candidates})

    def test_retail_price_does_not_cancel_avito_replacement_search(self):
        from sqlalchemy import select
        hardware=list(self.db.scalars(select(Hardware)));calls=[]
        def search(db,request):
            calls.append(request)
            if request.method=='http':
                return {'offers':[{'source':'regard'}], 'sources':[{'source':'regard','status':'public_page','message':'OK'}]}
            return {'offers':[], 'sources':[{'source':'avito','status':'unavailable','message':'HTTP 403'}]}
        import time
        with patch.object(settings,'offers_browser_enabled',True):
            refresh_upgrade_prices(self.db,hardware,hardware[0],hardware[1],time.monotonic()+30,
                search,['avito','regard'],GameName.CS2,CalcMode.MODE_1080P_LOW,target_fps=550)
        browser=[request for request in calls if request.method=='browser']
        self.assertTrue(browser)
        self.assertIn(browser[0].hardware_id,(3,6))
        self.assertEqual(browser[0].sources,['avito'])

    def test_real_batch_search_attempts_all_selected_stores(self):
        from sqlalchemy import select
        from app.services.offers import search_offers
        hardware=list(self.db.scalars(select(Hardware)))
        seen=[]
        def collect(source,request,*args):
            seen.append((source,request.hardware_id))
            return source, [], 'unavailable', 'HTTP 403', {}
        import time
        with patch.object(settings,'offers_browser_enabled',False),patch(
                'app.services.offers.collect_source',side_effect=collect):
            statuses=refresh_upgrade_prices(self.db,hardware,hardware[0],hardware[1],time.monotonic()+30,
                search_offers,['avito','regard','kns','dns','ozon'],GameName.CS2,CalcMode.MODE_1080P_LOW,target_fps=550)
        self.assertEqual({source for source,_ in seen},{'avito','regard','kns','dns','ozon'})
        self.assertTrue({('avito',3),('avito',6)}.issubset(set(seen)))
        self.assertTrue(any(row['source']=='avito' and 'X3D' in row['model'] for row in statuses))

    def test_gpu_resale_refresh_searches_gpu_first_when_gpu_is_limiting(self):
        from sqlalchemy import select
        hardware=list(self.db.scalars(select(Hardware)));calls=[]
        def search(db,request):
            calls.append(request)
            return {'offers':[], 'sources':[{'source':source,'status':'unavailable','message':'No offers'}
                for source in request.sources]}
        import time
        with patch.object(settings,'offers_browser_enabled',True):
            refresh_upgrade_prices(self.db,hardware,hardware[0],hardware[1],time.monotonic()+30,
                search,['avito'],GameName.RDR2,CalcMode.MODE_1440P_HIGH,resale_fallback=True)
        self.assertEqual(next(request for request in calls if request.method=='browser').hardware_id,2)

    def test_avito_http_denial_uses_search_engines_without_repeating_blocked_search_page(self):
        from sqlalchemy import select
        hardware=list(self.db.scalars(select(Hardware)));calls=[]
        def search(db,request):
            calls.append(request)
            return {'offers':[], 'sources':[{'source':'avito','status':'unavailable',
                'method':request.method,'message':'HTTP 403'}]}
        import time
        with patch.object(settings,'offers_browser_enabled',True):
            refresh_upgrade_prices(self.db,hardware,hardware[0],hardware[1],time.monotonic()+30,
                search,['avito'],GameName.CS2,CalcMode.MODE_1080P_LOW,resale_fallback=True)
        fallback=[request for request in calls if request.method!='http']
        self.assertEqual(len(fallback),1)
        self.assertEqual(fallback[0].method,'discovery')

    def test_browser_launch_failure_does_not_repeat_for_every_model_and_store(self):
        from sqlalchemy import select
        hardware=list(self.db.scalars(select(Hardware)));calls=[]
        def search(db,request):
            calls.append(request)
            return {'offers':[], 'sources':[{'source':source,'status':'unavailable',
                'message':'Не удалось запустить Chromium'} for source in request.sources]}
        import time
        with patch.object(settings,'offers_browser_enabled',True):
            refresh_upgrade_prices(self.db,hardware,hardware[0],hardware[1],time.monotonic()+30,
                search,['avito','regard','kns'],GameName.CS2,CalcMode.MODE_1080P_LOW)
        self.assertEqual(len([request for request in calls if request.method!='http']),1)

    def test_unknown_x3d_price_is_visible_alongside_a_priced_non_x3d(self):
        self.db.query(HardwarePrice).filter(HardwarePrice.hardware_id.in_([3,6])).delete()
        self.db.commit()
        result=post_calculate(self.payload,self.db)
        self.assertEqual(result.upgrade_id,4)
        self.assertTrue(any('X3D' in item['name'] and item['price'] is None for item in result.alternatives))

    def test_search_summary_does_not_claim_cached_avito_price_was_updated(self):
        from types import SimpleNamespace
        quote=SimpleNamespace(source='avito',price_rub=7000,observed_at=self.now-timedelta(days=1))
        summary=upgrade_search_summary([{'source':'avito','status':'unavailable','message':'HTTP 403',
            'model':'AMD Ryzen 5 5600X'}],{}, {1:quote},['avito','dns'],self.now,{1:'AMD Ryzen 5 5600X'})
        self.assertEqual(summary[0]['status'],'cached')
        self.assertEqual(summary[0]['fresh_quotes'],0)
        self.assertEqual(summary[0]['last_error'],'HTTP 403')
        self.assertEqual(summary[1]['status'],'not_attempted')


if __name__ == '__main__':
    unittest.main()

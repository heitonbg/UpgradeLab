"""Upgrade choices should use game-specific CPU comparisons and honest prices."""
import sys
import unittest
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
from app.services.upgrade_prices import upgrade_price_map


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


if __name__ == '__main__':
    unittest.main()

"""Offline FPS/provenance and builder regression checks."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_adaptive_builds as fixtures
from app.services.performance import estimate_fps

class BuilderCpuRegression(unittest.TestCase):
    def test_automatic_builder_passes_cpu_identity(self):
        fixture=fixtures.AdaptiveBuildTests();fixture.setUp()
        try:
            with patch('app.services.automatic_builds.estimate_fps',wraps=estimate_fps) as spy:
                fixture.build(game='CS2',mode='1080p_low')
            self.assertTrue(spy.call_args_list)
            for call in spy.call_args_list:
                self.assertTrue(call.kwargs.get('cpu_name') or len(call.args)>6 and call.args[6])
        finally:fixture.tearDown()

import json,math
from datetime import datetime,timedelta
from types import SimpleNamespace as Obj
from sqlalchemy import select
from app.db.models import StoreOffer
from app.services.game_catalog import search_games,catalog
from app.services.fps_validation import measured_native,grouped_split,series_key,metrics,validation_report
from app.services.fps_v2 import predict
from app.services.builds import BuildRequest,assemble
from app.services.saved_prices import snapshot_items,linked_offer
from app.services.planning_prices import scoped_inventory

class CatalogTests(unittest.TestCase):
    def test_large_local_catalog(self):
        self.assertGreater(len(catalog()),16000)
        self.assertEqual(search_games('GTA 5')['items'][0]['id'],'GTA V')
        self.assertEqual(search_games('Counter-Strike 2')['items'][0]['id'],'CS2')
    def test_unsupported_is_not_fake_fps(self):
        self.assertTrue(any(not r['fps_supported'] for r in search_games('')['items']))
        self.assertEqual(search_games('zzzzzzzznonexistent')['items'],[])
    def test_cached_search(self):
        self.assertIs(search_games('Hades'),search_games('Hades'))

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.row=json.loads((Path(__file__).resolve().parents[1]/'app/data/fps_measurements.json').read_text())['records']
        self.native=next(r for r in self.row if measured_native(r))
    def test_rejects_model_rt_upscaling_fg_mobile_os_and_bad_values(self):
        for patch_ in [dict(synthetic=True),dict(upscaling='FSR Quality'),dict(frame_generation=True),dict(graphics_preset='Ray Tracing: Ultra'),dict(form_factor='Laptop'),dict(os='linux'),dict(avg_fps=float('nan')),dict(cpu=''),dict(date='')]:
            self.assertFalse(measured_native({**self.native,**patch_}),patch_)
    def test_groups_never_leak(self):
        other={**self.native,'gpu_id':'other'}
        train,test=grouped_split([self.native,{**self.native,'resolution':'4K'},other])
        self.assertTrue(train and test)
        self.assertFalse({series_key(r) for r in train}&{series_key(r) for r in test})
    def test_single_series_cannot_be_split_into_fake_holdout(self):
        report=validation_report();self.assertEqual(report['eligible_native_windows'],3)
        self.assertEqual(report['held_out_rows'],0);self.assertFalse(report['promoted'])
        self.assertIsNone(report['candidate']['mae'])
    def test_metrics(self):
        m=metrics([(100,110,90,120),(200,180,170,190)],total=4)
        self.assertEqual(m['mae'],15);self.assertEqual(m['mape_percent'],10)
        self.assertEqual(m['interval_coverage'],.5);self.assertEqual(m['prediction_coverage'],.5)
        self.assertIsNone(metrics([])['mae'])

class FpsGateTests(unittest.TestCase):
    def setUp(self):
        self.cpu=Obj(name='AMD Ryzen 5 5600',raw_score=21819)
        self.gpu=Obj(name='GeForce RTX 4060',raw_score=19500,vram=8)
    def test_existing_prediction_remains_labelled_legacy(self):
        p=predict(self.cpu,self.gpu,'CS2',preset='low',ram_type='DDR4',ram_channels=2)
        self.assertEqual(p['average_fps'],estimate_fps(21819,19500,self.gpu.name,__import__('app.schemas.calculate',fromlist=['GameName']).GameName.CS2,__import__('app.schemas.calculate',fromlist=['CalcMode']).CalcMode.MODE_1080P_LOW,1,self.cpu.name))
        self.assertFalse(p['interval']['calibrated']);self.assertIsNone(p['one_percent_low'])
    def test_unknown_games_settings_and_features_abstain(self):
        for patch_ in [dict(game='Unknown'),dict(resolution='4K'),dict(preset='medium'),dict(rt=True),dict(upscaling='dlss'),dict(frame_generation=True)]:
            p=predict(self.cpu,self.gpu,**{'game':'CS2',**patch_})
            self.assertEqual(p['status'],'insufficient_data');self.assertIsNone(p['average_fps'])
    def test_unknown_x3d_no_universal_cache_bonus(self):
        a=predict(Obj(name='Unknown CPU',raw_score=20000),self.gpu,'CS2',preset='low')
        b=predict(Obj(name='AMD Ryzen 5 5500X3D',raw_score=20000),self.gpu,'CS2',preset='low')
        self.assertEqual(a['average_fps'],b['average_fps']);self.assertTrue(any('кеша' in w for w in b['warnings']))
    def test_cpu_gpu_limits(self):
        weak_cpu=predict(Obj(name='Unknown CPU',raw_score=1000),self.gpu,'CS2',preset='low')
        weak_gpu=predict(self.cpu,Obj(name='Unknown GPU',raw_score=100,vram=None),'CS2',preset='low')
        self.assertEqual(weak_cpu['limiting_component'],'CPU');self.assertEqual(weak_gpu['limiting_component'],'GPU')
    def test_no_cpu_or_gpu_score_no_prediction(self):
        self.assertIsNone(predict(Obj(name='Unknown',raw_score=0),self.gpu,'CS2')['average_fps'])

class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.AdaptiveBuildTests();self.fixture.setUp();self.db=self.fixture.db
    def tearDown(self):self.fixture.tearDown()
    def build(self,mode,**extra):
        with patch('app.services.builds.search_offers',side_effect=AssertionError('No network in planning')):
            return assemble(BuildRequest(**{**self.fixture.payload,'budget':80000,'pricing_mode':mode,**extra}),self.db)
    def test_reference_full_80000_no_network_no_live_claim(self):
        before=[(r.id,r.price_rub,r.observed_at,r.attributes) for r in self.db.scalars(select(StoreOffer))]
        result=self.build('reference')
        self.assertEqual(len(result['parts']),8);self.assertEqual(result['total_price'],48500)
        self.assertEqual(result['total_price'],sum(p['price'] for p in result['parts']))
        self.assertTrue(all(p.get('price_basis')=='reference' and p['offer_id'] is None and p['price_verified_at'] is None for p in result['parts']))
        self.assertFalse(result['purchase_ready']);self.assertEqual(result['status'],'draft');self.assertIn('справочные',result['price_note'])
        self.assertEqual(before,[(r.id,r.price_rub,r.observed_at,r.attributes) for r in self.db.scalars(select(StoreOffer))]);self.assertIsNone(scoped_inventory())
    def test_hybrid_uses_reference_only_for_missing_category(self):
        row=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='cooler'));row.observed_at=datetime.utcnow()-timedelta(days=2);self.db.commit()
        result=self.build('hybrid')
        self.assertEqual([p['type'] for p in result['parts'] if p.get('price_basis')=='reference'],['cooler'])
        self.assertTrue(all(p.get('offer_id') for p in result['parts'] if p['type']!='cooler'))
    def test_reference_unavailable_store_keeps_history(self):
        row=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='cooler'));row.observed_at=datetime.utcnow()-timedelta(days=30);self.db.commit()
        result=self.build('reference')
        cooler=next(p for p in result['parts'] if p['type']=='cooler')
        self.assertTrue(cooler['price_observed_at'].startswith(row.observed_at.date().isoformat()))
    def test_missing_data_does_not_invent_price(self):
        from sqlalchemy import delete
        from fastapi import HTTPException
        self.db.execute(delete(StoreOffer).where(StoreOffer.category=='case'));self.db.commit()
        with self.assertRaises(HTTPException) as e:self.build('reference')
        self.assertIn('case',e.exception.detail);self.assertIsNone(scoped_inventory())
    def test_saved_reference_not_upgraded_by_url_match(self):
        result=self.build('reference');items=snapshot_items(result)
        self.assertTrue(all(i['price_basis']=='reference' for i in items))
        self.assertTrue(all(linked_offer(self.db,i) is None for i in items))
    def test_existing_offers_mode_still_works(self):
        result=self.fixture.build(pricing_mode='offers');self.assertEqual(len(result['parts']),8)
    def test_builder_ram_uses_shared_cs2_rule(self):
        with patch('app.services.automatic_builds.estimate_fps',wraps=estimate_fps) as spy:self.fixture.build(game='CS2',mode='1080p_low')
        self.assertTrue(all(call.args[5]==1.0 for call in spy.call_args_list))

    def test_reference_is_not_an_additional_store(self):
        from app.schemas.offers import LABELS
        self.build('reference')
        self.assertNotIn('reference',LABELS)
        self.assertEqual(len(LABELS),13)

    def test_closed_catalog_is_not_a_reference_price_bypass(self):
        from fastapi import HTTPException
        row=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='case'));row.origin='catalog_import';self.db.commit()
        with self.assertRaises(HTTPException):self.build('reference')
    def test_reference_preserves_source_access_link(self):
        from app.services.result_access import current_result
        result=self.build('reference');self.assertTrue(current_result(self.db,result))
        row=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='case'));row.origin='catalog_import';self.db.commit()
        self.assertFalse(current_result(self.db,result))

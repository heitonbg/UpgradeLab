"""Offline benchmark curation, admissibility, and hybrid-policy regressions."""
import sys,unittest
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
from fastapi import HTTPException
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_adaptive_builds as fixtures
class OptimizerEvidenceTests(unittest.TestCase):
    def setUp(self):self.f=fixtures.AdaptiveBuildTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def test_missing_cpu_score_is_not_an_fps_prediction(self):
        self.f.db.get(__import__('app.db.models',fromlist=['Hardware']).Hardware,1).raw_score=0;self.f.db.commit()
        try:result=self.f.build(game='CS2',mode='1080p_low')
        except HTTPException:return
        self.assertIsNone(result.get('fps'));self.assertEqual(result['status'],'partial')
    def test_hybrid_preserves_offer_option_and_exposes_better_reference(self):
        row=self.f.add('GPU','GeForce RTX 4060',15000,3)
        row.observed_at=datetime.utcnow()-timedelta(days=2);self.f.db.commit()
        hybrid=self.f.build(game='CS2',mode='1080p_low',budget=80000,target_fps=400,pricing_mode='hybrid')
        reference=self.f.build(game='CS2',mode='1080p_low',budget=80000,target_fps=400,pricing_mode='reference')
        self.assertLess(hybrid['fps'],reference['fps'])
        self.assertGreater(reference['fps']/reference['total_price'],hybrid['fps']/hybrid['total_price'])
        self.assertLessEqual(reference['total_price'],80000)
        comparison=next(v for v in hybrid['alternatives'] if v.get('variant_key')=='hybrid_comparison')
        self.assertGreater(comparison['fps'],hybrid['fps'])
        self.assertEqual(comparison['fps'],reference['fps'])
        self.assertFalse(comparison['purchase_ready'])
        self.assertNotIn('alternatives',comparison)
        self.assertTrue(any(p.get('price_basis')=='reference' for p in comparison['parts']))
        self.assertLessEqual(len(hybrid['alternatives']),3)


import copy,json,math,tempfile
from app.services.benchmark_data import build_dataset,Observation,deduplicate,import_open_gpu,import_techfuel,native_cohort,DIRECTORY,ROOT
from app.services.benchmark_calibration import compare_models,error_metrics,publisher_folds,solve_frametime,relative_prediction,features

class BenchmarkDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.dataset=build_dataset();cls.rows=cls.dataset['rows']
    def test_snapshot_counts_separate_measurements_and_synthetics(self):
        q=self.dataset['quality'];self.assertEqual(q['observations'],81);self.assertEqual(q['games'],4)
        self.assertEqual(q['publishers'],2);self.assertEqual(q['series'],4)
        self.assertEqual(len(q['excluded']),20);self.assertEqual(len(q['duplicates_merged']),1)
        self.assertEqual(q['native_windows_stock'],4);self.assertEqual(q['native_linux_stock'],8)
    def test_missing_techfuel_metadata_remains_unknown(self):
        rows=[r for r in self.rows if r['publisher']=='TechFuelHQ'];self.assertEqual(len(rows),8)
        self.assertTrue(all(r['game_version'] is None and r['os'] is None and r['ram_channels'] is None for r in rows))
        wukong=next(r for r in rows if r['game']=='Black Myth: Wukong')
        self.assertIsNone(wukong['render_scale']);self.assertIsNone(wukong['rt']);self.assertIsNone(wukong['frame_generation'])
        self.assertTrue(all(not native_cohort(r) for r in rows))
    def test_repeated_pt_observation_merges_low_and_both_sources(self):
        r=next(r for r in self.rows if r['publisher']=='TechFuelHQ' and r['average_fps']==19)
        self.assertEqual(len(r['source_ids']),2);self.assertEqual(r['one_percent_low'],15)
    def test_equal_fps_from_independent_publishers_is_not_duplicate(self):
        row=self.rows[0];other={**row,'id':'independent','publisher':'Other','source_ids':['other']}
        rows,duplicates=deduplicate([row,other]);self.assertEqual(len(rows),2);self.assertEqual(duplicates,[])
    def test_conflicting_low_in_repeated_point_rejected(self):
        row=next(r for r in self.rows if r['one_percent_low'])
        with self.assertRaises(ValueError):deduplicate([row,{**row,'one_percent_low':row['one_percent_low']*.5}])
    def test_boolean_nan_negative_and_invalid_low_rejected(self):
        for values in [{'average_fps':True},{'average_fps':float('nan')},{'average_fps':-1},{'one_percent_low':100000}]:
            with self.assertRaises(ValueError):Observation.model_validate({**self.rows[0],**values})
    def test_license_and_first_party_assertion_required(self):
        ogb=json.loads((ROOT/'fps_measurements.json').read_text());ogb['_license']['name']='unknown'
        with self.assertRaises(ValueError):import_open_gpu(ogb)
        tf=json.loads((DIRECTORY/'techfuel_raw.json').read_text());tf['license']['spdx_id']='proprietary'
        with self.assertRaises(ValueError):import_techfuel(tf)
    def test_estimated_row_cannot_become_measurement(self):
        ogb=json.loads((ROOT/'fps_measurements.json').read_text());row=next(r for r in ogb['records'] if r['game_type']=='game')
        ogb['records']=[{**row,'data_type':'estimated'}];rows,excluded=import_open_gpu(ogb)
        self.assertFalse(rows);self.assertEqual(len(excluded),1)
    def test_rt_fg_os_and_oc_not_eligible_for_native_windows(self):
        row=next(r for r in self.rows if native_cohort(r))
        for values in [dict(data_type='estimated'),dict(rt=True),dict(frame_generation=True),dict(os='linux'),dict(overclocked=True),dict(upscaling='DLSS Quality'),dict(game_version=None)]:
            self.assertFalse(native_cohort({**row,**values}))
    def test_publisher_and_series_do_not_cross_folds(self):
        for publisher,train,test in publisher_folds(self.rows):
            self.assertNotIn(publisher,{r['publisher'] for r in train})
            self.assertFalse({r['series_id'] for r in train}&{r['series_id'] for r in test})
    def test_reports_are_deterministic_and_do_not_promote(self):
        a=compare_models(self.rows);b=compare_models(self.rows)
        self.assertEqual(a,b);self.assertFalse(a['promotion']['allowed'])
        self.assertEqual(a['models']['legacy']['n'],2)
        self.assertAlmostEqual(a['models']['legacy']['all_configuration_prediction_coverage'],2/72)
        self.assertAlmostEqual(a['models']['legacy']['all_observation_prediction_coverage'],3/81)
        self.assertAlmostEqual(a['models']['legacy']['mae'],86.385)
        self.assertEqual(a['models']['relative_transfer']['n'],0)
        self.assertIsNone(a['models']['regression']['mae']);self.assertEqual(a['x3d_comparisons'],[])
    def test_no_cross_cpu_x3d_transfer(self):
        row=next(r for r in self.rows if native_cohort(r))
        anchor={**row,'publisher':'Other','series_id':'other','cpu':'AMD Ryzen 7 5800X3D'}
        self.assertIsNone(relative_prediction(row,[anchor]))
    def test_unknown_cpu_and_vram_variant_abstain(self):
        row=next(r for r in self.rows if native_cohort(r))
        self.assertIsNone(features({**row,'cpu':'Unknown CPU'}))
        self.assertIsNone(features({**row,'vram_gb':8}))
    def test_frametime_solver_rank_and_positive_physics(self):
        # Synthetic mathematical unit fixtures, NOT imported benchmark evidence.
        points=[(c,g,1000/(20000/c+10000/g)) for c,g in [(10000,10000),(20000,10000),(30000,20000),(10000,30000),(20000,20000),(30000,30000)]]
        a,b=solve_frametime(points);self.assertAlmostEqual(a,20000);self.assertAlmostEqual(b,10000)
        self.assertIsNone(solve_frametime([(10000,10000,60)]*6))
    def test_median_percentage_error_and_abstention_denominator(self):
        m=error_metrics([(100,110,90,120),(100,200,180,220),(100,110,90,120)],4)
        self.assertEqual(m['mdape_percent'],10);self.assertEqual(m['mape_percent'],40)
        self.assertEqual(m['prediction_coverage'],.75);self.assertIsNone(error_metrics([],3)['mae'])
    def test_reproduction_no_database_or_network(self):
        from scripts.prepare_fps_benchmarks import prepare
        with tempfile.TemporaryDirectory() as directory:
            with patch('socket.socket.connect',side_effect=AssertionError('No network')),patch('app.db.base.engine.connect',side_effect=AssertionError('No working SQLite')):
                q,e=prepare(directory)
            saved=json.loads((Path(directory)/'measurements.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['rows'],self.rows);self.assertEqual(q['observations'],81)

    def test_raw_repeat_does_not_increase_independent_configurations(self):
        from app.services.benchmark_calibration import configuration_rows
        grouped=configuration_rows(self.rows)
        self.assertEqual(len(grouped),72)
        qhd=next(r for r in grouped if r['os']=='windows' and r['resolution']=='1440p' and r['preset']=='High' and r['upscaling']=='off')
        self.assertEqual(qhd['observation_count'],2)
        self.assertAlmostEqual(qhd['average_fps'],179.13)
        self.assertIsNone(qhd['one_percent_low'])
    def test_summary_version_is_not_assumed_consistent(self):
        archive=json.loads((ROOT/'fps_measurements.json').read_text());rows,_=import_open_gpu(archive)
        self.assertTrue(all(r['version_consistent'] is None for r in rows))
        self.assertTrue(all(not native_cohort(r) for r in rows))
    def test_upgrade_api_rejects_missing_current_score(self):
        from app.api.calculate import _post_calculate
        from app.schemas.calculate import CalculateRequest
        from app.db.models import Hardware
        fixture=fixtures.AdaptiveBuildTests();fixture.setUp()
        try:
            fixture.db.get(Hardware,1).raw_score=0;fixture.db.commit()
            with self.assertRaises(HTTPException):_post_calculate(CalculateRequest(cpu_id=1,gpu_id=2,game='CS2',mode='1080p_low'),fixture.db)
        finally:fixture.tearDown()

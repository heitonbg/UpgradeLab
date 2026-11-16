from pathlib import Path
import json
import sys
import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api.deps import get_db
from app.api.games import router as games_router
from app.api.calculate import _post_calculate
from app.db.models import Hardware
from app.db.base import Base
from app.schemas.calculate import CalculateRequest, GameName
from app.services.builds import BuildRequest
from app.services.fps_engine_v4 import resolve_fps_v4, relative_hardware_index, relative_pair_proxy
from app.services.game_catalog import catalog


class UniversalFpsV4Tests(unittest.TestCase):
    def setUp(self):
        self.cpu = SimpleNamespace(name='AMD Ryzen 9 9950X3D', raw_score=60000, cores=16, socket='AM5')
        self.gpu = SimpleNamespace(name='GeForce RTX 5080', raw_score=80000, vram=16)

    def test_v4_returns_real_pair_measurement_and_provenance(self):
        result = resolve_fps_v4(self.cpu, self.gpu, 'Cyberpunk 2077', '1440p', 'high')
        self.assertEqual(result['model_version'], '4.0')
        self.assertEqual(result['confidence_level'], 'measured_pair')
        self.assertEqual(result['measurement_type'], 'measured')
        self.assertEqual(result['average_fps'], 179.13)
        self.assertEqual(result['one_percent_low'], 136.21)
        self.assertTrue(result['source_evidence'][0]['url'].startswith('https://'))
        self.assertFalse(result['ram_used_by_model'])

    def test_v4_uses_exact_native_4k_measurement_when_available(self):
        result = resolve_fps_v4(self.cpu, self.gpu, 'Cyberpunk 2077', '4K', 'high')
        self.assertEqual(result['status'], 'measured_reference')
        self.assertEqual(result['average_fps'], 91.48)
        self.assertEqual(result['one_percent_low'], 76.8)

    def test_v4_accepts_3840_by_2160_alias_for_exact_native_measurement(self):
        result = resolve_fps_v4(self.cpu, self.gpu, 'Cyberpunk 2077', '3840×2160', 'high')
        self.assertEqual(result['status'], 'measured_reference')
        self.assertEqual(result['average_fps'], 91.48)

    def test_v4_evaluation_can_exclude_held_out_resolution(self):
        archive = json.loads((Path(__file__).resolve().parents[1] / 'app/data/benchmarks/measurements.json').read_text(encoding='utf-8'))
        training_rows = [row for row in archive['rows'] if row['resolution'] != '1440p']
        result = resolve_fps_v4(self.cpu, self.gpu, 'Cyberpunk 2077', '1440p', 'high',
                                measurement_rows=training_rows)
        self.assertEqual(result['status'], 'estimated_interpolation')
        self.assertEqual(result['method'], 'same_pair_frame_time_interpolation')
        self.assertAlmostEqual(result['average_fps'], 150.16, places=2)

    def test_evaluation_compares_only_like_for_like_system_fps(self):
        from app.services.fps_v2_evaluation import evaluate_v2
        comparison = evaluate_v2()['model_comparison']
        self.assertEqual(comparison['independent_test_series'], 1)
        self.assertEqual(comparison['leakage_safe_common_holdout_points'], 1)
        self.assertEqual(comparison['fps_v3']['scorable_points'], 0)
        self.assertEqual(comparison['fps_v4']['scorable_points'], 1)
        self.assertEqual(comparison['external_gpu_model']['scorable_full_system_points'], 0)
        self.assertFalse(comparison['external_gpu_model']['gpu_only_reference_points'][0]['scored_as_accuracy'])

    def test_v4_uses_labeled_legacy_profile_only_when_available(self):
        cpu = SimpleNamespace(name='AMD Ryzen 5 5600', raw_score=21819)
        gpu = SimpleNamespace(name='GeForce RTX 4060', raw_score=19500, vram=8)
        result = resolve_fps_v4(cpu, gpu, 'CS2', '1080p', 'low')
        self.assertEqual(result['confidence_level'], 'legacy_profile')
        self.assertGreater(result['average_fps'], 0)
        self.assertEqual(result['measurement_type'], 'estimated')

    def test_rtx_5090_has_fpshq_gpu_reference_for_1440p_and_4k_cyberpunk(self):
        from app.services.fps_engine_v4 import _fpshq_gpu_estimate
        gpu = SimpleNamespace(name='GeForce RTX 5090', raw_score=60000, vram=32)
        qhd = _fpshq_gpu_estimate(gpu, 'Cyberpunk 2077', '1440p', 'high', False, 'off', False)
        uhd = _fpshq_gpu_estimate(gpu, 'Cyberpunk 2077', '4K', 'high', False, 'off', False)
        self.assertEqual(qhd['fps'], 171)
        self.assertGreater(uhd['fps'], 0)
        self.assertEqual(qhd['source_settings']['resolution'], '1440p')
        self.assertEqual(uhd['source_settings']['resolution'], '4K')
        self.assertEqual(qhd['source_name'], 'FPSHQ')

    def test_gpu_above_pcgb_safe_range_without_exact_crosswalk_gets_nearest_anchor(self):
        cpu = SimpleNamespace(name='AMD Ryzen 5 5600', raw_score=21819)
        gpu = SimpleNamespace(name='GeForce RTX 5090 prototype', raw_score=60000, vram=32)
        result = resolve_fps_v4(cpu, gpu, 'Portal 2', '1080p', 'high')
        self.assertEqual(result['status'], 'external_model_nearest_anchor_fallback')
        self.assertGreater(result['gpu_oriented_fps'], 0)
        self.assertEqual(result['gpu_estimate_details']['nearest_reference_gpu'], 'GeForce RTX 4090')
        self.assertIsNone(result['average_fps'])
        self.assertIn('не перенос', result['note'])

    def test_unprofiled_catalog_game_gets_labeled_generic_gpu_reference(self):
        result = resolve_fps_v4(self.cpu, self.gpu, "The World's Most Unknown Game", '1440p', 'high')
        self.assertEqual(result['status'], 'catalog_gpu_reference_only')
        self.assertIsNone(result['average_fps'])
        self.assertGreater(result['gpu_oriented_fps'], 0)
        self.assertEqual(result['gpu_estimate_details']['scope'], 'nearest_reference_gpu_population_median_by_game')
        self.assertFalse(result['ram_used_by_model'])

    def test_cpu_frame_time_coverage_is_explicit_and_not_calibrated_from_single_pair(self):
        from app.services.benchmark_model_v2 import cpu_comparison_coverage
        coverage = cpu_comparison_coverage()
        self.assertEqual(coverage['eligible_native_observations'], 4)
        self.assertEqual(coverage['groups_with_multiple_cpu_models'], 0)
        self.assertEqual(coverage['calibrated_cpu_frame_time_games'], 0)
        result = resolve_fps_v4(self.cpu, self.gpu, 'Cyberpunk 2077', '1440p', 'high')
        self.assertFalse(result['cpu_frame_time_evidence']['calibrated'])
        self.assertIsNone(result['cpu_frame_time_ms'])
        self.assertIsNone(result['gpu_frame_time_ms'])
        self.assertIsNone(result['limiting_component'])

    def test_pair_delta_requires_same_exact_test_series_and_settings(self):
        from app.services.fps_engine_v4 import comparable_pair_measurements
        base = {'status': 'measured_reference', 'workload_source': 'licensed_pair_measurements',
                'settings': {'resolution': '1080p', 'preset': 'high', 'game_version': '1'},
                'series_ids': ['series-a'], 'source_evidence': [{'publisher': 'Open GPU Benchmarks'}]}
        self.assertTrue(comparable_pair_measurements(base, dict(base)))
        different_series = dict(base, series_ids=['series-b'])
        self.assertFalse(comparable_pair_measurements(base, different_series))
        different_settings = dict(base, settings={'resolution': '1440p', 'preset': 'high', 'game_version': '1'})
        self.assertFalse(comparable_pair_measurements(base, different_settings))

    def test_cpu_upgrade_does_not_show_unchanged_gpu_oriented_value_as_zero_gain(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                cpu = Hardware(type='CPU', name='AMD Ryzen 5 5600', raw_score=21819, normalized_score=21819, cores=6, socket='AM4')
                replacement = Hardware(type='CPU', name='AMD Ryzen 7 7800X3D', raw_score=34000, normalized_score=34000, cores=8, socket='AM5')
                gpu = Hardware(type='GPU', name='GeForce RTX 3060', raw_score=17008, normalized_score=17008, vram=12)
                db.add_all([cpu, replacement, gpu]); db.commit()
                request = CalculateRequest.model_validate({
                    'cpu_id': cpu.id, 'gpu_id': gpu.id, 'game': 'Portal 2',
                    'mode': '1080p_high', 'budget': 50000, 'target_fps': 60,
                    'selected_upgrade_id': replacement.id,
                })
                response = _post_calculate(request, db)
                self.assertGreater(response.fps_v4_evidence['gain_fps'], 0)
                self.assertIsNone(response.fps_v4_evidence['gpu_oriented_gain_fps'])
                self.assertEqual(response.fps_result['current']['result_type'], 'estimated_system_fps')
                self.assertGreater(response.fps_result['gain_fps'], 0)
                self.assertIsNone(response.fps_result['gpu_oriented_gain_fps'])
                self.assertIsNotNone(response.upgraded_fps)
        finally:
            engine.dispose()

    def test_accuracy_metrics_include_p90_bias_and_prediction_coverage(self):
        from app.services.fps_v2_evaluation import _point_metrics
        metrics = _point_metrics([
            {'predicted': 110, 'measured': 100},
            {'predicted': 180, 'measured': 200},
        ], denominator=4)
        self.assertEqual(metrics['n'], 2)
        self.assertEqual(metrics['eligible_holdouts'], 4)
        self.assertEqual(metrics['prediction_coverage'], 0.5)
        self.assertEqual(metrics['mae_fps'], 15)
        self.assertEqual(metrics['mdape_percent'], 10)
        self.assertEqual(metrics['p90_ape_percent'], 10)
        self.assertEqual(metrics['bias_fps'], -5)

    def test_passmark_percentiles_are_separate_and_not_fps(self):
        cpu = relative_hardware_index(200, [100, 200, 300])
        gpu = relative_hardware_index(900, [300, 600, 900])
        pair = relative_pair_proxy(200, 900, [100, 200, 300], [300, 600, 900])
        self.assertEqual(cpu['percentile'], 66.7)
        self.assertEqual(gpu['percentile'], 100.0)
        self.assertIsNotNone(pair['balanced_percentile_proxy'])
        self.assertIn('не является игровым FPS', cpu['note'])

    def test_all_catalog_entries_are_selectable_and_coverage_is_explicit(self):
        rows = catalog()
        self.assertGreater(len(rows), 16000)
        self.assertTrue(all(row.get('selectable') for row in rows))
        self.assertEqual(sum(row.get('fps_capability') == 'external_model_estimate' for row in rows), 16427)
        self.assertEqual(sum(row.get('external_gpu_estimate_available') for row in rows), 16441)
        self.assertEqual(sum(row.get('fps_capability') == 'insufficient_data' for row in rows), 1)
        self.assertEqual(sum(row.get('legacy_profile_available') for row in rows), 19)
        self.assertEqual(sum(row.get('native_pair_observation_count', 0) for row in rows), 4)
        self.assertTrue(all('fps_supported' not in row for row in rows))

    def test_calculate_and_builder_schemas_accept_any_game_but_keep_enum_for_known(self):
        calculate = CalculateRequest.model_validate({'cpu_id': 1, 'gpu_id': 2,
            'game': 'A game outside the legacy enum', 'mode': '1440p_high'})
        self.assertEqual(calculate.game, 'A game outside the legacy enum')
        known = CalculateRequest.model_validate({'cpu_id': 1, 'gpu_id': 2,
            'game': 'CS2', 'mode': '1080p_low'})
        self.assertEqual(known.game, GameName.CS2)
        build = BuildRequest.model_validate({'scenario': 'build', 'budget': 100000,
            'game': 'A game outside the legacy enum', 'mode': '1440p_high',
            'socket': 'AM5', 'ram_type': 'DDR5', 'ram_capacity_gb': 32})
        self.assertEqual(build.game, 'A game outside the legacy enum')

    def test_unsupported_game_upgrader_returns_gpu_catalog_reference_not_system_fps(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                cpu = Hardware(type='CPU', name='AMD Ryzen 9 9950X3D', raw_score=60000, normalized_score=60000, cores=16, socket='AM5')
                gpu = Hardware(type='GPU', name='GeForce RTX 5080', raw_score=80000, normalized_score=80000, vram=16)
                db.add_all([cpu, gpu]); db.commit()
                request = CalculateRequest.model_validate({'cpu_id': cpu.id, 'gpu_id': gpu.id,
                    'game': 'A game outside the legacy enum', 'mode': '1440p_high', 'budget': 50000})
                response = _post_calculate(request, db)
                self.assertIsNotNone(response.bottleneck)
                self.assertIsNotNone(response.current_fps)
                self.assertEqual(response.fps_v4_evidence['current']['status'], 'universal_fallback_estimate')
                self.assertEqual(response.fps_result['current']['result_type'], 'estimated_system_fps')
                self.assertGreater(response.fps_result['current']['gpu_oriented_fps'], 0)
                self.assertIsNotNone(response.fps_result['current']['average_fps'])
        finally:
            engine.dispose()

    def test_fps_api_returns_universal_v4_candidate_for_any_title(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            cpu = Hardware(type='CPU', name='AMD Ryzen 9 9950X3D', raw_score=60000, normalized_score=60000, cores=16, socket='AM5')
            gpu = Hardware(type='GPU', name='GeForce RTX 5080', raw_score=80000, normalized_score=80000, vram=16)
            db.add_all([cpu, gpu]); db.commit(); cpu_id, gpu_id = cpu.id, gpu.id
        app = FastAPI()
        def database():
            with Session(engine) as db:
                yield db
        app.dependency_overrides[get_db] = database
        app.include_router(games_router)
        try:
            with TestClient(app) as client:
                response = client.post('/api/fps/predict', json={'cpu_id': cpu_id, 'gpu_id': gpu_id,
                    'game': 'Unprofiled catalog title', 'resolution': '1440p', 'preset': 'high'})
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result['result_type'], 'estimated_system_fps')
                self.assertEqual(result['technical_details']['status'], 'universal_fallback_estimate')
                self.assertGreater(result['gpu_oriented_fps'], 0)
                self.assertEqual(result['best_available_fps'], result['average_fps'])
                self.assertIsNotNone(result['gpu_reference_range'])
                self.assertIsNotNone(result['average_fps'])
                self.assertIsNotNone(result['limiting_component'])
                self.assertNotIn('candidate_v4', result)
                measured = client.post('/api/fps/predict', json={'cpu_id': cpu_id, 'gpu_id': gpu_id,
                    'game': 'Cyberpunk 2077', 'resolution': '1440p', 'preset': 'high',
                    'ram_type': 'DDR5', 'ram_channels': 2, 'ram_capacity_gb': 64})
                self.assertEqual(measured.status_code, 200, measured.text)
                measured_result = measured.json()
                self.assertEqual(measured_result['result_type'], 'measured_system_fps')
                self.assertEqual(measured_result['average_fps'], 179.13)
                self.assertEqual(measured_result['one_percent_low'], 136.21)
                self.assertFalse(measured_result['technical_details']['ram_used_by_model'])
                self.assertEqual(measured_result['technical_details']['settings']['ram_type'], 'DDR5-6000')
                gpu3060 = Hardware(type='GPU', name='GeForce RTX 3060', raw_score=17008,
                                   normalized_score=17008, vram=12)
                with Session(engine) as db:
                    db.add(gpu3060); db.commit(); gpu3060_id = gpu3060.id
                external = client.post('/api/fps/predict', json={
                    'cpu_id': cpu_id, 'gpu_id': gpu3060_id, 'game': 'Portal 2',
                    'resolution': '1080p', 'preset': 'high',
                })
                self.assertEqual(external.status_code, 200, external.text)
                external_result = external.json()
                self.assertEqual(external_result['result_type'], 'estimated_system_fps')
                self.assertEqual(external_result['gpu_oriented_fps'], 325)
                self.assertIsNotNone(external_result['average_fps'])
                self.assertIsNone(external_result['one_percent_low'])
                self.assertIsNotNone(external_result['limiting_component'])
                gpu5090 = Hardware(type='GPU', name='GeForce RTX 5090', raw_score=60000,
                                   normalized_score=60000, vram=32)
                with Session(engine) as db:
                    db.add(gpu5090); db.commit(); gpu5090_id = gpu5090.id
                gaming = client.post('/api/fps/predict', json={
                    'cpu_id': cpu_id, 'gpu_id': gpu5090_id, 'game': 'Cyberpunk 2077',
                    'resolution': '1440p', 'preset': 'high',
                })
                self.assertEqual(gaming.status_code, 200, gaming.text)
                gaming_result = gaming.json()
                self.assertEqual(gaming_result['result_type'], 'estimated_system_fps')
                self.assertGreater(gaming_result['best_available_fps'], 0)
                self.assertEqual(gaming_result['gpu_reference_alternative']['gpu_oriented_fps'], 171)
                self.assertEqual(gaming_result['gpu_reference_alternative']['source_settings']['resolution'], '1440p')
                gpu_without_local_mark = Hardware(type='GPU', name='GeForce RTX 5090',
                                                  raw_score=0, normalized_score=0, vram=32)
                with Session(engine) as db:
                    db.add(gpu_without_local_mark); db.commit()
                    gpu_without_local_mark_id = gpu_without_local_mark.id
                crosswalk = client.post('/api/fps/predict', json={
                    'cpu_id': cpu_id, 'gpu_id': gpu_without_local_mark_id,
                    'game': 'Portal 2', 'resolution': '1080p', 'preset': 'high',
                })
                self.assertEqual(crosswalk.status_code, 200, crosswalk.text)
                crosswalk_result = crosswalk.json()
                self.assertEqual(crosswalk_result['result_type'], 'estimated_system_fps')
                self.assertGreater(crosswalk_result['best_available_fps'], 0)
                self.assertEqual(
                    crosswalk_result['technical_details']['gpu_estimate_details']['gpu_score_provenance']['source'],
                    'PCGameBenchmarks gpus.csv')
                coverage = client.get('/api/games/coverage').json()
                self.assertEqual(coverage['total_games'], coverage['selectable_games'])
                self.assertEqual(coverage['metadata_coverage']['steam_app_id'], 15439)
                self.assertEqual(coverage['benchmark_model_coverage']['native_pair_observations'], 4)
                external = coverage['external_fps_coverage']
                self.assertEqual(external['games_with_external_model_estimate'], 16441)
                adaptive = coverage['adaptive_strategy_coverage']
                self.assertEqual(adaptive['total_games'], 16447)
                self.assertEqual(adaptive['games_with_licensed_pair_measurements'], 1)
                self.assertEqual(adaptive['games_with_same_pair_resolution_interpolation'], 1)
                self.assertEqual(adaptive['games_with_legacy_system_estimate'], 19)
                self.assertEqual(adaptive['games_with_approximate_system_estimate'], 19)
                self.assertEqual(adaptive['games_with_external_gpu_curve'], 16441)
                self.assertEqual(adaptive['gpu_only_tier_games'], 16427)
                self.assertEqual(adaptive['games_without_title_specific_gpu_or_system_estimate'], 1)
                self.assertEqual(adaptive['external_model_estimate_records'], 197292)
                self.assertEqual(external['external_estimate_records'], 197292)
                self.assertEqual(external['full_system_predictions_from_external_model'], 0)
                self.assertEqual(external['cpu_bottleneck_predictions_from_external_model'], 0)
                cpu_resolution = coverage['cpu_requirement_resolution']
                self.assertLessEqual(cpu_resolution['games_with_any_requirement_reference'], 16441)
                self.assertGreaterEqual(cpu_resolution['minimum_fields_unresolved'], 0)
        finally:
            engine.dispose()


    def test_external_only_upgrader_does_not_promote_gpu_estimate_to_system_fps(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                cpu = Hardware(type='CPU', name='AMD Ryzen 5 5600', raw_score=21819, normalized_score=21819, cores=6, socket='AM4')
                gpu = Hardware(type='GPU', name='GeForce RTX 3060', raw_score=17008, normalized_score=17008, vram=12)
                db.add_all([cpu, gpu]); db.commit()
                request = CalculateRequest.model_validate({
                    'cpu_id': cpu.id, 'gpu_id': gpu.id, 'game': 'Portal 2',
                    'mode': '1080p_high', 'budget': 50000, 'target_fps': 60,
                })
                response = _post_calculate(request, db)
                self.assertIsNotNone(response.current_fps)
                self.assertIsNone(response.upgraded_fps)
                self.assertIsNotNone(response.bottleneck)
                self.assertIsNone(response.fps_v4_evidence['gain_fps'])
                evidence = response.fps_v4_evidence['current']
                self.assertEqual(evidence['status'], 'universal_fallback_estimate')
                self.assertEqual(evidence['gpu_oriented_fps'], 325)
                self.assertIsNotNone(evidence['average_fps'])
        finally:
            engine.dispose()

    def test_external_only_upgrader_reports_gpu_delta_without_system_fps(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                cpu = Hardware(type='CPU', name='AMD Ryzen 5 5600', raw_score=21819, normalized_score=21819, cores=6, socket='AM4')
                current_gpu = Hardware(type='GPU', name='GeForce RTX 3060', raw_score=17008, normalized_score=17008, vram=12)
                replacement_gpu = Hardware(type='GPU', name='GeForce RTX 4060', raw_score=19530, normalized_score=19530, vram=8)
                db.add_all([cpu, current_gpu, replacement_gpu]); db.commit()
                request = CalculateRequest.model_validate({
                    'cpu_id': cpu.id, 'gpu_id': current_gpu.id, 'game': 'Portal 2',
                    'mode': '1080p_high', 'budget': 50000, 'target_fps': 60,
                    'selected_upgrade_id': replacement_gpu.id,
                })
                response = _post_calculate(request, db)
                self.assertIsNotNone(response.current_fps)
                self.assertIsNotNone(response.upgraded_fps)
                evidence = response.fps_v4_evidence
                self.assertIsNotNone(evidence['gain_fps'])
                self.assertIsNone(evidence['gpu_oriented_gain_fps'])
                self.assertGreaterEqual(evidence['gain_fps'], 0)
                self.assertEqual(evidence['after']['gpu_oriented_fps'], 360)
        finally:
            engine.dispose()

    def test_builder_attaches_external_gpu_evidence_without_calling_it_system_fps(self):
        from contextlib import nullcontext
        from unittest.mock import patch
        from app.services.builds import assemble

        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                cpu = Hardware(type='CPU', name='AMD Ryzen 5 5600', raw_score=21819, normalized_score=21819, cores=6, socket='AM4')
                gpu = Hardware(type='GPU', name='GeForce RTX 3060', raw_score=17008, normalized_score=17008, vram=12)
                db.add_all([cpu, gpu]); db.commit()
                request = BuildRequest.model_validate({
                    'scenario': 'build', 'budget': 90000, 'game': 'Portal 2',
                    'mode': '1080p_high', 'socket': 'AM4', 'ram_type': 'DDR4',
                    'ram_capacity_gb': 16,
                })
                plan = {'parts': [
                    {'type': 'CPU', 'id': cpu.id, 'name': cpu.name},
                    {'type': 'GPU', 'id': gpu.id, 'name': gpu.name},
                ], 'alternatives': []}
                with (
                    patch('app.services.internal_offers.sync_internal', return_value=False),
                    patch('app.services.offer_geography.offer_scope', side_effect=lambda *_: nullcontext()),
                    patch('app.services.offer_geography.financial_evidence', side_effect=lambda result, *_: result),
                    patch('app.services.planning_prices.price_mode_scope', side_effect=lambda *_: nullcontext()),
                    patch('app.services.builds._assemble', return_value=plan),
                ):
                    result = assemble(request, db)
                evidence = result['fps_result']
                self.assertEqual(evidence['result_type'], 'estimated_system_fps')
                self.assertEqual(evidence['technical_details']['status'], 'universal_fallback_estimate')
                self.assertIsNotNone(evidence['average_fps'])
                self.assertEqual(evidence['gpu_oriented_fps'], 325)
                self.assertTrue(evidence['technical_details']['cpu_limit_assessed'])
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()

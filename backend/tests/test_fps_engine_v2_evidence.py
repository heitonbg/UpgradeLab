"""Regressions for source-backed FPS v2 and normalized benchmark storage."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.benchmarks import router as benchmark_router
from app.api.games import router as games_router
from app.api.deps import get_db
from app.db.migrations import migrate_benchmarks
from app.db.models import BenchmarkMeasurement, BenchmarkSource, Hardware
from app.services.benchmark_model_v2 import model_coverage, predict_pair
from app.services.benchmark_storage import import_curated_benchmarks


class EvidenceModelTests(unittest.TestCase):
    def test_exact_pair_result_has_source_and_measured_one_percent_low(self):
        result = predict_pair(
            'AMD Ryzen 9 9950X3D', 'GeForce RTX 5080', 'Cyberpunk 2077', '1440p', 'high',
            ram_type='DDR5', ram_channels=2, ram_capacity_gb=64)
        self.assertEqual(result['status'], 'measured_reference')
        self.assertEqual(result['measurement_type'], 'measured')
        self.assertAlmostEqual(result['average_fps'], 179.13, places=2)
        self.assertAlmostEqual(result['one_percent_low'], 136.21, places=2)
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['independent_series'], 1)
        self.assertEqual(result['sources'][0]['license'], 'CC-BY-4.0')

    def test_mismatched_ram_and_unmeasured_components_abstain(self):
        mismatch = predict_pair(
            'Ryzen 9 9950X3D', 'RTX 5080', 'Cyberpunk 2077', '1440p', 'high',
            ram_type='DDR4', ram_channels=2, ram_capacity_gb=64)
        unknown = predict_pair('Ryzen 5 5600', 'RTX 4060', 'Cyberpunk 2077', '1440p', 'high')
        self.assertEqual(mismatch['status'], 'insufficient_data')
        self.assertEqual(unknown['status'], 'insufficient_data')

    def test_target_outside_measured_resolution_range_is_not_extrapolated(self):
        result = predict_pair(
            'Ryzen 9 9950X3D', 'RTX 5080', 'Cyberpunk 2077', '720p', 'high',
            ram_type='DDR5', ram_channels=2, ram_capacity_gb=64)
        self.assertEqual(result['status'], 'insufficient_data')
        self.assertIn('экстраполяция запрещена', result['reason'])

    def test_leave_1440p_out_uses_frame_time_interpolation_from_real_1080p_and_4k(self):
        archive = json.loads((Path(__file__).resolve().parents[1] / 'app/data/benchmarks/measurements.json').read_text(encoding='utf-8'))
        rows = [row for row in archive['rows'] if row['resolution'] != '1440p']
        with patch('app.services.benchmark_model_v2.dataset', return_value=(rows, archive['sources'])):
            result = predict_pair(
                'Ryzen 9 9950X3D', 'RTX 5080', 'Cyberpunk 2077', '1440p', 'high',
                ram_type='DDR5', ram_channels=2, ram_capacity_gb=64)
        weight = ((2560 * 1440) - (1920 * 1080)) / ((3840 * 2160) - (1920 * 1080))
        expected = 1000 / ((1000 / 193.64) * (1 - weight) + (1000 / 91.48) * weight)
        self.assertEqual(result['status'], 'estimated_interpolation')
        self.assertEqual(result['measurement_type'], 'estimated')
        self.assertAlmostEqual(result['average_fps'], expected, places=2)
        self.assertEqual(result['interpolation']['anchors'][0]['resolution'], '1080p')
        self.assertEqual(result['interpolation']['anchors'][1]['resolution'], '4K')

    def test_v2_coverage_does_not_claim_calibrated_component_curves(self):
        coverage = model_coverage()
        self.assertEqual(coverage['native_pair_observations'], 4)
        self.assertEqual(coverage['paired_configurations'], 1)
        self.assertFalse(coverage['cpu_gpu_curves_calibrated'])

    def test_database_import_is_idempotent_and_retains_full_record(self):
        engine = create_engine('sqlite:///:memory:')
        try:
            migrate_benchmarks(engine)
            # Production SessionLocal disables autoflush; startup import must
            # remain idempotent when newly added sources are still pending.
            with Session(engine, autoflush=False) as db:
                first = import_curated_benchmarks(db)
                second = import_curated_benchmarks(db)
                self.assertEqual(first['inserted'], 87)
                self.assertEqual(first['total_records'], 87)
                self.assertEqual(second['inserted'], 0)
                self.assertEqual(second['unchanged'], 87)
                self.assertEqual(db.scalar(select(func.count()).select_from(BenchmarkSource)), first['total_sources'])
                row = db.scalar(select(BenchmarkMeasurement).where(
                    BenchmarkMeasurement.game == 'Cyberpunk 2077',
                    BenchmarkMeasurement.cpu == 'AMD Ryzen 9 9950X3D 16-Core Processor',
                    BenchmarkMeasurement.gpu == 'GeForce RTX 5080 Founders Edition'))
                data = json.loads(row.payload)
                self.assertTrue(data['source_url'].startswith('https://'))
                self.assertEqual(data['data_type'], 'measured')
                self.assertTrue(row.cpu_key and row.gpu_key)
        finally:
            engine.dispose()

    def test_import_refuses_to_overwrite_a_measurement_with_same_id(self):
        engine = create_engine('sqlite:///:memory:')
        migrate_benchmarks(engine)
        archive_path = Path(__file__).resolve().parents[1] / 'app/data/benchmarks/measurements.json'
        document = json.loads(archive_path.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            changed = json.loads(json.dumps(document))
            changed['rows'][0]['average_fps'] += 1
            changed_path = Path(directory) / 'changed.json'
            changed_path.write_text(json.dumps(changed), encoding='utf-8')
            try:
                with Session(engine) as db:
                    import_curated_benchmarks(db)
                    with self.assertRaisesRegex(ValueError, 'already exists'):
                        import_curated_benchmarks(db, changed_path)
                    self.assertEqual(db.scalar(select(func.count()).select_from(BenchmarkMeasurement)), 87)
            finally:
                engine.dispose()

    def test_api_reads_imported_measurements_and_reports_storage_counts(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        migrate_benchmarks(engine)
        with Session(engine) as db:
            import_curated_benchmarks(db)
        app = FastAPI()

        def database():
            with Session(engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        app.include_router(benchmark_router)
        try:
            with TestClient(app) as client:
                page = client.get('/api/benchmarks/measurements', params={'game': 'Cyberpunk', 'limit': 1})
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.json()['total'], 78)
                self.assertEqual(page.json()['items'][0]['data_type'], 'measured')
                info = client.get('/api/benchmarks/dataset-info').json()
                self.assertEqual(info['curated_measurements'], 87)
                self.assertEqual(info['stored_measurements'], 87)
                self.assertTrue(info['imported'])
        finally:
            engine.dispose()

    def test_fps_api_returns_baseline_and_measured_candidate_separately(self):
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Hardware.__table__.create(engine)
        with Session(engine) as db:
            cpu = Hardware(type='CPU', name='AMD Ryzen 9 9950X3D', raw_score=60000, normalized_score=60000)
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
                response = client.post('/api/fps/predict', json={
                    'cpu_id': cpu_id, 'gpu_id': gpu_id, 'game': 'Cyberpunk 2077',
                    'resolution': '1440p', 'preset': 'high', 'ram_type': 'DDR5',
                    'ram_channels': 2, 'ram_capacity_gb': 64})
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertEqual(payload['result_type'], 'measured_system_fps')
                self.assertEqual(payload['average_fps'], 179.13)
                self.assertEqual(payload['one_percent_low'], 136.21)
                self.assertEqual(payload['technical_details']['status'], 'measured_reference')
                self.assertIsNone(payload['limiting_component'])
                self.assertNotIn('candidate_v2', payload)
                self.assertNotIn('candidate_v3', payload)
                self.assertNotIn('candidate_v4', payload)
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()

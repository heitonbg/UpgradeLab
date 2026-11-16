"""Published measurements remain distinct from predicted FPS."""
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.benchmarks import game_reference, gpu_reference, list_benchmarks, router


class BenchmarkApiTests(unittest.TestCase):
    def test_measured_cohorts_have_sources_and_exact_settings(self):
        data = list_benchmarks(game='Cyberpunk', cpu='', gpu='', resolution='', limit=100, offset=0)
        self.assertEqual(data['measurement_type'], 'measured')
        self.assertGreater(data['total'], 0)
        for row in data['items']:
            self.assertGreater(row['mean_fps'], 0)
            self.assertTrue(row['source_urls'])
            self.assertIn('vram_gb', row['settings'])

    def test_missing_exact_pair_is_empty_not_a_model_guess(self):
        result = list_benchmarks(game='', cpu='Ryzen 5 5600', gpu='RTX 5060', resolution='', limit=50, offset=0)
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['items'], [])

    def test_pagination(self):
        first = list_benchmarks(game='', cpu='', gpu='', resolution='', limit=2, offset=0)
        second = list_benchmarks(game='', cpu='', gpu='', resolution='', limit=2, offset=2)
        self.assertEqual(first['total'], second['total'])
        self.assertNotEqual(first['items'], second['items'])

    def test_resolution_filter_accepts_pixel_dimensions_and_dataset_labels(self):
        by_label = list_benchmarks(game='', cpu='', gpu='', resolution='1080p', limit=100, offset=0)
        by_dimensions = list_benchmarks(game='', cpu='', gpu='', resolution='1920x1080', limit=100, offset=0)
        self.assertGreater(by_label['total'], 0)
        self.assertEqual(by_label['total'], by_dimensions['total'])
        self.assertEqual(by_label['items'], by_dimensions['items'])

        medians = game_reference(game='', resolution='1440p', preset='', limit=200)
        medians_by_dimensions = game_reference(game='', resolution='2560x1440', preset='', limit=200)
        self.assertEqual(medians['total'], medians_by_dimensions['total'])

        gpu_rows = gpu_reference(game='', gpu='', resolution='4K', preset='', limit=200)
        gpu_by_dimensions = gpu_reference(game='', gpu='', resolution='3840x2160', preset='', limit=200)
        self.assertEqual(gpu_rows['total'], gpu_by_dimensions['total'])

    def test_fpshq_references_are_separate_and_attributed(self):
        medians = game_reference(game='', resolution='', preset='', limit=200)
        self.assertEqual(medians['measurement_type'], 'publisher_aggregate')
        self.assertEqual(medians['license'], 'CC BY 4.0')
        self.assertEqual(medians['total'], 195)
        self.assertFalse(medians['exact_pair_supported'])

        gpu_rows = gpu_reference(game='', gpu='', resolution='', preset='', limit=200)
        self.assertEqual(gpu_rows['measurement_type'], 'review_aggregate')
        self.assertEqual(gpu_rows['license'], 'CC BY 4.0')
        self.assertEqual(gpu_rows['total'], 728)
        self.assertFalse(gpu_rows['exact_pair_supported'])
        self.assertTrue(all(row['basis'] == 'review_aggregate' and row['url'] for row in gpu_rows['items']))

    def test_http_route_validates_limit_without_database(self):
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        self.assertEqual(client.get('/api/benchmarks', params={'limit': 1000}).status_code, 422)
        self.assertEqual(client.get('/api/benchmarks').status_code, 200)


    def test_reference_table_can_filter_all_fpshq_row_types(self):
        all_rows = gpu_reference(game='', gpu='', resolution='', preset='', source='any', limit=50, offset=0)
        self.assertEqual(all_rows['measurement_type'], 'mixed_gpu_reference')
        self.assertEqual(all_rows['total'], 2400)
        self.assertEqual({gpu_reference(game='', gpu='', resolution='', preset='', source=kind, limit=1, offset=0)['items'][0]['data_type'] for kind in ('measured', 'aggregate', 'model')}, {'measured', 'aggregate', 'model'})
        modeled = gpu_reference(game='', gpu='', resolution='', preset='', source='model', limit=50, offset=0)
        self.assertEqual(modeled['total'], 1666)

    def test_gpu_reference_table_sorts_all_filtered_rows_before_pagination(self):
        result = gpu_reference(game='Cyberpunk 2077', gpu='', resolution='1440p', preset='', source='any', sort='fps_desc', limit=10, offset=0)
        values = [row['average_fps'] for row in result['items']]
        self.assertEqual(values, sorted(values, reverse=True))

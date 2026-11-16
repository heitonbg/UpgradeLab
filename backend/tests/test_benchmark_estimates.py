"""Protect preset, resolution and GPU distinctions in published sample use."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.benchmark_estimates import benchmark_reference, datasets
from app.services.performance import fps_outlook
from app.schemas.calculate import GameName, CalcMode


class BenchmarkEstimateTests(unittest.TestCase):
    def test_exact_high_and_derived_qhd_have_different_provenance(self):
        high = benchmark_reference('GeForce RTX 3060', "Baldur's Gate 3", '1080p_high')
        qhd = benchmark_reference('GeForce RTX 3060', "Baldur's Gate 3", '1440p_high')
        self.assertEqual(high['fps'], 86.7)
        self.assertFalse(high['interpolated'])
        self.assertFalse(high['derived'])
        self.assertTrue(qhd['derived'])
        self.assertAlmostEqual(qhd['fps'], 86.7 * 59.4 / 85.45)
        self.assertEqual(len(qhd['sources']), 3)
        self.assertIn('Ultra', qhd['sources'][-1]['settings'])

    def test_720p_and_ray_tracing_samples_do_not_become_native_raster_samples(self):
        self.assertIsNone(benchmark_reference('GeForce RTX 3060', 'Forza Horizon 5', '1080p_low'))
        data = datasets()['Resident Evil 4 Remake']
        self.assertTrue(all(not sample.get('1440p_ultra') for sample in data['samples']))
        result = benchmark_reference('GeForce RTX 4060', 'Resident Evil 4 Remake', '1440p_high')
        self.assertTrue(result['derived'])
        self.assertEqual(len(result['sources']), 1)
        self.assertNotIn('Max', result['sources'][0]['settings'])

    def test_mobile_and_different_memory_variants_do_not_inherit_a_desktop_measurement(self):
        self.assertIsNone(benchmark_reference('GeForce RTX 3060 Laptop', "Baldur's Gate 3", '1080p_high'))
        sample = benchmark_reference('GeForce RTX 3060 8GB', "Baldur's Gate 3", '1080p_high', 15000)
        self.assertTrue(sample['interpolated'])
        self.assertFalse(any(point['gpu'] == 'GeForce RTX 3060' for point in sample['sources']))

    def test_tank_requirements_are_not_presented_as_fps_measurements(self):
        outlook = fps_outlook(70, 'GeForce RTX 3060', GameName.MIR_TANKOV, CalcMode.MODE_1080P_HIGH)
        self.assertEqual(outlook['data_quality'], 'model_only')
        self.assertEqual(outlook['sources'], [])
        self.assertTrue(outlook['context_sources'])


if __name__ == '__main__':
    unittest.main()

    def test_rtx_5090d_cyberpunk_qhd_uses_real_gpu_reference_without_calling_it_pair_fps(self):
        reference = benchmark_reference('GeForce RTX 5090 D', 'Cyberpunk 2077', '1440p_high')
        self.assertEqual(reference['fps'], 171)
        self.assertTrue(reference['gpu_reference'])
        self.assertFalse(reference['exact_gpu'])
        self.assertIn('not a CPU/GPU system test', reference['note'])

    def test_4k_high_has_a_supported_estimate_profile(self):
        from app.core.constants import GAME_PROFILES
        from app.services.performance import estimate_fps
        from app.schemas.calculate import GameName, CalcMode
        self.assertIn(CalcMode.MODE_4K_HIGH, GAME_PROFILES[GameName.CYBERPUNK])
        value = estimate_fps(25000, 220000, 'GeForce RTX 5090', GameName.CYBERPUNK, CalcMode.MODE_4K_HIGH, 1, 'Ryzen 5 5600')
        self.assertGreater(value, 0)

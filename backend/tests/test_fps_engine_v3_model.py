import unittest

from app.services.fps_engine_v3 import CpuHardware, GpuHardware, GameWorkload, parallel_efficiency, predict_fps


class FpsEngineV3Tests(unittest.TestCase):
    def setUp(self):
        self.cpu = CpuHardware(single_thread_index=100, performance_cores=6, threads=12)
        self.gpu = GpuHardware(compute_index=100, bandwidth_gbps=500, texture_rate=100, pixel_rate=80)
        self.work = GameWorkload(serial_work_ms_index=500, parallel_work_ms_index=300,
            compute_work_ms_index=600, memory_work_ms_index=100, texture_work_ms_index=80,
            pixel_alpha=0.5, extra_ms=1, confidence='experimental')

    def test_unknown_workload_abstains(self):
        result = predict_fps(self.cpu, self.gpu, GameWorkload(), '1080p')
        self.assertIsNone(result['fps'])
        self.assertEqual(result['confidence'], 'insufficient_data')

    def test_cpu_gpu_frame_time_and_bottleneck(self):
        result = predict_fps(self.cpu, self.gpu, self.work, '1080p')
        self.assertGreater(result['fps'], 0)
        self.assertEqual(result['bottleneck'], 'GPU')
        self.assertAlmostEqual(result['fps'], 1000/(6+1), places=1)

    def test_higher_resolution_does_not_improve_fps(self):
        low = predict_fps(self.cpu, self.gpu, self.work, '1080p')
        high = predict_fps(self.cpu, self.gpu, self.work, '4K')
        self.assertLessEqual(high['fps'], low['fps'])

    def test_ram_is_not_an_input_and_rt_abstains_without_rt_calibration(self):
        result = predict_fps(self.cpu, self.gpu, self.work, '1440p', rt=True)
        self.assertIsNone(result['fps'])
        self.assertIn('calibrated RT workload and RT hardware throughput', result['missing_inputs'])

    def test_parallel_scaling_is_sublinear(self):
        self.assertLess(parallel_efficiency(16, 0, 32), 16)


if __name__ == '__main__':
    unittest.main()

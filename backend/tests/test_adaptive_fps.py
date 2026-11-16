import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.adaptive_fps import (
    adaptive_game_coverage, compare_adaptive_results, _predict_adaptive_evidence as predict_adaptive_fps,
)


class AdaptiveFpsServiceTests(unittest.TestCase):
    def setUp(self):
        self.cpu = SimpleNamespace(name="AMD Ryzen 9 9950X3D", raw_score=60000, cores=16, socket="AM5")
        self.gpu = SimpleNamespace(name="GeForce RTX 5080", raw_score=80000, vram=16)

    def test_exact_pair_measurement_is_the_single_system_result(self):
        result = predict_adaptive_fps(self.cpu, self.gpu, "Cyberpunk 2077",
                                     {"resolution": "1440p", "preset": "high"})
        self.assertEqual(result["result_type"], "measured_system_fps")
        self.assertEqual(result["average_fps"], 179.13)
        self.assertEqual(result["one_percent_low"], 136.21)
        self.assertIsNone(result["limiting_component"])
        self.assertEqual(result["technical_details"]["status"], "measured_reference")

    def test_resolution_interpolation_is_estimated_not_measured(self):
        from app.services.benchmark_model_v2 import dataset
        rows, _ = dataset()
        training = [row for row in rows if row.get("resolution") != "1440p"]
        from app.services.fps_engine_v4 import resolve_fps_v4
        evidence = resolve_fps_v4(self.cpu, self.gpu, "Cyberpunk 2077", "1440p", "high",
                                  measurement_rows=training)
        from app.services.adaptive_fps import present_adaptive_result
        result = present_adaptive_result(evidence, {"resolution": "1440p", "preset": "high"})
        self.assertEqual(result["result_type"], "estimated_system_fps")
        self.assertEqual(result["average_fps"], 150.16)
        self.assertIsNone(result["one_percent_low"])
        self.assertEqual(result["technical_details"]["status"], "estimated_interpolation")

    def test_legacy_estimate_is_independent_of_ram_fields(self):
        cpu = SimpleNamespace(name="AMD Ryzen 5 5600", raw_score=21819)
        gpu = SimpleNamespace(name="GeForce RTX 4060", raw_score=19500, vram=8)
        plain = predict_adaptive_fps(cpu, gpu, "CS2", {"resolution": "1080p", "preset": "low"})
        with_ignored_ram = predict_adaptive_fps(cpu, gpu, "CS2", {
            "resolution": "1080p", "preset": "low", "ram_type": "DDR5",
            "ram_channels": 1, "ram_capacity_gb": 8,
        })
        self.assertEqual(plain["result_type"], "estimated_system_fps")
        self.assertEqual(plain["average_fps"], with_ignored_ram["average_fps"])
        self.assertEqual(with_ignored_ram["settings"]["ram_type"], "DDR5")
        self.assertFalse(with_ignored_ram["ram_used_by_model"])

    def test_known_ram_mismatch_does_not_reuse_a_measured_pair(self):
        result = predict_adaptive_fps(self.cpu, self.gpu, "Cyberpunk 2077", {
            "resolution": "1440p", "preset": "high", "ram_type": "DDR4",
            "ram_capacity_gb": 16, "ram_channels": 2,
        })
        self.assertNotEqual(result["result_type"], "measured_system_fps")

    def test_external_gpu_estimate_never_becomes_system_fps(self):
        cpu = SimpleNamespace(name="AMD Ryzen 5 5600", raw_score=21819)
        gpu = SimpleNamespace(name="GeForce RTX 3060", raw_score=17008, vram=12)
        result = predict_adaptive_fps(cpu, gpu, "Portal 2", {"resolution": "1080p", "preset": "high"})
        self.assertEqual(result["result_type"], "gpu_reference_only")
        self.assertEqual(result["gpu_oriented_fps"], 325)
        self.assertIsNone(result["average_fps"])
        self.assertIsNone(result["limiting_component"])
        unsupported = predict_adaptive_fps(cpu, gpu, "Portal 2", {"resolution": "1440p", "preset": "high"})
        self.assertEqual(unsupported["result_type"], "gpu_reference_only")
        self.assertIsNotNone(unsupported["gpu_oriented_fps"])
        self.assertEqual(unsupported["settings"]["resolution"], "1440p")
        self.assertEqual(unsupported["source_settings"]["resolution"], "1080p")
        self.assertIsNotNone(unsupported["best_available_fps"])

    def test_scenario_is_attached_without_promoting_gpu_reference_to_system_fps(self):
        raw = {"status": "external_model_anchored", "average_fps": None,
               "gpu_oriented_fps": 120, "game": "Scenario Game", "settings": {
                   "resolution": "1080p", "preset": "high", "rt": False,
                   "upscaling": "off", "frame_generation": False},
               "gpu_estimate_details": {"available": True, "fps": 120,
                   "unrounded_fps": 120.0, "source_name": "PCGameBenchmarks",
                   "data_type": "external_model_estimate"}}
        scenario = {"available": True, "data_type": "experimental_requirements_anchored_estimate",
                    "scenario_fps": 105.0, "one_percent_low": None, "ram_used_by_model": False}
        with patch("app.services.adaptive_fps.resolve_fps_v4", return_value=raw), \
             patch("app.services.adaptive_fps._external_profile_for_game", return_value={"game_id": "Scenario Game"}), \
             patch("app.services.adaptive_fps.estimate_requirements_anchored_fps", return_value=scenario):
            result = predict_adaptive_fps(self.cpu, self.gpu, "Scenario Game", {
                "resolution": "1080p", "preset": "high"},
                cpu_catalog=[self.cpu], gpu_catalog=[self.gpu])
        self.assertEqual(result["result_type"], "gpu_reference_only")
        self.assertIsNone(result["average_fps"])
        self.assertEqual(result["gpu_oriented_fps"], 120)
        self.assertEqual(result["requirements_anchored_estimate"]["scenario_fps"], 105.0)
        self.assertEqual(result["technical_details"]["requirements_anchored_estimate"]["scenario_fps"], 105.0)

    def test_scenario_gain_is_separate_from_measured_and_gpu_only_gain(self):
        before = {"result_type": "gpu_reference_only", "game": "X", "settings": {"resolution": "1080p"},
                  "requirements_anchored_estimate": {"available": True, "model_version": "v1", "scenario_fps": 80}}
        after = {"result_type": "gpu_reference_only", "game": "X", "settings": {"resolution": "1080p"},
                 "requirements_anchored_estimate": {"available": True, "model_version": "v1", "scenario_fps": 93}}
        result = compare_adaptive_results(before, after)
        self.assertIsNone(result["gain_fps"])
        self.assertIsNone(result["gpu_oriented_gain_fps"])
        self.assertEqual(result["requirements_anchored_scenario_gain_fps"], 13)

    def test_unknown_game_still_has_a_numeric_catalog_gpu_reference(self):
        result = predict_adaptive_fps(self.cpu, self.gpu, "Unmatched Test Game", {
            "resolution": "1440p", "preset": "high"})
        self.assertEqual(result["result_type"], "gpu_reference_only")
        self.assertIsNone(result["average_fps"])
        self.assertIsNotNone(result["gpu_oriented_fps"])
        self.assertEqual(result["technical_details"]["status"], "catalog_gpu_reference_only")
        self.assertGreater(result["gpu_oriented_fps"], 0)
        self.assertEqual(result["best_available_fps"], result["gpu_oriented_fps"])
        self.assertEqual(result["best_available_fps_basis"], "gpu_reference_only")

    def test_unknown_game_returns_a_labeled_number_for_every_supported_resolution(self):
        for resolution in ("1080p", "1440p", "4K"):
            with self.subTest(resolution=resolution):
                result = predict_adaptive_fps(self.cpu, self.gpu, "No Catalog Match", {
                    "resolution": resolution, "preset": "high"})
                self.assertGreater(result["best_available_fps"], 0)
                self.assertEqual(result["best_available_fps_basis"], "gpu_reference_only")
                self.assertIsNone(result["average_fps"])
                self.assertEqual(result["settings"]["resolution"], resolution)
                self.assertIsNotNone(result["source_settings"]["resolution"])

    def test_legacy_system_estimate_also_exposes_fpshq_gpu_reference_for_5090(self):
        cpu = SimpleNamespace(name="AMD Ryzen 5 5600", raw_score=21819)
        gpu = SimpleNamespace(name="GeForce RTX 5090", raw_score=60000, vram=32)
        result = predict_adaptive_fps(cpu, gpu, "Cyberpunk 2077", {
            "resolution": "1440p", "preset": "high"})
        self.assertEqual(result["result_type"], "estimated_system_fps")
        self.assertEqual(result["average_fps"], 166)
        alternative = result["gpu_reference_alternative"]
        self.assertEqual(alternative["gpu_oriented_fps"], 171)
        self.assertEqual(alternative["source_name"], "FPSHQ")
        self.assertEqual(alternative["source_settings"]["resolution"], "1440p")

    def test_changed_gpu_has_separate_fpshq_delta(self):
        cpu = SimpleNamespace(name="AMD Ryzen 5 5600", raw_score=21819)
        first_gpu = SimpleNamespace(name="GeForce RTX 5090", raw_score=60000, vram=32)
        second_gpu = SimpleNamespace(name="GeForce RTX 5080", raw_score=55000, vram=16)
        settings = {"resolution": "1440p", "preset": "high"}
        before = predict_adaptive_fps(cpu, first_gpu, "Cyberpunk 2077", settings)
        after = predict_adaptive_fps(cpu, second_gpu, "Cyberpunk 2077", settings)
        comparison = compare_adaptive_results(before, after)
        self.assertIsNotNone(comparison["gpu_reference_alternative_gain_fps"])

    def test_cpu_change_does_not_report_unchanged_gpu_reference_as_gain(self):
        cpu_before = SimpleNamespace(name="AMD Ryzen 5 5600", raw_score=21819)
        cpu_after = SimpleNamespace(name="AMD Ryzen 7 7800X3D", raw_score=34000)
        gpu = SimpleNamespace(name="GeForce RTX 3060", raw_score=17008, vram=12)
        settings = {"resolution": "1080p", "preset": "high"}
        before = predict_adaptive_fps(cpu_before, gpu, "Portal 2", settings)
        after = predict_adaptive_fps(cpu_after, gpu, "Portal 2", settings)
        comparison = compare_adaptive_results(before, after)
        self.assertIsNone(comparison["gain_fps"])
        self.assertIsNone(comparison["gpu_oriented_gain_fps"])

    def test_game_coverage_counts_tiers_without_claiming_full_system_coverage(self):
        coverage = adaptive_game_coverage()
        self.assertEqual(coverage["total_games"], 16447)
        self.assertEqual(coverage["games_with_licensed_pair_measurements"], 1)
        self.assertEqual(coverage["games_with_same_pair_resolution_interpolation"], 1)
        self.assertEqual(coverage["games_with_legacy_system_estimate"], 19)
        self.assertEqual(coverage["games_with_approximate_system_estimate"], 19)
        self.assertEqual(coverage["games_with_external_gpu_curve"], 16441)
        self.assertEqual(coverage["gpu_only_tier_games"], 16427)
        self.assertEqual(coverage["games_without_title_specific_gpu_or_system_estimate"], 1)
        self.assertEqual(coverage["games_with_generic_gpu_catalog_reference_available"], 16447)
        self.assertEqual(coverage["external_model_estimate_records"], 197292)


if __name__ == "__main__":
    unittest.main()

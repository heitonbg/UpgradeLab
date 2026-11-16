from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.requirements_anchored_fps import estimate_requirements_anchored_fps


class RequirementsAnchoredFpsTests(unittest.TestCase):
    def setUp(self):
        self.cpus = [
            SimpleNamespace(id=1, name="Intel Core i7-12700", raw_score=29738, type="CPU"),
            SimpleNamespace(id=2, name="AMD Ryzen 7 7800X3D", raw_score=39419, type="CPU"),
            SimpleNamespace(id=3, name="Intel Core i5-12400F", raw_score=19500, type="CPU"),
        ]
        self.gpus = [
            SimpleNamespace(id=11, name="GeForce RTX 2060 SUPER", raw_score=16500, type="GPU"),
            SimpleNamespace(id=12, name="Radeon RX 5700 XT", raw_score=17500, type="GPU"),
            SimpleNamespace(id=13, name="Arc A770", raw_score=18000, type="GPU"),
            SimpleNamespace(id=14, name="GeForce RTX 4090", raw_score=39000, type="GPU"),
        ]
        self.profile = {
            "game_id": "game:test", "catalog_name": "Test Game",
            "source_url": "https://example.invalid/game",
            "data_type": "external_model_estimate",
            "recommended_requirements": {
                "cpu": "Core i7-12700 or Ryzen 7 7800X3D",
                "gpu": "GeForce RTX 2060 SUPER or Radeon RX 5700 XT or Arc A770",
            },
            "fps_by_reference_gpu": {
                "GeForce GTX 1650": 48, "GeForce RTX 3060": 92,
                "GeForce RTX 4060": 114, "GeForce RTX 4090": 160,
            },
        }
        self.base = {"available": True, "fps": 92, "unrounded_fps": 91.6,
                     "target_g3d_score": 17000, "device_class": "desktop",
                     "min_curve_log_elasticity": 0.25, "source_name": "PCGameBenchmarks",
                     "data_type": "external_model_estimate", "source_url": self.profile["source_url"]}

    def estimate(self, cpu=None, gpu=None, profile=None, base=None):
        return estimate_requirements_anchored_fps(
            profile or self.profile, cpu or self.cpus[0], gpu or self.gpus[0],
            self.cpus, self.gpus, base or self.base,
        )

    def test_exact_recommended_alternatives_produce_labeled_scenario(self):
        result = self.estimate()
        self.assertTrue(result["available"])
        self.assertEqual(result["data_type"], "experimental_requirements_anchored_estimate")
        self.assertGreater(result["scenario_fps"], 0)
        self.assertIsNone(result["one_percent_low"])
        self.assertEqual(len(result["reference_cpu_models"]), 2)
        self.assertEqual(len(result["reference_gpu_models"]), 3)
        self.assertEqual(result["ram_used_by_model"], False)

    def test_minimum_exact_requirements_are_used_if_recommended_names_are_unresolved(self):
        profile = {**self.profile,
            "recommended_requirements": {"cpu": "Unknown CPU 9000", "gpu": "Unknown GPU 9000"},
            "minimum_requirements": {"cpu": "Core i5-12400F", "gpu": "GeForce RTX 2060 SUPER"}}
        result = self.estimate(profile=profile)
        self.assertTrue(result["available"])
        self.assertEqual(result["requirements"]["level"], "minimum")
        self.assertEqual(result["confidence"], "very_low")

    def test_fpshq_gpu_reference_can_anchor_labeled_experimental_scenario(self):
        base = {**self.base, "source_name": "FPSHQ", "data_type": "external_model_estimate",
                "source_settings": {"resolution": "1440p", "preset": "High", "rt": False,
                                    "upscaling": "off", "frame_generation": False},
                "license": "CC BY 4.0"}
        result = self.estimate(base=base)
        self.assertTrue(result["available"])
        self.assertEqual(result["gpu_baseline"]["source_name"], "FPSHQ")
        self.assertEqual(result["gpu_baseline"]["license"], "CC BY 4.0")

    def test_unresolved_requirement_alternative_abstains(self):
        profile = {**self.profile, "recommended_requirements": {
            "cpu": "Core i7-12700 or Ryzen 9 99999", "gpu": "RTX 2060 SUPER"}}
        result = self.estimate(profile=profile)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "recommended_cpu_not_fully_resolved")

    def test_gpu_requirement_requires_exact_catalog_crosswalk(self):
        profile = {**self.profile, "recommended_requirements": {
            "cpu": "Core i7-12700", "gpu": "NVIDIA RTX 20-series"}}
        result = self.estimate(profile=profile)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "recommended_gpu_not_exactly_resolved")

    def test_requirement_without_vram_abstains_when_catalog_has_multiple_vram_skus(self):
        from app.services.requirements_anchored_fps import resolve_gpu_requirement
        catalog = [
            SimpleNamespace(id=1, name="GeForce RTX 3060 8GB", raw_score=16000, type="GPU"),
            SimpleNamespace(id=2, name="GeForce RTX 3060 12GB", raw_score=19000, type="GPU"),
        ]
        result = resolve_gpu_requirement("GeForce RTX 3060", catalog)
        self.assertEqual(result["status"], "unmatched")
        self.assertEqual(result["unresolved_models"][0]["reason"], "ambiguous_vram_variant_in_catalog")

    def test_mapping_catalog_rows_are_supported(self):
        from app.services.requirements_anchored_fps import resolve_gpu_requirement
        result = resolve_gpu_requirement("GeForce RTX 2060 SUPER", [
            {"id": 11, "name": "GeForce RTX 2060 SUPER", "raw_score": 16500, "type": "GPU"},
        ])
        self.assertEqual(result["status"], "resolved_exact_models")

    def test_missing_gpu_baseline_abstains(self):
        result = self.estimate(base={"available": False, "reason": "no_curve"})
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "gpu_reference_estimate_unavailable")

    def test_weak_cpu_reduces_scenario_relative_to_reference(self):
        fast = self.estimate(cpu=self.cpus[1])
        slow = self.estimate(cpu=self.cpus[2])
        self.assertLess(slow["scenario_fps"], fast["scenario_fps"])

    def test_faster_gpu_never_reduces_fps_on_capped_curve(self):
        base_fast_gpu = {**self.base, "unrounded_fps": 160.0, "fps": 160,
                         "target_g3d_score": 39000, "min_curve_log_elasticity": 0.25}
        slow_cpu_result = self.estimate(cpu=self.cpus[2])
        fast_cpu_result = estimate_requirements_anchored_fps(
            self.profile, self.cpus[2], self.gpus[3], self.cpus, self.gpus,
            base_fast_gpu,
        )
        self.assertGreaterEqual(fast_cpu_result["scenario_fps"], slow_cpu_result["scenario_fps"])

    def test_future_or_lower_gpu_score_inputs_remain_finite_and_monotone(self):
        scores = [12000, 15000, 17000, 20000, 26000, 39000]
        results = []
        for score in scores:
            base = {**self.base, "target_g3d_score": score,
                    "unrounded_fps": min(160.0, 30.0 + score / 400.0),
                    "min_curve_log_elasticity": 0.25}
            results.append(estimate_requirements_anchored_fps(
                self.profile, self.cpus[2], SimpleNamespace(name="GPU", raw_score=score, type="GPU"),
                self.cpus, self.gpus, base,
            )["scenario_fps"])
        self.assertTrue(all(a <= b for a, b in zip(results, results[1:])))

    def test_no_scenario_if_selected_hardware_is_invalid(self):
        gpu = SimpleNamespace(name="Unknown", raw_score=0, type="GPU")
        result = self.estimate(gpu=gpu)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "selected_hardware_score_missing")


if __name__ == "__main__":
    unittest.main()

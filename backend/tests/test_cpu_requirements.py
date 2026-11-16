from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.cpu_requirements import (
    CpuRequirementResolver, assess_cpu_adequacy, parse_cpu_requirement,
    resolve_cpu_requirement,
)


class CpuRequirementResolverTests(unittest.TestCase):
    def setUp(self):
        self.cpus = [
            SimpleNamespace(id=1, name="Intel Core i7-12700", raw_score=24000),
            SimpleNamespace(id=2, name="AMD Ryzen 7 7800X3D", raw_score=36000),
            SimpleNamespace(id=3, name="Intel Core i5-8400", raw_score=9000),
            SimpleNamespace(id=4, name="Intel Core i5-8600K", raw_score=10000),
            SimpleNamespace(id=5, name="Intel Core i5-9400F", raw_score=11000),
            SimpleNamespace(id=6, name="AMD Ryzen 5 5600", raw_score=20000),
        ]

    def test_exact_models_and_or_alternatives_match_only_exact_catalog_names(self):
        result = resolve_cpu_requirement("Core i7-12700 or Ryzen 7 7800X3D", self.cpus)
        self.assertEqual(result["status"], "resolved_exact_models")
        self.assertEqual({row["id"] for row in result["resolved_models"]}, {1, 2})
        self.assertEqual(result["reference_cpu_mark_range"], [24000, 36000])
        self.assertEqual(result["match_confidence"], "high")

    def test_vendor_prefix_frequency_suffix_and_spaced_apu_suffix_normalize_to_exact_sku(self):
        catalog = [
            SimpleNamespace(id=10, name="Intel Core i7-12700 @ 2.10GHz", raw_score=24000),
            SimpleNamespace(id=11, name="Intel Core i7-12700 Processor", raw_score=24000),
            SimpleNamespace(id=12, name="AMD Ryzen 5 2400G 4-Core Processor", raw_score=7000),
        ]
        intel = resolve_cpu_requirement("Intel Core i7 12700", catalog)
        apu = resolve_cpu_requirement("AMD Ryzen 5 2400 G", catalog)
        self.assertEqual(intel["status"], "resolved_exact_models")
        self.assertEqual(intel["resolved_models"][0]["catalog_entry_count"], 2)
        self.assertEqual(intel["resolved_models"][0]["cpu_mark_range"], [24000.0, 24000.0])
        self.assertEqual(apu["resolved_models"][0]["name"], "AMD Ryzen 5 2400G 4-Core Processor")

    def test_series_requirement_is_a_generation_range_not_a_fake_exact_sku(self):
        parsed = parse_cpu_requirement("Intel Core i5 4000 series")
        self.assertEqual(parsed["parse_type"], "family_with_generation")
        self.assertEqual(parsed["models"], [])
        self.assertEqual(parsed["families"], [{"vendor": "intel", "family": "i5", "generation": 4}])

    def test_missing_or_partial_exact_match_is_not_replaced_by_a_nearby_cpu(self):
        resolver = CpuRequirementResolver(self.cpus)
        missing = resolver.resolve("Core i9-14900K")
        self.assertEqual(missing["status"], "unmatched")
        self.assertEqual(missing["resolved_models"], [])
        self.assertEqual(missing["unresolved_models"][0]["reason"], "model_not_in_catalog")
        partial = resolver.resolve("Core i7-12700 or Ryzen 9 9950X")
        self.assertEqual(partial["status"], "partially_resolved")
        self.assertEqual([row["id"] for row in partial["resolved_models"]], [1])

    def test_family_with_generation_reports_a_range_instead_of_selecting_one_sku(self):
        result = resolve_cpu_requirement("Intel Core i5 (8th Generation)", self.cpus)
        self.assertEqual(result["status"], "resolved_family_range")
        self.assertEqual({row["id"] for row in result["resolved_models"]}, {3, 4})
        self.assertEqual(result["reference_cpu_mark_range"], [9000, 10000])
        self.assertEqual(result["match_confidence"], "low")

    def test_family_without_generation_and_abstract_requirements_remain_unresolved(self):
        broad = resolve_cpu_requirement("Intel Core i5", self.cpus)
        abstract = resolve_cpu_requirement("Quad-core Intel or AMD CPU at 3 GHz", self.cpus)
        self.assertEqual(broad["status"], "unresolved_family")
        self.assertEqual(abstract["status"], "abstract_requirement")
        self.assertEqual(abstract["resolved_models"], [])
        self.assertEqual(parse_cpu_requirement("Quad-core CPU")["parse_type"], "abstract_requirement")

    def test_adequacy_is_a_requirements_relative_cpu_mark_index_not_fps(self):
        profile = {
            "catalog_name": "Test Game",
            "source_url": "https://pcgamebenchmarks.com/game/test",
            "minimum_requirements": {"cpu": "Intel Core i5-8400"},
            "recommended_requirements": {"cpu": "Intel Core i7-12700 or Ryzen 7 7800X3D"},
        }
        low = assess_cpu_adequacy(profile, self.cpus[-1], self.cpus)
        high_cpu = SimpleNamespace(name="AMD Ryzen 7 7800X3D", raw_score=36000)
        high = assess_cpu_adequacy(profile, high_cpu, self.cpus)
        self.assertTrue(low["available"])
        self.assertLess(low["recommended"]["index_vs_reference_percent"],
                        high["recommended"]["index_vs_reference_percent"])
        self.assertEqual(low["minimum"]["reference_cpu_mark"], 9000)
        self.assertEqual(low["minimum"]["index_vs_reference_percent"], 222.2)
        self.assertNotIn("fps", low)
        self.assertIn("не Single Thread", low["note"])

    def test_adequacy_index_changes_continuously_and_preserves_alternative_spread(self):
        profile = {
            "minimum_requirements": {"cpu": "Intel Core i5-8400"},
            "recommended_requirements": {"cpu": "Core i7-12700 or Ryzen 7 7800X3D"},
        }
        first = assess_cpu_adequacy(profile, SimpleNamespace(name="CPU A", raw_score=30000), self.cpus)
        nearby = assess_cpu_adequacy(profile, SimpleNamespace(name="CPU B", raw_score=30100), self.cpus)
        first_index = first["recommended"]["index_vs_reference_percent"]
        nearby_index = nearby["recommended"]["index_vs_reference_percent"]
        self.assertAlmostEqual(first_index, 100.0)
        self.assertAlmostEqual(nearby_index - first_index, 0.3, places=1)
        self.assertEqual(first["recommended"]["range_vs_reference_percent"], [83.3, 125.0])
        self.assertNotIn("fps", first)

    def test_cpu_mark_comparison_has_no_catalog_match_when_catalog_is_missing(self):
        profile = {"minimum_requirements": {"cpu": "Intel Core i7-12700"}}
        result = assess_cpu_adequacy(profile, self.cpus[0], [])
        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "unresolved_requirements")
        self.assertEqual(result["unresolved_reference_models"][0]["reason"], "model_not_in_catalog")


if __name__ == "__main__":
    unittest.main()

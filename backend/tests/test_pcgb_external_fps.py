from __future__ import annotations

import importlib.util
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.external_fps_model import estimate_gpu_fps, gpu_device_class, match_source_gpu, package, profiles_by_id
from app.services.cpu_requirements import assess_cpu_adequacy
from app.services.fps_engine_v4 import resolve_fps_v4
from app.services.game_catalog import catalog


class PcGameBenchmarksPackageTests(unittest.TestCase):
    def test_pinned_source_provenance_and_full_import_counts(self):
        source = package()["source"]
        report_path = BACKEND / "app" / "data" / "external_fps" / "pcgamebenchmarks" / "import_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        profiles = profiles_by_id()
        self.assertEqual(source["license"], "CC BY 4.0")
        self.assertEqual(len(package()["gpu_catalog"]), 1381)
        self.assertEqual(source["data_type"], "external_model_estimate")
        self.assertEqual(source["git_revision"], "299e6f38ed48eda91235bbc451096f5e6fd62910")
        self.assertEqual(report["runtime_catalog_games"], 16447)
        self.assertEqual(report["source_games"], 16623)
        self.assertEqual(report["matched_games"], len(profiles))
        self.assertEqual(report["matched_games"], 16441)
        self.assertEqual(report["external_model_estimate_records"], 197292)
        self.assertEqual(report["source_reference_gpus"], 12)
        self.assertEqual(report["source_gpu_catalog_rows"], 1381)
        self.assertEqual(report["source_gpu_catalog_type_counts"]["Desktop"], 433)
        self.assertEqual(report["invalid_fps_points_skipped"], 0)
        self.assertEqual(report["non_monotonic_games_rejected"], 0)
        self.assertEqual(sum(report["match_method_counts"].values()), 16441)
        self.assertIn("https://github.com/emilioagustin83/pc-game-fps-dataset", source["repository"])
        self.assertTrue((BACKEND / "app" / "data" / "external_fps" / "pcgamebenchmarks" / "source" / "LICENSE").is_file())

    def test_every_profile_is_typed_and_has_a_monotonic_12_gpu_curve(self):
        document = package()
        anchors = sorted(document["reference_gpus"], key=lambda item: item["g3d_mark"])
        point_count = 0
        for profile in document["profiles"]:
            self.assertEqual(profile["data_type"], "external_model_estimate")
            self.assertEqual(profile["fps_resolution"], "1080p")
            self.assertEqual(profile["fps_preset"], "High")
            values = []
            for anchor in anchors:
                value = profile["fps_by_reference_gpu"].get(anchor["name"])
                self.assertIsInstance(value, (int, float), profile["catalog_name"])
                self.assertTrue(math.isfinite(float(value)), profile["catalog_name"])
                self.assertGreater(value, 0, profile["catalog_name"])
                values.append(value)
                point_count += 1
            self.assertEqual(values, sorted(values), profile["catalog_name"])
        self.assertEqual(point_count, 197292)

    def test_resolver_returns_gpu_only_estimate_with_explicit_limits(self):
        row = next(game for game in catalog() if game["name"] == "Portal 2")
        gpu = SimpleNamespace(name="GeForce RTX 3060", raw_score=17008, vram=12)
        slow_cpu = SimpleNamespace(name="AMD Ryzen 3 1200", raw_score=7500, cores=4)
        fast_cpu = SimpleNamespace(name="AMD Ryzen 9 9950X3D", raw_score=60000, cores=16)
        slow_result = resolve_fps_v4(slow_cpu, gpu, row["name"], "1080p", "high")
        fast_result = resolve_fps_v4(fast_cpu, gpu, row["name"], "1080p", "high")
        self.assertEqual(slow_result["status"], "external_model_anchored")
        self.assertEqual(slow_result["measurement_type"], "external_model_estimate")
        self.assertEqual(slow_result["gpu_oriented_fps"], 325)
        self.assertIsNone(slow_result["average_fps"])
        self.assertIsNone(slow_result["one_percent_low"])
        self.assertFalse(slow_result["cpu_limit_assessed"])
        self.assertFalse(slow_result["ram_used_by_model"])
        self.assertEqual(slow_result["gpu_oriented_fps"], fast_result["gpu_oriented_fps"])
        self.assertEqual(slow_result["source_evidence"][0]["license"], "CC BY 4.0")
        self.assertIn("не измерение", slow_result["note"])

    def test_catalog_reference_resolves_missing_local_score_only_for_exact_gpu_identity(self):
        from app.services.external_fps_model import estimate_catalog_gpu_reference
        result = estimate_catalog_gpu_reference("GeForce RTX 3060", 0, 12)
        self.assertTrue(result["available"])
        self.assertGreater(result["target_g3d_score"], 0)
        self.assertEqual(result["gpu_score_provenance"]["source"], "PCGameBenchmarks gpus.csv")
        ambiguous = estimate_catalog_gpu_reference("GeForce RTX Mobile Unknown", 0, None)
        self.assertFalse(ambiguous["available"])

    def test_model_abstains_outside_source_settings_and_safe_score_range(self):
        profile = next(item for item in package()["profiles"] if item["catalog_name"] == "Portal 2")
        game_id = profile["game_id"]
        non_native = estimate_gpu_fps(game_id, "GeForce RTX 3060", 17008, 12, resolution="1440p")
        self.assertIsNone(non_native["fps"])
        self.assertIn("only_1080p_high", non_native["reason"])
        beyond_range = estimate_gpu_fps(game_id, "GeForce RTX 9999", 100000, 12)
        self.assertIsNone(beyond_range["fps"])
        self.assertEqual(beyond_range["reason"], "above_safe_reference_range")
        mobile = estimate_gpu_fps(game_id, "GeForce RTX 4060 Laptop GPU", 17008, 8)
        self.assertIsNone(mobile["fps"])
        self.assertEqual(mobile["reason"], "no_separate_mobile_reference_curve")

    def test_gpu_name_classification_does_not_use_vram_to_guess_device_type(self):
        self.assertEqual(gpu_device_class("GeForce RTX 4060", 8), "desktop")
        self.assertEqual(gpu_device_class("GeForce RTX 4060 Laptop GPU", 8), "mobile")
        self.assertEqual(gpu_device_class("Intel Arc 130V GPU", 8), "integrated")
        self.assertEqual(gpu_device_class("Intel Arc A380E", 6), "desktop")
        self.assertEqual(gpu_device_class("Radeon RX590 GME", 8), "desktop")
        self.assertEqual(gpu_device_class("Radeon R9 295X2", 8), "desktop")
        self.assertEqual(gpu_device_class("USB Display Adapter", 8), "non_rendering")
        self.assertEqual(gpu_device_class("RTX PRO 5000 Blackwell", 48), "workstation")
        self.assertEqual(gpu_device_class("NVIDIA RTX A6000", 48), "workstation")
        self.assertEqual(gpu_device_class("NVIDIA T600", 4), "workstation")
        self.assertEqual(gpu_device_class("NVIDIA GRID T4-1Q", 16), "virtualized")
        self.assertEqual(gpu_device_class("GeForce MX150", 2), "mobile")
        self.assertEqual(gpu_device_class("GeForce 940M", 2), "mobile")
        self.assertEqual(gpu_device_class("AMD Radeon 890M", 8), "integrated")
        self.assertEqual(gpu_device_class("AMD Radeon R7 Graphics A10-7890K", 2), "integrated")
        self.assertEqual(gpu_device_class("NVIDIA RTX 5000 Ada-1B", 8), "virtualized")

    def test_exact_gpu_crosswalk_uses_source_score_and_keeps_type_provenance(self):
        result = estimate_gpu_fps("CS2", "GeForce RTX 3060", 1, 12)
        self.assertEqual(result["fps"], 248)
        self.assertEqual(result["target_g3d_score"], 17008)
        self.assertEqual(result["gpu_score_provenance"]["source"], "PCGameBenchmarks gpus.csv")
        self.assertEqual(result["gpu_match"]["source_device_type"], "Desktop")
        self.assertEqual(result["gpu_match"]["status"], "exact_source_model_and_device_type")

    def test_mobile_workstation_unknown_and_mixed_source_types_abstain(self):
        mobile = estimate_gpu_fps("CS2", "GeForce RTX 4060 Laptop GPU", 20000, 8)
        workstation = estimate_gpu_fps("CS2", "RTX PRO 5000 Blackwell", 30000, 48)
        unknown = estimate_gpu_fps("CS2", "USB Display Adapter", 17000, 8)
        mixed = next(row for row in package()["gpu_catalog"]
                     if "," in row["source_device_type"] and gpu_device_class(row["name"]) == "desktop")
        mixed_result = estimate_gpu_fps("CS2", mixed["name"], mixed["g3d_mark"], 8)
        self.assertEqual(mobile["reason"], "no_separate_mobile_reference_curve")
        self.assertEqual(workstation["reason"], "no_workstation_reference_curve")
        virtualized = estimate_gpu_fps("CS2", "NVIDIA GRID T4-1Q", 19462, 8)
        self.assertEqual(virtualized["reason"], "virtualized_gpu_has_no_matching_reference_curve")
        self.assertEqual(unknown["reason"], "non_rendering_display_adapter")
        self.assertEqual(mixed_result["reason"], "exact_source_gpu_has_mixed_device_types")

    def test_exact_source_device_type_can_resolve_unclassified_desktop_without_vram_guess(self):
        result = estimate_gpu_fps("CS2", "Intel Arc GPU", 1, 16)
        self.assertIsNotNone(result["fps"])
        self.assertEqual(result["device_class"], "desktop")
        self.assertEqual(result["gpu_match"]["status"], "exact_source_model_device_type_inferred")
        self.assertEqual(result["gpu_score_provenance"]["source"], "PCGameBenchmarks gpus.csv")
        self.assertEqual(result["confidence"], "very_low")

    def test_non_rendering_virtual_display_is_not_promoted_by_source_score(self):
        result = estimate_gpu_fps("CS2", "SMI USB Display", 19462, 8)
        self.assertIsNone(result["fps"])
        self.assertEqual(result["reason"], "non_rendering_display_adapter")

    def test_requirement_adequacy_does_not_change_gpu_only_fps_or_claim_system_fps(self):
        row = next(game for game in catalog() if game["name"] == "God of War")
        gpu = SimpleNamespace(name="GeForce RTX 3060", raw_score=17008, vram=12)
        cpu_refs = [
            SimpleNamespace(id=1, name="Intel Core i5-2500K", raw_score=6000),
            SimpleNamespace(id=2, name="AMD Ryzen 3 1200", raw_score=7500),
        ]
        slower = SimpleNamespace(name="AMD Ryzen 5 5600", raw_score=21488)
        faster = SimpleNamespace(name="AMD Ryzen 7 7800X3D", raw_score=39419)
        slow = resolve_fps_v4(slower, gpu, row["name"], "1080p", "high", cpu_catalog=[*cpu_refs, slower, faster])
        fast = resolve_fps_v4(faster, gpu, row["name"], "1080p", "high", cpu_catalog=[*cpu_refs, slower, faster])
        self.assertEqual(slow["gpu_oriented_fps"], fast["gpu_oriented_fps"])
        self.assertIsNone(slow["average_fps"])
        self.assertTrue(slow["cpu_adequacy"]["available"])
        self.assertLess(slow["cpu_adequacy"]["minimum"]["index_vs_reference_percent"],
                        fast["cpu_adequacy"]["minimum"]["index_vs_reference_percent"])
        self.assertFalse(slow["cpu_limit_assessed"])

    def test_import_is_idempotent_and_does_not_touch_database(self):
        script_path = BACKEND / "scripts" / "import_pcgb_fps.py"
        spec = importlib.util.spec_from_file_location("import_pcgb_fps_test", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        source_dir = BACKEND / "app" / "data" / "external_fps" / "pcgamebenchmarks" / "source"
        catalog_path = BACKEND / "app" / "data" / "game_catalog.json"
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            kwargs = dict(
                source_dir=source_dir,
                output_dir=output_dir,
                catalog_path=catalog_path,
                source_revision="299e6f38ed48eda91235bbc451096f5e6fd62910",
                retrieved_at="2026-11-15",
            )
            first_report = module.build_package(**kwargs)
            first_bytes = {name: (output_dir / name).read_bytes() for name in
                           ("source_manifest.json", "profiles.json", "import_report.json")}
            second_report = module.build_package(**kwargs)
            second_bytes = {name: (output_dir / name).read_bytes() for name in
                            ("source_manifest.json", "profiles.json", "import_report.json")}
            self.assertEqual(first_report, second_report)
            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(first_report["matched_games"], 16441)


if __name__ == "__main__":
    unittest.main()

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.services.adaptive_fps import predict_adaptive_fps, compare_adaptive_results
from scripts.startup import run_import
from app.services.catalog_files import CatalogError

class UniversalFallbackTests(unittest.TestCase):
    def test_resolution_scaling_and_cpu_response(self):
        cpu = SimpleNamespace(name="AMD Ryzen 5 5600", raw_score=21819)
        gpu = SimpleNamespace(name="GeForce RTX 3060", raw_score=17008, vram=12)
        results = [predict_adaptive_fps(cpu, gpu, "Portal 2", {"resolution": r, "preset": "high"})
                   for r in ("1080p", "1440p", "4K")]
        values = [r["average_fps"] for r in results]
        self.assertTrue(all(v > 0 for v in values))
        self.assertGreaterEqual(values[0], values[1])
        self.assertGreaterEqual(values[1], values[2])
        self.assertTrue(all(r["one_percent_low"] is None for r in results))
        weak = predict_adaptive_fps(SimpleNamespace(name="weak", raw_score=2000), gpu,
                                   "Portal 2", {"resolution": "1080p", "preset": "high"})
        self.assertLess(weak["average_fps"], values[0])
        self.assertIsNotNone(compare_adaptive_results(weak, results[0])["gain_fps"])
        self.assertEqual(results[0]["technical_details"]["status"], "universal_fallback_estimate")

    def test_expired_local_feed_does_not_block_network(self):
        with patch.dict("os.environ", {"REGARD_BOOTSTRAP_ON_START":"true", "AMVERA":"0"}), \
             patch("scripts.startup.settings.regard_download_enabled", True), \
             patch("scripts.startup.bootstrap", side_effect=CatalogError("no_public_products")), \
             patch("scripts.startup.network_refresh") as refresh:
            run_import()
            refresh.assert_called_once()

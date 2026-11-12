import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.benchmark_aggregation import aggregate


def observation(identifier, fps, publisher="A", series="one"):
    return dict(id=identifier, game="CS2", game_version="1", cpu="Ryzen 5 5600",
                gpu="RTX 3060", ram_gb=16, ram_type="DDR4", ram_channels=2,
                resolution="1080p", preset="Low", rt=False, upscaling="off",
                frame_generation=False, scene="benchmark", overclocked=False,
                os="Windows", form_factor="Desktop", average_fps=fps,
                publisher=publisher, series_id=series,
                source_url="https://example.org/benchmark", source_ids=[identifier],
                license="CC-BY-4.0", attribution="Example source")


class ConfidenceTests(unittest.TestCase):
    def test_single_publisher_has_no_between_source_interval(self):
        item = aggregate([observation("one", 100)])[0]
        self.assertEqual(item["independent_publishers"], 1)
        self.assertIsNone(item["p10_between_publishers_fps"])
        self.assertIsNone(item["p90_between_publishers_fps"])

    def test_multi_publisher_interval_is_available(self):
        item = aggregate([observation("one", 100),
                          observation("two", 200, publisher="B", series="two")])[0]
        self.assertEqual(item["independent_publishers"], 2)
        self.assertIsNotNone(item["p10_between_publishers_fps"])
        self.assertIsNotNone(item["p90_between_publishers_fps"])


if __name__ == "__main__":
    unittest.main()

"""Synthetic offline fixtures: manual and automatic CPU/board rules must agree."""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.base import Base
from app.db.models import Hardware, HardwarePrice, StoreOffer
from app.services.builds import BuildRequest, assemble


class ManualCompatibilityTests(unittest.TestCase):
    def build(self, cpu_name, socket, board_name, use_offer=True):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                for ident, kind, name, component_socket in [
                    (1, "CPU", cpu_name, socket),
                    (2, "GPU", "GeForce GTX 1060", None),
                ]:
                    db.add(Hardware(id=ident, type=kind, name=name, socket=component_socket,
                                    raw_score=9000, normalized_score=50))
                    db.add(HardwarePrice(hardware_id=ident, source="retailer_feed", price_rub=1000,
                                         market="retail_ru", source_url="https://example.test/synthetic-fixture",
                                         observed_at=datetime.utcnow()))
                board = {"name": board_name, "price": 1000}
                if use_offer:
                    db.add(StoreOffer(id=10, source="regard",
                                      url="https://www.regard.ru/product/10/synthetic-fixture",
                                      name=board_name, category="motherboard", price_rub=1000,
                                      condition="new", observed_at=datetime.utcnow(), origin="feed",
                                      attributes=json.dumps({})))
                    board["offer_id"] = 10
                db.commit()
                other = {key: {"name": "Synthetic fixture " + key, "price": 0}
                         for key in ("memory", "storage", "psu", "case", "cooler")}
                request = BuildRequest(scenario="build", budget=10000, game="CS2", mode="1080p_low",
                                       socket=socket, ram_type="DDR4", ram_capacity_gb=16,
                                       motherboard=board, **other)
                result = assemble(request, db)
                self.assertEqual(len(result["parts"]), 8)
                self.assertEqual(sum(part["price"] for part in result["parts"]), result["total_price"])
                self.assertLessEqual(result["total_price"], request.budget)
                return result
        finally:
            engine.dispose()

    def assert_rejected(self, *args, **kwargs):
        with self.assertRaises(HTTPException) as error:
            self.build(*args, **kwargs)
        self.assertIn(error.exception.status_code, (400, 422))

    def test_h110_offer_rejects_ninth_generation_cpu(self):
        self.assert_rejected("Intel Core i5-9400F", "LGA1151", "MSI H110M DDR4 LGA1151")

    def test_b365_offer_rejects_sixth_generation_cpu(self):
        self.assert_rejected("Intel Core i5-6400", "LGA1151", "Gigabyte B365M DDR4 LGA1151")

    def test_b460_offer_rejects_eleventh_generation_cpu(self):
        self.assert_rejected("Intel Core i5-11400F", "LGA1200", "MSI B460M DDR4 LGA1200")

    def test_manual_board_name_uses_the_same_chipset_rules(self):
        self.assert_rejected("Intel Core i5-9400F", "LGA1151", "MSI H110M DDR4 LGA1151", use_offer=False)

    def test_offer_title_socket_conflict_is_rejected_without_attributes(self):
        self.assert_rejected("AMD Ryzen 5 5600", "AM4", "MSI B650M AM5 DDR5")

    def test_manual_title_socket_conflict_is_rejected(self):
        self.assert_rejected("AMD Ryzen 5 5600", "AM4", "MSI B650M AM5 DDR5", use_offer=False)

    def test_known_compatible_generations_remain_available(self):
        for cpu_name, socket, board_name in [
            ("Intel Core i5-6400", "LGA1151", "MSI H110M DDR4 LGA1151"),
            ("Intel Core i5-9400F", "LGA1151", "Gigabyte B365M DDR4 LGA1151"),
            ("Intel Core i5-11400F", "LGA1200", "MSI B560M DDR4 LGA1200"),
        ]:
            with self.subTest(cpu=cpu_name):
                result = self.build(cpu_name, socket, board_name)
                self.assertEqual(result["parts"][0]["name"], cpu_name)

    def test_unknown_board_name_preserves_existing_manual_flow(self):
        result = self.build("Intel Core i5-9400F", "LGA1151", "Synthetic board", use_offer=False)
        self.assertTrue(any("не подтверждена" in note for note in result["compatibility_notes"]))


if __name__ == "__main__":
    unittest.main()

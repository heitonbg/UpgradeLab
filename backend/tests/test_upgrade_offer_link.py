import unittest
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.models import Hardware
from app.schemas.calculate import CalculateRequest
from app.api.calculate import _post_calculate
from app.core.price_time import db_now

class UpgradeOfferLinkTests(unittest.TestCase):
    def test_selected_catalog_game_upgrade_retains_real_quote_link(self):
        engine=create_engine("sqlite://")
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                cpu=Hardware(type="CPU",name="AMD Ryzen 5 5600",raw_score=21819,normalized_score=21819,socket="AM4")
                gpu=Hardware(type="GPU",name="GeForce RTX 3060",raw_score=17008,normalized_score=17008,vram=12)
                replacement=Hardware(type="GPU",name="GeForce RTX 4060",raw_score=19530,normalized_score=19530,vram=8)
                db.add_all([cpu,gpu,replacement]);db.commit()
                url="https://www.regard.ru/product/1234"
                quote=SimpleNamespace(price_rub=29000,source="regard",source_url=url,market="new_ru",origin="catalog_import",observed_at=db_now(),verified_at=None,offer_id=1234)
                payload=CalculateRequest(cpu_id=cpu.id,gpu_id=gpu.id,selected_upgrade_id=replacement.id,game="Portal 2",mode="1080p_high",budget=30000)
                with patch("app.api.calculate.upgrade_price_map",return_value={replacement.id:quote}):
                    result=_post_calculate(payload,db)
                self.assertEqual(result.upgrade_price["price_url"],url)
                self.assertTrue(result.upgrade_price["is_purchase_quote"])
                self.assertEqual(result.avg_price,29000)
        finally:
            engine.dispose()

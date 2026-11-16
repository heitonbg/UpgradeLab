"""The model picker must not wait for a full offer-price scan."""
import unittest
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Hardware, HardwarePrice
from app.api.hardware import hardware_selectors
from app.crud.hardware import get_by_id
from app.api.autodetect import CpuDetectRequest, detect_cpu


class HardwareSelectorTests(unittest.TestCase):
    def test_selector_keeps_models_but_does_not_compute_or_expose_prices(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        try:
            with Session(engine) as db:
                db.add_all([
                    Hardware(id=1, type='CPU', name='Ryzen 5 5600', raw_score=20000,
                             normalized_score=50, socket='AM4'),
                    Hardware(id=2, type='GPU', name='RTX 5060', raw_score=21000,
                             normalized_score=50, vram=8),
                    Hardware(id=3, type='RAM', name='DDR4 16GB', raw_score=1,
                             normalized_score=1, ram_type='DDR4', ram_capacity_gb=16),
                    Hardware(id=4, type='SSD', name='Other', raw_score=0, normalized_score=0),
                    Hardware(id=5, type='CPU', name='Apple M4', raw_score=50000,
                             normalized_score=99, socket='Apple'),
                    Hardware(id=6, type='CPU', name='Intel Core i5-12400F', raw_score=15000,
                             normalized_score=40, socket='LGA1700'),
                    HardwarePrice(hardware_id=1, source='reference', price_rub=10000,
                                  market='retail_ru', source_url='https://example.test',
                                  observed_at=__import__('datetime').datetime.utcnow()),
                ])
                db.commit()
                response = Response()
                rows = hardware_selectors(db, response)
                self.assertEqual({row['type'] for row in rows}, {'CPU', 'GPU', 'RAM'})
                cpu_rows = [row for row in rows if row['type'] == 'CPU']
                self.assertEqual([row['name'] for row in cpu_rows], ['Ryzen 5 5600', 'Intel Core i5-12400F'])
                self.assertEqual(rows[0]['socket'], 'AM4')
                self.assertEqual(next(row for row in rows if row['type'] == 'GPU')['vram'], 8)
                self.assertEqual(next(row for row in rows if row['type'] == 'RAM')['ram_capacity_gb'], 16)
                self.assertTrue(all('avg_price' not in row and 'price_source' not in row for row in rows))
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertIsNone(get_by_id(db, 5))
                self.assertIsNone(detect_cpu(CpuDetectRequest(cpu_name='Apple M4'), db).cpu_id)
        finally:
            engine.dispose()

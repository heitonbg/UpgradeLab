"""Full-PC regressions: ad confusion, budget allocation, power and game balance."""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.base import Base
from app.db.models import Hardware, StoreOffer
from app.services.builds import BuildRequest, assemble
from app.services.assembly_policy import balanced_options, psu_requirement, cooling_requirement


class AutomaticPolicyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        for ident, kind, name, score, price, vram in [
            (1, 'CPU', 'Intel Core i5-12400F', 20000, 8000, None),
            (2, 'CPU', 'Intel Core i5-13400F', 27000, 18000, None),
            (3, 'GPU', 'Radeon RX Vega 64', 14000, 12300, 8),
            (4, 'GPU', 'GeForce RTX 3060', 18000, 20000, 12),
            (5, 'GPU', 'GeForce RTX 5060', 25000, 33000, 8),
            (6, 'GPU', 'Radeon RX 6800 XT', 28000, 40000, 16),
            (7, 'GPU', 'Radeon RX 5500', 12000, 4922, 8),
        ]:
            self.db.add(Hardware(id=ident, type=kind, name=name, raw_score=score, normalized_score=50,
                                 socket='LGA1700' if kind == 'CPU' else None, vram=vram))
            self.add(kind, name if ident != 7 else 'GeForce GT 710 4GB (Radeon RX5500 8GB)', price,
                     hardware_id=ident)
        self.add('motherboard', 'MSI PRO H610M-E DDR4', 4500)
        self.add('motherboard', 'MSI PRO H610M-E DDR4 под восстановление', 10, condition='used')
        self.add('memory', 'RAM 16GB DDR4 2x8GB KIT', 3000)
        self.add('storage', 'Kingston KC3000 1TB M.2 NVMe', 18000)
        self.add('storage', 'Lexar NM620 512GB M.2 NVMe', 4000)
        self.add('storage', 'Lexar NM620 1TB M.2 NVMe', 5500)
        self.add('storage', 'Crucial P3 Plus 500GB M.2 NVMe', 4500)
        self.add('psu', 'Corsair CX550 550W Bronze', 3500)
        self.add('psu', 'DeepCool PK650D 650W Bronze', 5200)
        self.add('psu', 'Corsair CX750 750W Bronze', 6500)
        self.add('psu', 'MSI MAG A750GL 750W Gold', 8500)
        self.add('cooler', 'DeepCool AG300', 650)
        self.add('cooler', 'ID-COOLING SE-214-XT BLACK', 1200)
        self.add('cooler', 'Thermalright Assassin X 120 Refined SE', 1000)
        self.add('case', 'DeepCool CC560 ARGB', 4500)
        self.add('case', 'Montech X3 Mesh', 4800)
        self.db.commit()
        self.payload = dict(scenario='build', auto_parts=True, game='Red Dead Redemption 2', mode='1440p_high',
                            target_fps=60, budget=50000, socket='LGA1700', ram_type='DDR4', ram_capacity_gb=16,
                            price_sources=['regard', 'avito'])

    def add(self, category, name, price, hardware_id=None, condition='new'):
        self.db.add(StoreOffer(source='avito' if condition == 'used' else 'regard', category=category, name=name,
                               price_rub=price, hardware_id=hardware_id, condition=condition, attributes='{}',
                               url=f'https://www.regard.ru/product/{len(self.db.new) + 100}/fixture',
                               observed_at=datetime.utcnow(), origin='feed'))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def build(self, **changes):
        with patch('app.services.builds.search_offers', return_value={}):
            return assemble(BuildRequest(**{**self.payload, **changes}), self.db)

    def test_fifty_thousand_does_not_spend_eighteen_thousand_on_ssd(self):
        result = self.build()
        for build in result['alternatives']:
            parts = {part['type']: part for part in build['parts']}
            self.assertLessEqual(build['total_price'], 50000)
            self.assertEqual(sum(part['price'] for part in build['parts']), build['total_price'])
            self.assertIn('Lexar', parts['storage']['name'])
            self.assertLessEqual(parts['storage']['price'], 6000)
            self.assertNotIn('восстановление', parts['motherboard']['name'])
            self.assertNotIn('RX 5500', parts['GPU']['name'])
            self.assertIn('Corsair CX550', parts['psu']['name'])

    def test_hundred_thousand_variants_keep_gpu_and_power_balanced(self):
        result = self.build(budget=100000)
        for build in result['alternatives']:
            parts = {part['type']: part for part in build['parts']}
            self.assertNotIn('Vega', parts['GPU']['name'])
            self.assertNotIn('GT 710', parts['GPU']['name'])
            self.assertNotEqual(parts['cooler']['name'], 'DeepCool AG300')
            self.assertEqual(parts['storage']['quality']['capacity_gb'], 1000)
            self.assertLessEqual(build['total_price'], 100000)
            if '6800 XT' in parts['GPU']['name']:
                self.assertGreaterEqual(parts['psu']['quality']['watts'], 750)
            cpu = self.db.get(Hardware, parts['CPU']['id'])
            gpu = self.db.get(Hardware, parts['GPU']['id'])
            self.assertGreaterEqual(parts['psu']['quality']['watts'], psu_requirement(cpu, gpu))
            self.assertGreaterEqual(parts['cooler']['quality']['cooling_class'], cooling_requirement(cpu))

    def test_selected_variant_and_case_survive_saving(self):
        initial = self.build(budget=100000)
        for variant in initial['alternatives']:
            parts = {part['type']: part for part in variant['parts']}
            saved = self.build(budget=100000, selected_cpu_id=parts['CPU']['id'], selected_gpu_id=parts['GPU']['id'],
                               selected_case_offer_id=parts['case']['offer_id'])
            self.assertEqual([p['name'] for p in saved['parts']], [p['name'] for p in variant['parts']])
            self.assertEqual(saved['total_price'], variant['total_price'])

    def test_stronger_cpu_cannot_receive_the_cheapest_small_cooler(self):
        result = self.build(budget=100000, selected_cpu_id=2, selected_gpu_id=4)
        cooler = next(part for part in result['parts'] if part['type'] == 'cooler')
        self.assertGreaterEqual(cooler['quality']['cooling_class'], 2)


if __name__ == '__main__':
    unittest.main()

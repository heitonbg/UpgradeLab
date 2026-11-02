"""Distinct budgeted alternatives and preserving the user's selected pair."""
import sys
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.models import Hardware, HardwarePrice, StoreOffer
from app.services.builds import BuildRequest, assemble


class BuildVariantsTests(unittest.TestCase):
    def test_corrected_cooler_price_is_included_in_the_returned_full_build(self):
        names = {'motherboard':'Gigabyte B450M DS3H DDR4 M.2 PCIe 2280','memory':'16GB DDR4 комплект 2x8',
                 'storage':'Netac NV3000 500GB M.2 2280','psu':'MSI MAG A650BN',
                 'case':'DeepCool CC560','cooler':'ID-COOLING SE-214-XT'}
        for index,(category,name) in enumerate(names.items(),100):
            self.db.add(StoreOffer(id=index,source='regard',url=f'https://www.regard.ru/product/{index}/test',
                                   name=name,category=category,price_rub=846 if category=='cooler' else 2000,
                                   condition='new',observed_at=datetime.utcnow(),attributes='{}',
                                   origin='public_page' if category=='cooler' else 'feed'))
        self.db.commit()
        markup=json.dumps({'@type':'Product','name':names['cooler'],
            'url':'https://www.regard.ru/product/105/test','offers':{'price':1752,'priceCurrency':'RUB'}})
        request=BuildRequest(**{**self.payload,'auto_parts':True,'budget':50000})
        with patch('app.services.builds.search_offers',return_value={}), patch(
                'app.services.price_verification.fetch',return_value=f'<script type="application/ld+json">{markup}</script>') as fetch:
            result=assemble(request,self.db)
        self.assertEqual(fetch.call_count,1)
        for variant in result['alternatives']:
            cooler=next(part for part in variant['parts'] if part['type']=='cooler')
            self.assertEqual(cooler['price'],1752)
            self.assertTrue(cooler['price_verified_at'])
            self.assertEqual(sum(part['price'] for part in variant['parts']),variant['total_price'])
            self.assertLessEqual(variant['total_price'],50000)

    def test_nvme_is_preferred_only_with_a_confirmed_board_slot(self):
        names = {'motherboard': 'Generic AM4 DDR4', 'memory': '16GB DDR4 комплект 2x8',
                 'storage': 'Samsung 870 EVO 500GB', 'psu': 'MSI MAG A650BN',
                 'case': 'DeepCool CC560', 'cooler': 'DeepCool AG400'}
        for index, (category, name) in enumerate(names.items(), 100):
            self.db.add(StoreOffer(id=index, source='regard', url=f'https://www.regard.ru/product/{index}/test',
                                   name=name, category=category, price_rub=2000,
                                   condition='new', observed_at=datetime.utcnow(), origin='feed', attributes='{}'))
        self.db.add(StoreOffer(id=200, source='regard', url='https://www.regard.ru/product/200/test',
                               name='Kingston KC3000 512GB M.2 NVMe', category='storage', price_rub=2100,
                               condition='new', observed_at=datetime.utcnow(), origin='feed', attributes='{}'))
        self.db.commit()
        request = BuildRequest(**{**self.payload, 'auto_parts': True, 'budget': 50000})
        with patch('app.services.builds.search_offers', return_value={}):
            sata = assemble(request, self.db)
            self.assertIn('870 EVO', next(p for p in sata['parts'] if p['type'] == 'storage')['name'])
            board = self.db.get(StoreOffer, 100)
            board.attributes = json.dumps({'nvme_2280': True})
            self.db.commit()
            nvme = assemble(request, self.db)
            storage = next(p for p in nvme['parts'] if p['type'] == 'storage')
            self.assertIn('KC3000', storage['name'])
            self.assertTrue(storage['quality']['board_compatibility'])
            self.assertEqual(sum(p['price'] for p in nvme['parts']), nvme['total_price'])

    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.hardware = []
        for index, (kind, score, price) in enumerate([
            ('CPU', 5000, 4000), ('CPU', 14000, 8000),
            ('GPU', 6000, 6000), ('GPU', 10000, 10000), ('GPU', 18000, 16000),
        ], start=1):
            hardware = Hardware(id=index, type=kind, name=f'Test {kind} {index}', raw_score=score,
                                normalized_score=50, socket='AM4' if kind == 'CPU' else None)
            self.db.add(hardware)
            self.db.add(StoreOffer(id=index, hardware_id=index, source='regard', category=kind,
                                   name=hardware.name, price_rub=price, condition='new', observed_at=datetime.utcnow(),
                                   url=f'https://www.regard.ru/product/{index}/hardware', origin='feed', attributes='{}'))
            self.db.add(HardwarePrice(hardware_id=index, source='retailer_feed', price_rub=price,
                                     market='retail_ru', source_url=f'https://example.test/{index}',
                                     observed_at=datetime.utcnow(), sample_count=1))
            self.hardware.append(hardware)
        self.db.commit()
        self.payload = dict(scenario='build', budget=25000, target_fps=60, game='CS2', mode='1080p_low',
                            socket='AM4', ram_type='DDR4', ram_capacity_gb=16, auto_parts=False)
        self.payload.update({key: {'name': f'Test {key}', 'price': 100} for key in
                             ('motherboard', 'memory', 'storage', 'psu', 'case', 'cooler')})

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_three_distinct_complete_builds_within_budget(self):
        result = assemble(BuildRequest(**self.payload), self.db)
        variants = result['alternatives']
        self.assertEqual(len(variants), 3)
        pairs = {(v['parts'][0]['id'], v['parts'][1]['id']) for v in variants}
        self.assertEqual(len(pairs), 3)
        for variant in variants:
            self.assertEqual(len(variant['parts']), 8)
            self.assertEqual(sum(part['price'] for part in variant['parts']), variant['total_price'])
            self.assertLessEqual(variant['total_price'], self.payload['budget'])
            self.assertEqual(variant['remaining_budget'], self.payload['budget'] - variant['total_price'])
            self.assertEqual(variant['target_reached'], variant['fps_outlook']['minimum'] >= self.payload['target_fps'])
            self.assertNotIn('alternatives', variant)

    def test_selected_alternative_survives_recalculation_for_saving(self):
        initial = assemble(BuildRequest(**self.payload), self.db)
        variant = initial['alternatives'][-1]
        selected = BuildRequest(**self.payload, selected_cpu_id=variant['parts'][0]['id'],
                                selected_gpu_id=variant['parts'][1]['id'])
        saved = assemble(selected, self.db)
        self.assertEqual([p['id'] for p in saved['parts'][:2]], [p['id'] for p in variant['parts'][:2]])
        self.assertEqual(saved['fps'], variant['fps'])
        self.assertEqual(saved['total_price'], variant['total_price'])

    def test_small_budget_does_not_duplicate_cards(self):
        result = assemble(BuildRequest(**{**self.payload, 'budget': 11000, 'target_fps': 1000}), self.db)
        self.assertEqual(len(result['alternatives']), 1)
        self.assertFalse(result['target_reached'])

    def test_invalid_selected_pair_is_rejected(self):
        with self.assertRaises(ValidationError):
            BuildRequest(**self.payload, selected_cpu_id=1)
        with self.assertRaises(HTTPException) as error:
            assemble(BuildRequest(**self.payload, selected_cpu_id=99999, selected_gpu_id=3), self.db)
        self.assertEqual(error.exception.status_code, 400)

    def test_automatic_build_searches_and_rejects_ambiguous_board_and_weak_psu(self):
        self.payload['budget'] = 35000
        # Three real tradeoffs near the best FPS; a much slower pair should no
        # longer be invented just to fill the third card.
        for hardware_id, score in [(3, 12000), (4, 12800), (5, 18000)]:
            self.db.get(Hardware, hardware_id).raw_score = score
        names = {
            'motherboard': 'Motherboard AM4 DDR4',
            'memory': 'RAM 16GB DDR4 (2x8GB KIT)', 'storage': 'SSD Samsung 870 EVO 500GB SATA',
            'psu': 'Блок питания MSI MAG A650BN 650 Вт', 'case': 'DeepCool CC560 ARGB', 'cooler': 'Кулер DeepCool AG400',
        }
        for index, (category, name) in enumerate(names.items()):
            self.db.add(StoreOffer(source='regard', url=f'https://www.regard.ru/product/{100+index}/test',
                                   name=name, category=category, price_rub=2000 if category == 'case' else 100,
                                   condition='new', observed_at=datetime.utcnow(), origin='feed', attributes='{}'))
        for index, (category, name) in enumerate([
            ('motherboard', 'Материнские платы AM4/1155/1150/1151/1200 Обмен'),
            ('psu', 'Блок питания Exegate ATX 400 Вт'),
            ('storage', 'Внешний SSD Samsung 870 EVO 500GB USB'),
            ('cooler', 'Крепления для кулера DeepCool AG400'),
        ]):
            self.db.add(StoreOffer(source='regard', url=f'https://www.regard.ru/product/{200+index}/test',
                                   name=name, category=category, price_rub=1,
                                   condition='new', observed_at=datetime.utcnow(), origin='feed', attributes='{}'))
        self.db.add(StoreOffer(source='regard', url='https://www.regard.ru/product/300/test-case',
                               name='Montech X3 Mesh', category='case', price_rub=2500,
                               condition='new', observed_at=datetime.utcnow(), origin='feed', attributes='{}'))
        self.db.commit()
        with patch('app.services.builds.search_offers', return_value={'offers': [], 'sources': []}) as search:
            result = assemble(BuildRequest(**{**self.payload, 'auto_parts': True}), self.db)
            base_case = next(part for part in result['parts'] if part['type'] == 'case')
            alternative = next(v for v in result['alternatives'] if next(p for p in v['parts'] if p['type'] == 'case')['offer_id'] != base_case['offer_id'])
            alternative_case = next(p for p in alternative['parts'] if p['type'] == 'case')
            saved = assemble(BuildRequest(**{**self.payload, 'auto_parts': True,
                'selected_cpu_id': alternative['parts'][0]['id'], 'selected_gpu_id': alternative['parts'][1]['id'],
                'selected_case_offer_id': alternative_case['offer_id']}), self.db)
            self.assertEqual(next(part for part in saved['parts'] if part['type'] == 'case')['offer_id'], alternative_case['offer_id'])
            self.assertEqual(saved['total_price'], alternative['total_price'])
        # Avito is attempted first even when a full retail PC is already cached.
        self.assertTrue(search.call_args_list)
        self.assertTrue(all(call.args[1].sources == ['avito'] for call in search.call_args_list))
        self.assertEqual({call.args[1].category for call in search.call_args_list}, {'CPU','GPU',*names})
        selected = {part['type']: part for part in result['parts']}
        self.assertEqual(selected['motherboard']['name'], names['motherboard'])
        self.assertEqual(selected['psu']['name'], names['psu'])
        self.assertEqual(selected['storage']['name'], names['storage'])
        self.assertEqual(selected['cooler']['name'], names['cooler'])
        self.assertEqual(selected['psu']['quality']['label'], '80 PLUS Bronze')


if __name__ == '__main__':
    unittest.main()

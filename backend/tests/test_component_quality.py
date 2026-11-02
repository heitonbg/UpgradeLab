"""Regression examples from marketplace ads that must not become PC parts."""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.component_quality import quality_check, invalid_manual_part


def offer(category, name, attributes=None, condition='new'):
    return SimpleNamespace(category=category, name=name, attributes=json.dumps(attributes or {}), condition=condition)


class ComponentQualityTests(unittest.TestCase):
    def test_avito_internal_chinese_ssd_is_allowed_with_condition_warning(self):
        for name in ['Netac NV3000 500GB M.2 2280', 'Netac NV3000-Q 512GB M.2 2280', 'KingSpec NX-512GB M.2 2280']:
            row=offer('storage',name,condition='used')
            row.source='avito'
            quality,reason=quality_check(row)
            self.assertIsNone(reason)
            self.assertEqual(quality['condition'],'used')
            self.assertFalse(quality['health_verified'])
            self.assertIn('SMART',' '.join(quality['claims']))
        row=offer('storage','KingSpec NX-512GB M.2 2230',condition='used');row.source='avito'
        self.assertIsNone(quality_check(row)[0])
        row=offer('storage','KingSpec NX-512GB M.2',condition='used');row.source='avito'
        self.assertIsNone(quality_check(row)[0])
        row=offer('storage','Netac NV3000 500GB',{'description':'SMART ошибки, ресурс исчерпан'},condition='used');row.source='avito'
        self.assertIsNone(quality_check(row)[0])
    def test_multiple_brands_have_verified_profiles_without_invented_interfaces(self):
        for name in ['Crucial BX500 480GB SATA', 'Kingston A400 480GB SATA 2.5', 'Kingston SA400S37/480G']:
            quality, reason = quality_check(offer('storage', name))
            self.assertIsNone(reason)
            self.assertEqual(quality['capacity_gb'], 480)
            self.assertNotIn('TLC NAND и DRAM-кеш', quality['claims'])
        for name, generation in [('Lexar NM620 512GB', '3.0'), ('Samsung 980 500GB', '3.0'),
                                 ('Crucial P3 Plus 1TB', '4.0')]:
            quality, reason = quality_check(offer('storage', name))
            self.assertIsNone(reason)
            self.assertIn('PCIe ' + generation, quality['claims'][0])
        self.assertIsNone(quality_check(offer('storage', 'Lexar NM620 500GB'))[0])
        self.assertIsNone(quality_check(offer('storage', 'Samsung 980 PRO 500GB'))[0])
        self.assertEqual(quality_check(offer('psu', 'Corsair CX550 550W Bronze'))[0]['watts'], 550)
        self.assertIsNone(quality_check(offer('psu', 'Corsair CX550 80 PLUS Gold'))[0])
        for name in ['ID-COOLING SE-214-XT BLACK', 'Thermalright Assassin X 120 Refined SE', 'ARCTIC Freezer 36']:
            self.assertIsNotNone(quality_check(offer('cooler', name), 'LGA1700')[0])
        self.assertIsNone(quality_check(offer('cooler', 'ARCTIC Freezer 36'), 'LGA1200')[0])

    def test_internal_nvme_and_conflicting_or_external_variants(self):
        for name in ['Kingston KC3000 512GB M.2 NVMe', 'WD Blue SN580 1TB M.2 2280']:
            evidence, reason = quality_check(offer('storage', name))
            self.assertIsNone(reason)
            self.assertEqual(evidence['interface'], 'NVMe')
            self.assertFalse(invalid_manual_part(name, 'storage'))
        for name, attrs in [
            ('Kingston KC3000 512GB USB', {}),
            ('Kingston KC3000 512GB SATA', {}),
            ('WD Blue SN580 1TB', {'interface': 'SATA'}),
            ('WD Blue SN580 512GB', {}),
            ('Kingston KC3000 512GB 2230', {}),
            ('Kingston KC3000 512GB / 1TB', {}),
        ]:
            with self.subTest(name=name):
                self.assertIsNone(quality_check(offer('storage', name, attrs))[0])

    def test_nvme_board_requires_slot_evidence_not_just_socket_or_m2(self):
        from app.services.storage_compatibility import nvme_board_evidence
        for name in ['Generic AM4 DDR4', 'Generic B550 M.2']:
            self.assertIsNone(nvme_board_evidence(offer('motherboard', name)))
        board = offer('motherboard', 'MSI B550M PRO-VDH')
        self.assertIn('msi.com', nvme_board_evidence(board)['source_url'])
        self.assertIn('msi.com',nvme_board_evidence(offer('motherboard','MSI B550M PRO-VDH WIFI'))['source_url'])
        self.assertIsNone(nvme_board_evidence(offer('motherboard','MSI B550M PRO-VDH',{'nvme_2280':False})))

    def test_watts_or_a_sellers_certificate_claim_are_not_enough(self):
        for name in ['Блок питания Exegate 650W', 'Unknown ATX 800W 80 PLUS Gold', 'Блок питания MSI MAG A650N 650W', 'MSI MAG A650BNL 650W']:
            with self.subTest(name=name):
                evidence, reason = quality_check(offer('psu', name, {'watts': 650, 'efficiency_rating': '80 PLUS Gold'}))
                self.assertIsNone(evidence)
                self.assertTrue(reason)

    def test_verified_psu_model_has_manufacturer_evidence_and_protections(self):
        evidence, reason = quality_check(offer('psu', 'Блок питания MSI MAG A650BN 650 Вт'))
        self.assertIsNone(reason)
        self.assertEqual(evidence['watts'], 650)
        self.assertEqual(evidence['label'], '80 PLUS Bronze')
        self.assertTrue(evidence['source_url'].startswith('https://www.msi.com/'))
        self.assertIn('Защиты:', ' '.join(evidence['claims']))
        self.assertIsNone(quality_check(offer('psu', 'MSI MAG A650BN 1000W'))[0])
        self.assertIsNone(quality_check(offer('psu', 'MSI MAG A650BN 80 PLUS Gold'))[0])
        self.assertIsNone(quality_check(offer('psu', 'MSI MAG A650BN', condition='used'))[0])
        self.assertIsNone(quality_check(offer('psu', 'Кабели для блока питания MSI MAG A650BN'))[0])

    def test_external_ssds_and_adapters_cannot_override_the_title_with_attributes(self):
        for name in ['Внешний SSD Samsung 870 EVO 500GB USB', 'SSD Kingston KC600 512GB USB Type-C',
                     'Адаптер для SSD Samsung 870 EVO', 'Корпус для Kingston KC600 512GB',
                     'Kingston SKC600MS/512G mSATA', 'Внешний SSD Kingspec 1TB']:
            with self.subTest(name=name):
                self.assertIsNone(quality_check(offer('storage', name, {'interface':'SATA','capacity_gb':500}))[0])
                self.assertTrue(invalid_manual_part(name,'storage'))

    def test_internal_known_ssd_series_capacity_and_interface(self):
        for name in ['SSD Samsung 870 EVO 500GB SATA 2.5', 'Kingston KC600 512GB SATA', 'SSD Samsung 870 EVO 1 ТБ']:
            with self.subTest(name=name):
                evidence, reason = quality_check(offer('storage', name))
                self.assertIsNone(reason)
                self.assertEqual(evidence['label'], 'Внутренний SATA SSD')
                self.assertIn('TLC NAND и DRAM-кеш', evidence['claims'])
        for name in ['Samsung 870 EVO 250GB', 'Samsung 870 EVO 512GB', 'Samsung 870 EVO', 'SSD Generic 1TB', 'Kingston KC600 512GB / 1TB']:
            with self.subTest(name=name):
                self.assertIsNone(quality_check(offer('storage', name))[0])
        self.assertIsNone(quality_check(offer('storage','Samsung 870 EVO 500GB',{'capacity_gb':1000}))[0])
        self.assertIsNone(quality_check(offer('storage','Kingston KC600 512GB',condition='used'))[0])
        self.assertIsNone(quality_check(offer('storage','Компьютер Ryzen 5 с Samsung 870 EVO 500GB'))[0])

    def test_cooler_mount_for_80_rubles_is_not_a_complete_cooler(self):
        for name in ['Крепления для кулера DeepCool AG400', 'DeepCool AG400 bracket AM4',
                     'Рамка для кулера DeepCool AG400', 'Вентилятор для DeepCool AG400',
                     'DeepCool AG400 без крепления', 'Кулер неизвестной модели AM4']:
            with self.subTest(name=name):
                self.assertIsNone(quality_check(offer('cooler',name),'AM4')[0])
        evidence, reason = quality_check(offer('cooler','Кулер DeepCool AG400'),'AM4')
        self.assertIsNone(reason)
        self.assertEqual(evidence['model'],'DeepCool AG400')
        self.assertIsNone(quality_check(offer('cooler','DeepCool AG400',{'sockets':['LGA1700']}),'AM4')[0])
        self.assertIsNone(quality_check(offer('cooler','DeepCool AG400'),'AM3+')[0])


if __name__ == '__main__':
    unittest.main()

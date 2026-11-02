import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.gaming_selection import gaming_cases, gaming_options, CPU_SEARCHES
from app.services.performance import estimate_fps, fps_outlook, references
from app.schemas.calculate import GameName, CalcMode


class GamingPolicyTests(unittest.TestCase):
    def test_every_game_and_mode_has_an_explicit_non_measurement_estimate(self):
        for game in GameName:
            for mode in CalcMode:
                estimate = estimate_fps(15000, 17000, 'GeForce RTX 3060', game, mode)
                outlook = fps_outlook(estimate, 'GeForce RTX 3060', game, mode)
                self.assertLessEqual(outlook['minimum'], estimate)
                self.assertGreaterEqual(outlook['maximum'], estimate)
        outlook = fps_outlook(60, 'GeForce RTX 3060', GameName.BG3, CalcMode.MODE_1440P_HIGH)
        self.assertEqual(outlook['data_quality'],'estimated_from_tests')
        self.assertTrue(outlook['sources'])
        self.assertEqual(outlook['comparison_tests'][0]['fps'], 44.6)
        self.assertIn('Ultra', outlook['comparison_tests'][0]['settings'])
        self.assertFalse(fps_outlook(60, 'GeForce RTX 3060 Ti', GameName.BG3, CalcMode.MODE_1080P_LOW)['comparison_tests'])

    def test_rdr2_reference_is_not_a_guarantee_of_60_for_the_cpu_gpu_pair(self):
        game, mode = GameName.RDR2, CalcMode.MODE_1440P_HIGH
        estimate = estimate_fps(13500, 16500, 'GeForce RTX 2060 SUPER', game, mode, 1.07)
        outlook = fps_outlook(estimate, 'GeForce RTX 2060 SUPER', game, mode)
        self.assertEqual(estimate, 60)
        self.assertLess(outlook['minimum'], 60)
        self.assertGreater(outlook['maximum'], 60)
        self.assertEqual(len(outlook['sources']), 2)
        self.assertIn('не тест вашей связки', outlook['note'])
        self.assertFalse(references('GeForce RTX 2060', game, mode))
        self.assertFalse(references('GeForce RTX 2060 SUPER', game, CalcMode.MODE_1080P_HIGH))

    def test_cpu_replacement_cannot_exceed_gpu_reference_limit(self):
        game, mode = GameName.RDR2, CalcMode.MODE_1440P_HIGH
        weak = estimate_fps(13500, 16500, 'GeForce RTX 2060 SUPER', game, mode)
        strong = estimate_fps(90000, 16500, 'GeForce RTX 2060 SUPER', game, mode)
        self.assertEqual(weak, strong)
        generic = fps_outlook(60, 'GeForce RTX 5060', game, mode)
        self.assertEqual(generic['method'], 'synthetic_estimate')
        self.assertEqual(generic['sources'], [])

    def test_newer_cpu_is_preferred_when_it_fits_the_same_budget(self):
        old = (Obj(name='AMD Ryzen 7 1700'), Obj(name='RTX 2060 SUPER'), 18000, 80)
        modern = (Obj(name='AMD Ryzen 5 5600'), Obj(name='RTX 2060 SUPER'), 26000, 90)
        self.assertEqual(gaming_options([old, modern]), [modern])
        self.assertEqual(gaming_options([old]), [old])
        self.assertIn('Ryzen 5 5600', CPU_SEARCHES['AM4'])
        entry = (Obj(name='AMD Ryzen 5 5500'), Obj(name='RTX 3060'), 22000, 95)
        self.assertEqual(gaming_options([entry, modern]), [modern])
        slow_gpu = (modern[0], Obj(name='GTX 1050'), 16000, 35)
        self.assertEqual(gaming_options([entry, slow_gpu]), [entry, slow_gpu])

    def test_gaming_case_is_not_the_cheapest_old_office_case(self):
        def case(name, price, condition='new'):
            return Obj(name=name, price_rub=price, condition=condition, attributes='{}')
        old = case('PowerCool Slim V2', 350, 'used')
        office = case('Office ATX', 1800)
        gaming = case('DeepCool CC560 ARGB', 4500)
        mesh = case('Montech X3 Mesh', 5500)
        expensive = case('Premium RGB Mesh Glass', 22000)
        result = gaming_cases([old, office, gaming, mesh, expensive], 70000)
        self.assertIn(gaming, result)
        self.assertIn(mesh, result)
        self.assertNotIn(old, result)
        self.assertNotIn(office, result)
        self.assertNotIn(expensive, result)
        self.assertTrue(all(item.condition == 'new' for item in result))
        self.assertIn(old, gaming_cases([old, gaming], 70000, 'budget'))


if __name__ == '__main__':
    unittest.main()

import unittest
from app.services.calculator import calculate
from app.schemas.calculate import GameName, CalcMode

class UnlimitedResaleTests(unittest.TestCase):
    def test_resale_does_not_turn_unlimited_budget_into_sale_only_limit(self):
        base=dict(cpu_raw=21819,gpu_raw=17008,cpu_name="AMD Ryzen 5 5600",gpu_name="GeForce RTX 3060",game=GameName.CYBERPUNK,mode=CalcMode.MODE_1440P_HIGH,budget=None,target_fps=240,
            all_gpus=[{"id":100,"name":"GeForce RTX 5090","raw_score":65000,"avg_price":250000}],all_cpus=[])
        plain=calculate(**base)
        resale=calculate(**base,sell_mode="budget_plus_sell",gpu_price=3000)
        self.assertEqual(resale.upgrade_id, plain.upgrade_id)
        self.assertIsNotNone(plain.upgrade_id)

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as Row

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.partial_budget import partial_budget_plan, CATEGORIES


class PartialBudgetTests(unittest.TestCase):
    def pool(self, **prices):
        return {category: [Row(id=index*20+i, source='regard', category=category, price_rub=price)
                          for i, price in enumerate(prices.get(category, []))]
                for index, category in enumerate(CATEGORIES)}

    def test_41k_gpu_and_10k_cpu_are_not_proposed_for_a_50k_pc(self):
        pool = self.pool(CPU=[10000], GPU=[41000], storage=[5000], case=[3000])
        rows, plan = partial_budget_plan(pool, 50000)
        self.assertFalse(any(row.category == 'GPU' for row in rows))
        self.assertEqual(plan['known_parts_subtotal'], sum(row.price_rub for row in rows))
        self.assertLessEqual(plan['known_parts_subtotal'] + plan['reserved_for_missing'], 50000)

    def test_cheaper_gpu_is_selected_and_missing_parts_keep_a_reserve(self):
        pool = self.pool(CPU=[10000], GPU=[41000, 18000], storage=[5000], case=[3000])
        rows, plan = partial_budget_plan(pool, 50000)
        self.assertEqual(next(row for row in rows if row.category == 'GPU').price_rub, 18000)
        self.assertGreater(plan['reserved_for_missing'], 0)
        self.assertLessEqual(sum(row.price_rub for row in rows) + plan['reserved_for_missing'], 50000)

    def test_preferred_source_cannot_break_the_whole_pc_budget(self):
        pool = self.pool(CPU=[10000], GPU=[18000])
        pool['GPU'].append(Row(id=999, source='avito', category='GPU', price_rub=41000))
        rows, plan = partial_budget_plan(pool, 50000, 'avito')
        self.assertFalse(any(row.id == 999 for row in rows))
        self.assertLessEqual(plan['known_parts_subtotal'] + plan['reserved_for_missing'], 50000)

    def test_partial_result_does_not_pair_ryzen_with_intel_board(self):
        pool=self.pool(CPU=[7000],motherboard=[4000,5500])
        def compatible(rows,candidate):
            return candidate.category!='motherboard' or candidate.price_rub==5500
        rows,plan=partial_budget_plan(pool,50000,compatible=compatible)
        self.assertEqual(next(row.price_rub for row in rows if row.category=='motherboard'),5500)

    def test_compatible_board_is_not_lost_behind_twelve_cheaper_incompatible_boards(self):
        pool=self.pool(CPU=[7000],motherboard=list(range(1000,2400,100)))
        rows,_=partial_budget_plan(pool,50000,compatible=lambda rows,row:row.category!='motherboard' or row.price_rub==2300)
        self.assertTrue(any(row.category=='motherboard' for row in rows))


if __name__ == '__main__':
    unittest.main()

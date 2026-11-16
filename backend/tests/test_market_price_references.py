import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.market_price_references import planning_price_options, planning_price_reference


class MarketPriceReferenceTests(unittest.TestCase):
    def test_common_5600_reference_is_explicitly_not_a_purchase_quote(self):
        result = planning_price_reference('AMD Ryzen 5 5600 6-Core Processor', 'CPU')
        self.assertEqual(result['retail_price_rub'], 10799)
        self.assertEqual(result['used_price_rub'], 8500)
        self.assertEqual(result['used_discount_percent'], 21)
        self.assertFalse(result['is_purchase_quote'])

    def test_variant_names_do_not_inherit_base_model_reference(self):
        self.assertIsNone(planning_price_reference('AMD Ryzen 5 5600X', 'CPU'))
        self.assertIsNone(planning_price_reference('AMD Ryzen 7 5700X3D', 'CPU'))
        self.assertIsNone(planning_price_reference('GeForce RTX 5060 Ti', 'GPU'))
        self.assertIsNone(planning_price_reference('Radeon RX 7600 XT', 'GPU'))

    def test_budget_candidate_references_are_model_specific_and_deduplicated(self):
        results = planning_price_options(['Ryzen 5 5500', 'Ryzen 5 5600', 'Ryzen 5 5600'], 'CPU')
        self.assertEqual([item['key'] for item in results], ['ryzen55600'])

    def test_used_market_can_exceed_new_shop_reference_without_clamping(self):
        result = planning_price_reference('GeForce RTX 4060', 'GPU')
        self.assertLess(result['used_discount_percent'], 0)

    def test_current_common_gpu_reference_values_are_dated_and_have_sources(self):
        result = planning_price_reference('GeForce RTX 5060', 'GPU')
        self.assertEqual(result['observed_at'], '2026-11-13')
        self.assertEqual(result['retail_price_rub'], 53999)
        self.assertEqual(result['used_price_rub'], 46000)
        self.assertGreaterEqual(result['used_sample_count'], 3)
        self.assertIn('dns-shop.ru/search', result['retail_url'])
        self.assertIn('avito.ru/rossiya', result['market_url'])
        self.assertNotIn('thing-price.ru', result['market_url'] + result['retail_url'])


if __name__ == '__main__':
    unittest.main()

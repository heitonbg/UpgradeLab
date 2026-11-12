"""Small full-PC optima and independent locks; no external shops."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_adaptive_builds as fixtures
from app.db.models import Hardware
from unittest.mock import patch
from app.core.config import settings

class SmartBuilderTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.AdaptiveBuildTests();self.fixture.setUp();self.addCleanup(self.fixture.tearDown)
  self.fixture.add('GPU','GeForce RTX 4060',18000,3);self.fixture.db.commit()
 def test_small_full_pc_performance_optimum(self):
  result=self.fixture.build(budget=80000,objective='performance',pricing_mode='reference')
  self.assertEqual(next(p['id'] for p in result['parts'] if p['type']=='GPU'),3)
  self.assertEqual(len(result['parts']),8);self.assertEqual(result['total_price'],52500)
  self.assertEqual(sum(p['price'] for p in result['parts']),result['total_price'])
  self.assertFalse(result['purchase_ready']);self.assertFalse(result['solver_diagnostics']['global_optimum_proven'])
 def test_gpu_only_lock_survives_candidate_cap(self):
  with patch.object(settings,'builder_max_gpu_candidates',1):
   result=self.fixture.build(budget=80000,selected_gpu_id=3,pricing_mode='reference')
  for item in [result,*result['alternatives']]:self.assertEqual(next(p['id'] for p in item['parts'] if p['type']=='GPU'),3)
 def test_cpu_work_uses_cpu_mark_not_gaming_bonus(self):
  self.fixture.db.add(Hardware(id=4,type='CPU',name='AMD Ryzen 7 5700X',socket='AM4',raw_score=28000,normalized_score=65));self.fixture.db.commit()
  self.fixture.add('CPU','AMD Ryzen 7 5700X',9000,4);self.fixture.db.commit()
  result=self.fixture.build(budget=80000,workload='cpu_work',objective='performance',pricing_mode='reference')
  self.assertEqual(next(p['id'] for p in result['parts'] if p['type']=='CPU'),4)
  self.assertEqual(result['selection_score'],28000)
 def test_economy_minimum_among_full_fixture_builds(self):
  result=self.fixture.build(budget=80000,objective='economy',workload='cpu_work',pricing_mode='reference')
  self.assertEqual(result['total_price'],48500);self.assertEqual(len(result['parts']),8)
 def test_condition_filter_does_not_invent_used_offers(self):
  from app.services.offer_geography import offer_scope
  from app.services.planning_prices import reference_inventory
  from types import SimpleNamespace
  with offer_scope(SimpleNamespace(condition='used')):self.assertEqual(reference_inventory(self.fixture.db),[])

if __name__=='__main__':unittest.main()

"""Small exhaustive oracle for the explicit hardware-proxy objective."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as Obj

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.builds import build_options
from app.services.automatic_builds import storage_shortlist, cpu_gaming_percentile


class OptimizerV2OracleTests(unittest.TestCase):
    def setUp(self):
        cpus = [Obj(id=1, raw_score=100, name='CPU A'), Obj(id=2, raw_score=200, name='CPU B')]
        gpus = [Obj(id=3, raw_score=100, name='GPU A'), Obj(id=4, raw_score=200, name='GPU B')]
        # Each row represents one complete, compatible CPU/GPU/RAM composition.
        self.options = [(cpus[0], gpus[0], 50, 90, .45),
                        (cpus[1], gpus[0], 70, 95, .62),
                        (cpus[0], gpus[1], 80, 140, .70),
                        (cpus[1], gpus[1], 100, 150, .95)]
        self.score = lambda item: item[4]

    def selected(self, objective):
        return build_options(self.options, 60, objective=objective,
                             hardware_score=self.score)[0][3]

    def test_all_three_objectives_match_exhaustive_oracle(self):
        # The oracle checks every feasible complete composition without pruning.
        performance = max(self.options, key=lambda item: (item[4], -item[2]))
        economy = min(self.options, key=lambda item: (item[2], -item[4]))
        balanced = max(self.options, key=lambda item: (item[4] / item[2] ** .5, item[4], -item[2]))
        self.assertEqual(self.selected('performance'), performance)
        self.assertEqual(self.selected('economy'), economy)
        self.assertEqual(self.selected('balanced'), balanced)

    def test_performance_rank_uses_the_weakest_hardware_dimension(self):
        weak=(*self.options[1][:4], .95, .30, .90)
        strong=(*self.options[2][:5], .70, .80)
        result=build_options([weak,strong],60,objective='performance',
            hardware_score=lambda option:option[4],
            hardware_rank=lambda option:(option[5],option[6],option[4],-option[2]))
        self.assertEqual(result[0][3],strong)

    def test_multicore_mark_cannot_hide_a_weak_per_core_cpu_proxy(self):
        totals=[7000,16000,22000,27000,45000]
        per_core=[1750,2600,2900,3300,3600]
        many=cpu_gaming_percentile(Obj(raw_score=45000,cores=16),totals,per_core,'AM4')
        balanced=cpu_gaming_percentile(Obj(raw_score=27000,cores=8),totals,per_core,'AM4')
        self.assertGreater(many['total'],balanced['total'])
        self.assertLess(many['effective'],balanced['effective'])
        self.assertIsNone(cpu_gaming_percentile(Obj(raw_score=45000,cores=None),totals,per_core,'AM4')['per_core'])

    def test_ssd_frontier_keeps_affordable_1tb_nvme_and_separate_sources(self):
        drives=[Obj(id=1,source='regard',price_rub=9720),
                Obj(id=2,source='regard',price_rub=10500),
                Obj(id=3,source='regard',price_rub=11500),
                Obj(id=4,source='avito',price_rub=11300)]
        specs={1:{'interface':'SATA','capacity_gb':480},
               2:{'interface':'SATA','capacity_gb':1000},
               3:{'interface':'NVMe','capacity_gb':1000},
               4:{'interface':'NVMe','capacity_gb':1000}}
        self.assertEqual({item.id for item in storage_shortlist(drives,specs)}, {1,2,3,4})

    def test_economy_does_not_use_legacy_target_fps_as_a_gate(self):
        selected = build_options(self.options, 10000, objective='economy',
                                 hardware_score=self.score)[0][3]
        self.assertEqual(selected, min(self.options, key=lambda item: (item[2], -item[4])))

    def test_balanced_maximizes_the_weakest_normalized_hardware_dimension(self):
        cpu=Obj(id=11,raw_score=100,name='CPU balanced')
        gpu_weak=Obj(id=12,raw_score=200,name='GPU stronger')
        gpu_balanced=Obj(id=13,raw_score=150,name='GPU balanced')
        gpu_heavy=(cpu,gpu_weak,900,100,.90,.60)
        balanced=(cpu,gpu_balanced,950,95,.80,.80)
        result=build_options([gpu_heavy,balanced],60,objective='balanced',
            hardware_score=lambda item:item[4],hardware_rank=lambda item:(item[5],item[4],-item[2]))
        self.assertEqual(result[0][3],balanced)


if __name__ == '__main__':
    unittest.main()



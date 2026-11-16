import unittest,random
from types import SimpleNamespace as Obj
from unittest.mock import patch
from sqlalchemy import select,delete
import test_adaptive_builds as fixtures
from app.db.models import StoreOffer,Hardware
from app.services.builds import BuildRequest
from app.services.adaptive_builds import platform_candidates
from app.services.target_selection import target_variants
class TargetRankingTests(unittest.TestCase):
    def test_performance_spends_spare_budget_on_cpu_without_downgrading_gpu_or_fps(self):
        gpu=Obj(id=3)
        weak=(Obj(id=1,raw_score=19000),gpu,80000,150,0,0,0,0,0,.8)
        stronger=(Obj(id=2,raw_score=22000),gpu,85000,150,0,0,0,0,0,.8)
        slower=(Obj(id=4,raw_score=30000),gpu,88000,140,0,0,0,0,0,.8)
        self.assertEqual(target_variants([weak,stronger,slower],144,True)[0][3],stronger)
        self.assertEqual(target_variants([weak,stronger,slower],144)[0][3],weak)
    def test_exhaustive_small_oracle_hits_target_at_minimum_total_cost(self):
        rng=random.Random(41)
        for _ in range(50):
            options=[(Obj(id=i),Obj(id=100+i),rng.randrange(40000,120000),rng.randrange(40,160),0,0,0,0,0,.8) for i in range(20)]
            reached=[o for o in options if o[3]>=120]
            expected=min(reached,key=lambda o:(o[2],-o[3])) if reached else max(options,key=lambda o:(o[3],-o[2]))
            self.assertEqual(target_variants(options,120)[0][3],expected)
    def test_balance_breaks_same_cost_and_fps_ties(self):
        weak=(Obj(id=1),Obj(id=3),100,120,0,0,0,0,0,.2)
        balanced=(Obj(id=2),Obj(id=4),100,120,0,0,0,0,0,.8)
        self.assertEqual(target_variants([weak,balanced],120)[0][3],balanced)
    def test_requested_ddr5_is_not_silently_downgraded(self):
        p=BuildRequest(scenario='build',auto_parts=True,budget=120000,game='Cyberpunk 2077',mode='1440p_high',socket='AM5',ram_type='DDR5',ram_capacity_gb=16,selection_policy='target_fps')
        profiles=platform_candidates(p);self.assertTrue(profiles);self.assertEqual({x.ram_type for x in profiles},{'DDR5'});self.assertEqual({x.socket for x in profiles},{'AM5','LGA1700'})
class TargetIntegrationTests(unittest.TestCase):
    setUp=fixtures.AdaptiveBuildTests.setUp
    tearDown=fixtures.AdaptiveBuildTests.tearDown
    add=fixtures.AdaptiveBuildTests.add
    build=fixtures.AdaptiveBuildTests.build
    def test_cs2_4k_90k_prefers_5600_over_5500_with_same_gpu(self):
        self.db.add(Hardware(id=30,type='CPU',name='AMD Ryzen 5 5500',socket='AM4',raw_score=19000,normalized_score=45))
        cpu_offer=self.db.scalar(select(StoreOffer).where(StoreOffer.hardware_id==1))
        cpu_offer.price_rub=12290
        gpu_offer=self.db.scalar(select(StoreOffer).where(StoreOffer.hardware_id==2))
        gpu_offer.price_rub=30000
        self.add('CPU','AMD Ryzen 5 5500',9980,30)
        self.db.commit()
        with patch('app.services.automatic_builds.estimate_fps',return_value=150), patch('app.services.fps_v2.estimate_fps',return_value=150):
            result=self.build(budget=90000,game='CS2',mode='4k_high',target_fps=144,selection_policy='target_fps',objective='performance')
        self.assertEqual(next(part for part in result['parts'] if part['type']=='CPU')['id'],1)
        self.assertEqual(next(part for part in result['parts'] if part['type']=='GPU')['id'],2)
        self.assertLessEqual(result['total_price'],90000)
    def test_downgrade_gpu_for_budget_and_keep_target_pair_above_budget_separate(self):
        self.add('GPU','GeForce RTX 4060',30000,3);self.db.commit()
        with patch('app.services.automatic_builds.estimate_fps',side_effect=lambda cpu,gpu,*args:90 if gpu==15000 else 130), patch('app.services.fps_v2.estimate_fps',side_effect=lambda cpu,gpu,*args:90 if (gpu.raw_score if hasattr(gpu,'raw_score') else gpu)==15000 else 130):
            result=self.build(selection_policy='target_fps',target_fps=120)
        self.assertEqual(len(result['parts']),8);self.assertLessEqual(result['total_price'],50000);self.assertEqual(result['fps'],90)
        stretch=result['stretch_alternatives'][0];self.assertGreater(stretch['total_price'],50000);self.assertEqual(stretch['fps'],130)
        self.assertEqual(stretch['budget_shortfall'],stretch['total_price']-50000);self.assertTrue(stretch['over_budget'])
        self.assertTrue(all(v['total_price']<=50000 for v in result['alternatives']))
        self.assertEqual(result['memory_configuration']['modules'],2)
    def test_cheapest_complete_target_build_not_most_expensive_cpu(self):
        self.add('GPU','GeForce RTX 4060',15000,3);self.db.commit()
        with patch('app.services.automatic_builds.estimate_fps',side_effect=lambda cpu,gpu,*args:90 if gpu==15000 else 130), patch('app.services.fps_v2.estimate_fps',side_effect=lambda cpu,gpu,*args:90 if (gpu.raw_score if hasattr(gpu,'raw_score') else gpu)==15000 else 130):
            result=self.build(selection_policy='target_fps',target_fps=80)
        self.assertEqual(result['total_price'],48500);self.assertEqual(result['fps'],90);self.assertEqual(result['selection_basis'],'target_fps_then_complete_cost')
        self.assertIsNone(result['target_reached']);self.assertTrue(result['target_reached_by_model'])
    def test_cyberpunk_1440p_ddr5_target_120_with_120k_uses_cheaper_sufficient_cpu(self):
        self.db.add_all([Hardware(id=10,type='CPU',name='AMD Ryzen 5 7500F',socket='AM5',raw_score=27000,normalized_score=70),
            Hardware(id=11,type='CPU',name='AMD Ryzen 7 7800X3D',socket='AM5',raw_score=35000,normalized_score=90)])
        self.db.commit()
        self.add('CPU','AMD Ryzen 5 7500F',13000,10)
        self.add('CPU','AMD Ryzen 7 7800X3D',45000,11)
        self.add('motherboard','MSI PRO B650M-B DDR5',11000)
        self.add('memory','DDR5 2x8GB KIT',8000)
        self.add('GPU','GeForce RTX 4060',35000,3)
        self.db.commit()
        with patch('app.services.automatic_builds.estimate_fps',side_effect=lambda cpu,gpu,*args:75 if gpu==15000 else 125), patch('app.services.fps_v2.estimate_fps',side_effect=lambda cpu,gpu,*args:75 if (gpu.raw_score if hasattr(gpu,'raw_score') else gpu)==15000 else 125):
            result=self.build(selection_policy='target_fps',budget=120000,target_fps=120,game='Cyberpunk 2077',mode='1440p_high',socket='AM5',ram_type='DDR5')
        self.assertEqual(len(result['parts']),8);self.assertLessEqual(result['total_price'],120000)
        self.assertEqual(result['fps'],125);self.assertEqual(result['actual_config']['ram_type'],'DDR5')
        self.assertEqual(next(p for p in result['parts'] if p['type']=='CPU')['id'],10)
        self.assertEqual(result['memory_configuration']['modules'],2)

    def test_missing_board_does_not_receive_entire_unused_budget(self):
        self.db.execute(delete(StoreOffer).where(StoreOffer.category=='motherboard'));self.db.commit()
        result=self.build(selection_policy='target_fps',budget=120000,target_fps=120)
        self.assertEqual(result['status'],'partial');self.assertNotIn('fps',result)
        board=next(g for g in result['missing_parts'] if g['type']=='motherboard')
        self.assertLessEqual(board['budget_limit'],120000*.08)
        self.assertGreater(result['budget_plan']['unallocated_budget'],0)

    def test_auto_platform_search_includes_both_ram_generations_and_intel_sockets(self):
        p=BuildRequest(scenario='build',auto_parts=True,budget=120000,game='Cyberpunk 2077',mode='1440p_high',socket='AUTO',ram_type='AUTO',ram_capacity_gb=16,selection_policy='target_fps')
        profiles=platform_candidates(p)
        self.assertIn(('AM5','DDR5'), {(x.socket,x.ram_type) for x in profiles})
        self.assertIn(('AM4','DDR4'), {(x.socket,x.ram_type) for x in profiles})
        self.assertIn(('LGA1700','DDR4'), {(x.socket,x.ram_type) for x in profiles})
        self.assertIn(('LGA1700','DDR5'), {(x.socket,x.ram_type) for x in profiles})

    def test_intel_alternative_contains_its_own_board_and_two_stick_memory(self):
        self.db.add(Hardware(id=20,type='CPU',name='Intel Core i5-12400F',socket='LGA1700',raw_score=19000,normalized_score=52))
        self.db.commit()
        self.add('CPU','Intel Core i5-12400F',9000,20)
        self.add('motherboard','MSI PRO B760M-P DDR4',8000)
        self.add('memory','Kingston Fury 2x8GB DDR4 KIT',7000)
        self.db.commit()
        with patch('app.services.automatic_builds.estimate_fps',side_effect=lambda cpu,gpu,*args:100 if cpu==21000 else 105), patch('app.services.fps_v2.estimate_fps',side_effect=lambda cpu,gpu,*args:100 if (cpu.raw_score if hasattr(cpu,'raw_score') else cpu)==21000 else 105):
            result=self.build(selection_policy='target_fps',budget=60000,target_fps=100,game='Red Dead Redemption 2',mode='1440p_high',socket='AUTO',ram_type='AUTO')
        choices=[result,*result.get('alternatives',[])]
        intel=next((item for item in choices if item.get('actual_config',{}).get('socket')=='LGA1700'),None)
        self.assertIsNotNone(intel)
        self.assertEqual(len(intel['parts']),8)
        self.assertEqual(next(part for part in intel['parts'] if part['type']=='motherboard')['name'],'MSI PRO B760M-P DDR4')
        self.assertEqual(intel['memory_configuration']['modules'],2)

    def test_automatic_socket_can_be_constrained_to_either_memory_generation(self):
        for ram,expected in [('DDR4', {('AM4','DDR4'),('LGA1700','DDR4'),('LGA1200','DDR4')}),
                             ('DDR5', {('AM5','DDR5'),('LGA1700','DDR5')})]:
            p=BuildRequest(scenario='build',auto_parts=True,budget=120000,game='Cyberpunk 2077',mode='1440p_high',socket='AUTO',ram_type=ram,ram_capacity_gb=16,selection_policy='target_fps')
            self.assertEqual({(x.socket,x.ram_type) for x in platform_candidates(p)},expected)

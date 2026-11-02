"""A complete PC takes priority over an initially planned GPU or platform."""
import sys,json,unittest
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as Obj
from unittest.mock import patch
from sqlalchemy import create_engine,select,delete
from sqlalchemy.orm import Session
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db.base import Base
from app.db.models import Hardware,StoreOffer
from app.core.config import settings
from app.services.builds import assemble,BuildRequest
from app.services.automatic_builds import memory_configuration,memory_matches,cpu_board_matches


class AdaptiveBuildTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://');Base.metadata.create_all(self.engine);self.db=Session(self.engine)
        self.db.add_all([
            Hardware(id=1,type='CPU',name='AMD Ryzen 5 5600',socket='AM4',raw_score=21000,normalized_score=50),
            Hardware(id=2,type='GPU',name='Radeon RX 6600',raw_score=15000,normalized_score=50,vram=8),
            Hardware(id=3,type='GPU',name='GeForce RTX 4060',raw_score=19500,normalized_score=60,vram=8)])
        self.db.commit()
        for category,name,price,hw in [
            ('CPU','AMD Ryzen 5 5600',5000,1),('GPU','Radeon RX 6600',14000,2),
            ('motherboard','ASRock B450M-HDV R4.0 DDR4',10000,None),
            ('memory','DDR4 2x8GB',9000,None),('storage','Samsung 870 EVO 500GB',3000,None),
            ('psu','MSI MAG A650BN 650W',3500,None),('case','DeepCool CC560',3000,None),
            ('cooler','DeepCool AG400',1000,None)]:
            self.add(category,name,price,hw)
        self.db.commit()
        self.payload=dict(scenario='build',auto_parts=True,budget=50000,target_fps=60,
            game='Red Dead Redemption 2',mode='1440p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,
            price_sources=['avito'],allow_store_fallback=True)

    def add(self,category,name,price,hw=None,source='avito'):
        index=len(list(self.db.scalars(select(StoreOffer))))+len(self.db.new)+1000
        url=(f'https://www.avito.ru/moskva/tovary_dlya_kompyutera/fixture_{index}' if source=='avito'
             else f'https://www.regard.ru/product/{index}/fixture')
        row=StoreOffer(category=category,name=name,price_rub=price,hardware_id=hw,source=source,url=url,
            condition='new',attributes='{}',observed_at=datetime.utcnow(),origin='feed')
        self.db.add(row)
        return row

    def tearDown(self):self.db.close();self.engine.dispose()

    def build(self,**changes):
        with patch('app.services.builds.search_offers',return_value={}),patch.object(settings,'offers_browser_enabled',False):
            return assemble(BuildRequest(**{**self.payload,**changes}),self.db)

    def test_cheaper_gpu_frees_budget_for_complete_cpu_board_and_memory(self):
        self.add('GPU','GeForce RTX 4060',30000,3);self.db.commit()
        result=self.build()
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['total_price'],48500)
        self.assertEqual(len(result['parts']),8)
        self.assertEqual(next(part for part in result['parts'] if part['type']=='GPU')['name'],'Radeon RX 6600')
        self.assertTrue(result['budget_reallocated'])
        self.assertEqual(result['preferred_parts_count'],8)

    def test_retail_gpu_does_not_replace_a_complete_avito_pc(self):
        self.add('GPU','GeForce RTX 4060',15000,3,source='regard');self.db.commit()
        result=self.build(price_sources=['avito','regard'])
        self.assertEqual(result['preferred_parts_count'],8)
        self.assertTrue(all(part['price_source']=='Avito' for part in result['parts']))

    def test_avito_is_searched_before_returning_a_cached_retail_configuration(self):
        self.db.execute(delete(StoreOffer).where(StoreOffer.category=='GPU'))
        self.add('GPU','GeForce RTX 4060',15000,3,source='regard');self.db.commit()
        def search(db,request):
            if request.sources==['avito'] and request.category=='GPU':
                self.add('GPU','Radeon RX 6600',14000,2);db.commit()
            return {}
        with patch('app.services.builds.search_offers',side_effect=search) as lookup,patch.object(settings,'offers_browser_enabled',False):
            result=assemble(BuildRequest(**{**self.payload,'price_sources':['avito','regard']}),self.db)
        self.assertTrue(lookup.called)
        self.assertEqual(result['preferred_parts_count'],8)
        self.assertTrue(all(call.args[1].sources==['avito'] for call in lookup.call_args_list))

    def test_hybrid_keeps_more_avito_parts_when_retail_duplicates_are_cheaper(self):
        cpu=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='CPU'))
        cpu.source='regard';cpu.url='https://www.regard.ru/product/9900/cpu'
        self.add('GPU','Radeon RX 6600',13000,2,source='regard')
        self.add('motherboard','ASRock B450M-HDV R4.0 DDR4',5000,source='regard')
        self.db.commit()
        result=self.build(price_sources=['avito','regard'])
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['preferred_parts_count'],7)
        parts={part['type']:part for part in result['parts']}
        self.assertEqual(parts['GPU']['price_source'],'Avito')
        self.assertEqual(parts['motherboard']['price_source'],'Avito')
        self.assertLessEqual(result['total_price'],50000)

    def test_platform_is_replaced_as_a_compatible_set_and_reported_for_saving(self):
        result=self.build(socket='AM5',ram_type='DDR5')
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['actual_config']['socket'],'AM4')
        self.assertEqual(result['actual_config']['ram_type'],'DDR4')
        self.assertTrue(any('AM5/DDR5' in item for item in result['selection_changes']))
        locked=self.build(socket='AM5',ram_type='DDR5',allow_platform_change=False,allow_store_fallback=False)
        self.assertEqual(locked['status'],'partial')

    def test_memory_kit_capacity_is_the_sum_of_its_modules(self):
        for title in ['DDR4 2x8GB','DDR4 2х8 ГБ','DDR4 2 по 8 ГБ']:
            memory=Obj(name=title,attributes='{}')
            self.assertEqual(memory_configuration(memory)['capacity_gb'],16)
            self.assertTrue(memory_matches(memory,BuildRequest(**self.payload)))
        self.assertEqual(memory_configuration(Obj(name='DDR4 16GB',attributes='{}'))['modules'],1)
        self.assertFalse(memory_matches(Obj(name='DDR4 8GB',attributes='{}'),BuildRequest(**self.payload)))

    def test_single_module_is_allowed_without_a_dual_channel_fps_bonus(self):
        dual=self.build()
        row=self.db.scalar(select(StoreOffer).where(StoreOffer.category=='memory'))
        row.name='DDR4 16GB';self.db.commit()
        single=self.build()
        self.assertEqual(single['status'],'complete')
        self.assertEqual(single['memory_configuration']['modules'],1)
        self.assertLessEqual(single['fps'],dual['fps'])
        self.assertTrue(any('один модуль' in note for note in single['compatibility_notes']))

    def test_same_socket_does_not_make_intel_chipsets_interchangeable(self):
        cpu=Obj(name='Intel Core i5-8400')
        self.assertFalse(cpu_board_matches(cpu,Obj(name='ASUS H110')))
        self.assertFalse(cpu_board_matches(cpu,Obj(name='ASUS H110M-K')))
        self.assertTrue(cpu_board_matches(cpu,Obj(name='ASUS B360')))

    def test_a_small_ssd_share_overrun_does_not_block_an_affordable_complete_pc(self):
        self.db.scalar(select(StoreOffer).where(StoreOffer.category=='motherboard')).price_rub=5000
        self.db.scalar(select(StoreOffer).where(StoreOffer.category=='memory')).price_rub=3000
        self.db.scalar(select(StoreOffer).where(StoreOffer.category=='storage')).price_rub=10008
        self.db.commit()
        result=self.build()
        self.assertEqual(result['status'],'complete')
        self.assertLessEqual(result['total_price'],50000)
        self.assertTrue(result['budget_reallocated'])


if __name__=='__main__':unittest.main()

import sys
import unittest
import json
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.base import Base
from app.db.models import Hardware, HardwarePrice, StoreOffer
from app.api.calculate import post_calculate
from app.schemas.calculate import CalculateRequest
from app.services.calculator import meaningful_upgrade
from app.services.performance import cpu_capacity


class PlatformUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db=Session(self.engine)
        for ident,kind,name,score,socket in (
            (1,'CPU','AMD FX-6100 Six-Core',3709,'AM3+'),
            (2,'CPU','AMD FX-6120 Six-Core',3849,'AM3+'),
            (3,'GPU','GeForce GTX 1050 Ti',6368,None),
            (4,'CPU','AMD Ryzen 5 3600',17800,'AM4')):
            self.db.add(Hardware(id=ident,type=kind,name=name,raw_score=score,normalized_score=30,socket=socket))
        self.db.add(HardwarePrice(hardware_id=4,source='avito_snapshot',price_rub=4500,market='used_ru',
            source_url='https://www.avito.ru/cpu',observed_at=datetime.utcnow(),sample_count=3))
        for ident,category,name,price,condition in (
            (10,'motherboard','MSI A520M-A PRO DDR4 AM4',3000,'used'),
            (11,'memory','DDR4 16GB 2x8GB',1500,'used'),
            (12,'cooler','DeepCool AG300',1000,'new')):
            self.db.add(StoreOffer(id=ident,source='avito',category=category,name=name,price_rub=price,
                url=f'https://www.avito.ru/item_{ident}',condition=condition,observed_at=datetime.utcnow(),origin='feed',attributes='{}'))
        self.db.commit()
        self.payload={'cpu_id':1,'gpu_id':3,'game':'CS2','mode':'1080p_low','budget':10000,
                      'target_fps':180,'price_sources':['avito'],
                      'ram_manual':{'type':'DDR3','capacity_gb':8}}

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_tiny_fx_sidegrade_is_rejected_and_old_cpu_is_not_boosted_by_curve(self):
        self.db.query(StoreOffer).delete()
        self.db.query(HardwarePrice).delete()
        self.db.commit()
        request=CalculateRequest(**self.payload)
        result=post_calculate(request,self.db)
        self.assertIsNone(result.upgrade_id)
        self.assertFalse(any(card.get('id')==2 for card in result.alternatives))
        self.assertFalse(meaningful_upgrade(139,141))
        self.assertLess(cpu_capacity(3709,'AMD FX-6100 Six-Core',request.game,request.mode),80)

    def test_platform_includes_all_four_prices_retains_gpu_and_does_not_promise_target(self):
        result=post_calculate(CalculateRequest(**self.payload),self.db)
        self.assertEqual(result.upgrade_kind,'platform')
        self.assertEqual(result.upgrade_id,4)
        self.assertEqual(result.avg_price,10000)
        self.assertEqual({part['type'] for part in result.upgrade_parts},{'CPU','motherboard','memory','cooler'})
        self.assertEqual(result.avg_price,sum(part['price'] for part in result.upgrade_parts))
        self.assertGreater(result.upgraded_fps,result.current_fps)
        self.assertFalse(result.target_reached)
        self.assertTrue(result.within_budget)
        self.assertIn('GeForce GTX 1050 Ti',' '.join(result.compatibility_notes))
        self.assertIn('плата',result.recommendation)

    def test_selected_platform_is_recalculated_and_missing_or_wrong_offer_is_rejected(self):
        first=post_calculate(CalculateRequest(**self.payload),self.db)
        choice=next(card for card in first.alternatives if card['kind']=='platform')
        request=CalculateRequest(**{**self.payload,'selected_platform':choice['platform_selection']})
        again=post_calculate(request,self.db)
        self.assertEqual(again.upgrade_parts,first.upgrade_parts)
        self.db.get(StoreOffer,10).price_rub=9000
        self.db.commit()
        from fastapi import HTTPException
        with self.assertRaises(HTTPException): post_calculate(request,self.db)

    def test_missing_cooler_prevents_a_fake_complete_package(self):
        self.db.delete(self.db.get(StoreOffer,12))
        self.db.commit()
        result=post_calculate(CalculateRequest(**self.payload),self.db)
        self.assertNotEqual(result.upgrade_kind,'platform')
        self.assertFalse(any(card.get('kind')=='platform' for card in result.alternatives))

    def test_no_affordable_platform_shows_full_cost_and_budget_shortfall(self):
        result=post_calculate(CalculateRequest(**{**self.payload,'budget':8000}),self.db)
        self.assertIsNone(result.upgrade_id)
        card=next(card for card in result.alternatives if card['kind']=='platform')
        self.assertEqual(card['price'],10000)
        self.assertEqual(card['budget_shortfall'],2000)
        self.assertFalse(card['selection_allowed'])

    def test_platform_selection_and_all_prices_survive_server_save(self):
        from app.api.account import save_build
        from app.db.models import User, SavedBuild
        result=post_calculate(CalculateRequest(**self.payload),self.db)
        choice=next(card for card in result.alternatives if card['kind']=='platform')
        request=CalculateRequest(**{**self.payload,'selected_platform':choice['platform_selection']})
        user=User(id=1,email='platform@example.test',name='Test',password_hash='fixture')
        self.db.add(user)
        self.db.commit()
        saved=save_build(request,self.db,user)
        data=json.loads(self.db.get(SavedBuild,saved['id']).data)
        self.assertEqual(data['config']['selected_platform'],choice['platform_selection'])
        self.assertEqual(data['result']['upgrade_kind'],'platform')
        self.assertEqual(len(data['result']['upgrade_parts']),4)
        self.assertEqual(data['result']['avg_price'],10000)

    def test_observed_cooler_price_is_preferred_over_unverified_search_mismatch(self):
        self.db.get(StoreOffer,12).origin='product_page'
        self.db.add(StoreOffer(id=13,source='avito',category='cooler',name='DeepCool AG300',
            price_rub=400,url='https://www.avito.ru/item_13',condition='new',observed_at=datetime.utcnow(),
            origin='public_page',attributes='{}'))
        self.db.commit()
        result=post_calculate(CalculateRequest(**self.payload),self.db)
        cooler=next(part for part in result.upgrade_parts if part['type']=='cooler')
        self.assertEqual(cooler['price'],1000)

    def test_automatic_fx_resale_matches_unlinked_ads_and_makes_platform_affordable(self):
        for ident,price,name in ((20,500,'Процессор AMD FX-6100 AM3+'),
                                 (21,600,'AMD FX 6100'),(22,700,'AMD FX6100 Six-Core')):
            self.db.add(StoreOffer(id=ident,source='avito',category='CPU',name=name,price_rub=price,
                url=f'https://www.avito.ru/item_{ident}',condition='used',observed_at=datetime.utcnow(),
                origin='public_page',attributes='{}',hardware_id=None))
        self.db.add(StoreOffer(id=23,source='avito',category='CPU',name='AMD FX-6100 донор',price_rub=400,
            url='https://www.avito.ru/item_23',condition='used',observed_at=datetime.utcnow(),origin='public_page',attributes='{}'))
        self.db.commit()
        result=post_calculate(CalculateRequest(**{**self.payload,'budget':9500,'sell_mode':'budget_plus_sell'}),self.db)
        self.assertEqual(result.resale_status,'estimated')
        self.assertEqual(result.current_component_price,600)
        self.assertEqual(result.resale_price['sample_count'],3)
        self.assertEqual(result.total_budget,10100)
        self.assertEqual(result.upgrade_kind,'platform')
        self.assertTrue(result.within_budget)
        self.assertEqual(result.net_upgrade_cost,9400)

    def test_missing_automatic_resale_is_unknown_not_zero_or_over_budget_verdict(self):
        result=post_calculate(CalculateRequest(**{**self.payload,'budget':8000,'sell_mode':'budget_plus_sell'}),self.db)
        self.assertEqual(result.resale_status,'unavailable')
        self.assertIn('пока неизвестна',result.resale_notice)
        card=result.alternatives[0]
        self.assertIsNone(card['resale_value'])
        self.assertIsNone(card['net_cost'])
        self.assertIsNone(card['budget_shortfall'])
        self.assertEqual(card['cash_shortfall'],2000)
        self.assertEqual(card['selection_block_reason'],'resale_price_unavailable')
        self.assertFalse(card['selection_allowed'])

    def test_fx_refresh_uses_short_exact_model_name(self):
        from unittest.mock import patch
        from app.services.upgrade_prices import refresh_avito
        from app.core.config import settings
        import time
        queries=[]
        def search(db,payload):
            queries.append(payload.query)
            return {'sources':[{'source':'avito','status':'unavailable'}]}
        with patch('app.services.store_providers.source_blocked',return_value=False),patch.object(settings,'offers_browser_enabled',False):
            refresh_avito(self.db,[],self.db.get(Hardware,1),self.db.get(Hardware,3),time.monotonic()+1,search)
        self.assertEqual(queries,['AMD FX-6100'])

    def test_real_low_prices_for_legacy_cpu_are_not_lost_to_generic_300_ruble_floor(self):
        for ident,price in ((20,100),(21,200),(22,300)):
            self.db.add(StoreOffer(id=ident,source='avito',category='CPU',name='Процессор AMD FX-6100',price_rub=price,
                url=f'https://www.avito.ru/item_{ident}',condition='used',observed_at=datetime.utcnow(),
                origin='public_page',attributes='{}',hardware_id=None))
        self.db.commit()
        result=post_calculate(CalculateRequest(**{**self.payload,'sell_mode':'budget_plus_sell'}),self.db)
        self.assertEqual(result.resale_status,'estimated')
        self.assertEqual(result.current_component_price,200)
        self.assertEqual(result.resale_price['sample_count'],3)

    def test_one_fx_listing_is_enough_for_automatic_resale_and_is_not_an_average(self):
        self.db.add(StoreOffer(id=20,source='avito',category='CPU',name='Процессор AMD FX6100',price_rub=600,
            url='https://www.avito.ru/item_12345678',condition='used',observed_at=datetime.utcnow(),
            origin='public_page',attributes='{}',hardware_id=None))
        self.db.commit()
        result=post_calculate(CalculateRequest(**{**self.payload,'budget':9500,'sell_mode':'budget_plus_sell'}),self.db)
        self.assertEqual(result.current_component_price,600)
        self.assertEqual(result.total_budget,10100)
        self.assertEqual(result.resale_price['average_method'],'one_offer')
        self.assertEqual(result.resale_price['sample_count'],1)
        self.assertEqual(result.resale_price['price_url'],'https://www.avito.ru/item_12345678')
        self.assertTrue(result.within_budget)

    def test_failed_avito_search_tries_compact_model_discovery_and_reads_a_real_offer(self):
        import time
        from unittest.mock import patch
        from app.services.upgrade_prices import refresh_avito, avito_price_estimates
        from app.services.offers import upsert
        from app.schemas.offers import OfferInput
        from app.core.config import settings
        attempts=[]
        def search(db,payload):
            attempts.append((payload.query,payload.method))
            if payload.method=='http':
                return {'sources':[{'source':'avito','status':'unavailable'}], 'offers':[]}
            row=OfferInput(source='avito',category='CPU',name='AMD FX-6100 AM3+',price_rub=600,
                url='https://www.avito.ru/moskva/tovary_dlya_kompyutera/fx_6100_12345678',condition='used',
                observed_at=datetime.utcnow())
            upsert(db,[row],'browser_page')
            return {'sources':[{'source':'avito','status':'browser_page'}], 'offers':[{'price_rub':600}]}
        with patch('app.services.store_providers.source_blocked',return_value=False),patch.object(settings,'offers_browser_enabled',True):
            refresh_avito(self.db,[],self.db.get(Hardware,1),self.db.get(Hardware,3),time.monotonic()+2,search,single_offer_fallback=True)
        self.assertEqual(attempts,[('AMD FX-6100','http'),('fx6100','discovery')])
        self.assertEqual(avito_price_estimates(self.db)[1].price_rub,600)


if __name__=='__main__': unittest.main()

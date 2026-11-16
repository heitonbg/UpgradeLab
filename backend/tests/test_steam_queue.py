import asyncio,json,tempfile,time,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine,select,func,update
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.db.base import Base
from app.db.models import Hardware,SteamRequirements,SteamEnrichmentTask as Task,SteamSourceState
from app.services.steam_storage import request_requirements,read_status,local_game,claim,finish_task,fail_task,reserve_request,ensure_schema,with_requirements,enriched_profile
from app.services.steam_http import SteamFailure
from app.services.game_catalog import search_games
from app.services.adaptive_fps import predict_adaptive_fps
from app.workers.steam_requirements_worker import Worker
from test_steam_http_parser import fixture,catalog_rows

GAME='Clair Obscur: Expedition 33'
NOW=datetime(2026,11,16,5,0)
class SteamFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'steam.db';self.engine=create_engine('sqlite:///'+self.path.as_posix(),connect_args={'check_same_thread':False,'timeout':20})
        self.addCleanup(self.engine.dispose);Base.metadata.create_all(self.engine)
        cpus,gpus=catalog_rows()
        with Session(self.engine) as db:
            for h in [*cpus,*gpus]:db.add(Hardware(id=h.id,type=h.type,name=h.name,raw_score=h.raw_score,normalized_score=h.raw_score,socket='AM4' if h.type=='CPU' else None))
            db.commit()
        self.gid=str(local_game(GAME)['id'])
        with Session(self.engine) as db:read_status(db,GAME)
    def enqueue(self,game=GAME,now=None):
        with Session(self.engine) as db:return request_requirements(db,game,now=now)
class SteamQueueTests(SteamFixture):
    def test_hundred_concurrent_selections_create_one_task(self):
        with ThreadPoolExecutor(max_workers=20) as pool:results=list(pool.map(lambda _:self.enqueue(),range(100)))
        with Session(self.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(Task)),1)
        self.assertTrue(all(r['status']=='queued' for r in results))
    def test_two_games_create_two_tasks(self):
        self.enqueue();self.enqueue('Portal 2')
        with Session(self.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(Task)),2)
    def test_lease_atomic_claim_and_restart(self):
        self.enqueue(now=NOW)
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda owner:claim(self.engine,owner,NOW),['a','b']))
        first=next(r for r in rows if r);self.assertEqual(sum(r is not None for r in rows),1)
        self.assertIsNone(claim(self.engine,'restart',NOW+timedelta(seconds=119)))
        later=claim(self.engine,'restart',NOW+timedelta(seconds=121));self.assertEqual(later['id'],first['id']);self.assertEqual(later['attempts'],2)
        self.assertIsNone(finish_task(self.engine,first,first['lease_owner'],fixture(),1903340,NOW+timedelta(seconds=122)))
    def test_exhausted_crashed_lease_is_terminal(self):
        self.enqueue(now=NOW)
        for i in range(3):self.assertIsNotNone(claim(self.engine,str(i),NOW+timedelta(seconds=i*121)))
        self.assertIsNone(claim(self.engine,'again',NOW+timedelta(seconds=400)))
        with Session(self.engine) as db:self.assertEqual(db.scalar(select(Task.status)),'failed')
    def test_failures_stop_after_bounded_attempts(self):
        self.enqueue(now=NOW)
        for i in range(3):
            now=NOW+timedelta(minutes=i*5);task=claim(self.engine,'owner',now);self.assertIsNotNone(task)
            fail_task(self.engine,task,'owner',SteamFailure('http_503',transient=True),now)
        self.assertIsNone(claim(self.engine,'owner',NOW+timedelta(hours=1)))
        with Session(self.engine) as db:self.assertEqual(db.scalar(select(Task.status)),'failed')
    def test_retry_after_and_source_cooldown_persist(self):
        self.enqueue(now=NOW);task=claim(self.engine,'owner',NOW)
        fail_task(self.engine,task,'owner',SteamFailure('http_429',retry_after=600,transient=True),NOW)
        self.assertEqual(reserve_request(self.engine,NOW+timedelta(seconds=1)),599)
        with Session(self.engine) as db:self.assertEqual(db.get(Task,task['id']).next_attempt_at,NOW+timedelta(seconds=600))
    def test_403_cools_source_for_day(self):
        self.enqueue(now=NOW);task=claim(self.engine,'owner',NOW)
        fail_task(self.engine,task,'owner',SteamFailure('http_403'),NOW)
        self.assertGreaterEqual(reserve_request(self.engine,NOW),86400)
    def test_request_spacing_is_persistent(self):
        self.assertEqual(reserve_request(self.engine,NOW),0)
        self.assertGreaterEqual(reserve_request(self.engine,NOW),3)
    def test_positive_cache_and_idempotent_refresh(self):
        self.enqueue(now=NOW);task=claim(self.engine,'owner',NOW);p=finish_task(self.engine,task,'owner',fixture(),1903340,NOW)
        again=self.enqueue(now=NOW+timedelta(days=1));self.assertEqual(again['status'],'available');self.assertFalse(again['refresh_pending'])
        self.assertIsNone(claim(self.engine,'owner',NOW+timedelta(days=1)))
        with Session(self.engine) as db:
            row=db.get(SteamRequirements,self.gid);version=row.content_sha256;row.expires_at=NOW;db.commit()
        self.enqueue(now=NOW+timedelta(days=31));task=claim(self.engine,'owner',NOW+timedelta(days=31));finish_task(self.engine,task,'owner',fixture(),1903340,NOW+timedelta(days=31))
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(SteamRequirements)),1);self.assertEqual(db.scalar(select(func.count()).select_from(Task)),1)
            self.assertEqual(db.get(SteamRequirements,self.gid).content_sha256,version)
    def test_missing_recommended_negative_cache(self):
        self.enqueue('Portal 2',NOW);task=claim(self.engine,'owner',NOW);finish_task(self.engine,task,'owner',fixture(620),620,NOW)
        result=self.enqueue('Portal 2',NOW+timedelta(days=1));self.assertEqual(result['status'],'no_recommended');self.assertFalse(result['refresh_pending'])
        self.assertIsNone(claim(self.engine,'owner',NOW+timedelta(days=1)))
    def test_empty_update_does_not_erase_old_data(self):
        self.enqueue(now=NOW);task=claim(self.engine,'owner',NOW);finish_task(self.engine,task,'owner',fixture(),1903340,NOW)
        with Session(self.engine) as db:row=db.get(SteamRequirements,self.gid);old=row.content_sha256;row.expires_at=NOW;db.commit()
        self.enqueue(now=NOW+timedelta(days=31));task=claim(self.engine,'owner',NOW+timedelta(days=31));empty={**fixture(),'pc_requirements':{}}
        finish_task(self.engine,task,'owner',empty,1903340,NOW+timedelta(days=31))
        with Session(self.engine) as db:self.assertEqual(db.get(SteamRequirements,self.gid).content_sha256,old)
    def test_disabled_worker_does_not_block_local_api(self):
        from app.api.steam_requirements import router
        from app.api.deps import get_db
        app=FastAPI();app.include_router(router)
        def db():
            with Session(self.engine) as session:yield session
        app.dependency_overrides[get_db]=db
        with TestClient(app) as c:
            start=time.perf_counter();r=c.post('/api/games/requirements',json={'game':GAME})
            self.assertEqual(r.status_code,200);self.assertEqual(r.json()['status'],'queued');self.assertLess(time.perf_counter()-start,1)
            self.assertEqual(c.get('/api/games/requirements',params={'game':GAME}).status_code,200)
            self.assertEqual(c.post('/api/games/requirements',json={'game':'https://example.com'}).status_code,404)
    def test_schema_addition_creates_verified_backup_and_preserves_rows(self):
        other=Path(self.temp.name)/'legacy.db';engine=create_engine('sqlite:///'+other.as_posix())
        try:
            with engine.begin() as c:c.exec_driver_sql('CREATE TABLE old_accounts(id INTEGER PRIMARY KEY,name TEXT)');c.exec_driver_sql("INSERT INTO old_accounts VALUES(1,'kept')")
            saved=ensure_schema(engine);self.assertTrue(saved.is_file());self.assertIsNone(ensure_schema(engine))
            with engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT name FROM old_accounts').scalar(),'kept')
        finally:engine.dispose()
    def test_reversed_words_find_exact_game(self):
        r=search_games('33 expedition',5);self.assertEqual(r['items'][0]['name'],GAME);self.assertEqual(str(r['items'][0]['steam_app_id']),'1903340')
    def test_hardware_scores_are_not_modified(self):
        self.enqueue(now=NOW);task=claim(self.engine,'owner',NOW)
        with Session(self.engine) as db:before=list(db.execute(select(Hardware.id,Hardware.raw_score)))
        finish_task(self.engine,task,'owner',fixture(),1903340,NOW)
        with Session(self.engine) as db:self.assertEqual(list(db.execute(select(Hardware.id,Hardware.raw_score))),before)

class SteamWorkerTests(SteamFixture):
    def test_worker_downloads_once_then_cache_reuses(self):
        self.enqueue()
        class Fake:
            calls=0
            async def details(self,appid):self.calls+=1;return fixture()
            async def search(self,title):raise AssertionError('known AppID must not search')
        client=Fake();worker=Worker(self.engine,client)
        self.assertTrue(asyncio.run(worker.run_once()));self.assertFalse(asyncio.run(worker.run_once()))
        self.assertEqual(self.enqueue()['status'],'available');self.assertEqual(client.calls,1)
    def test_title_mismatch_is_not_imported(self):
        self.enqueue()
        class Fake:
            async def details(self,appid):return {**fixture(),'name':'A different game demo'}
        asyncio.run(Worker(self.engine,Fake()).run_once())
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(SteamRequirements)),0)
            self.assertEqual(db.scalar(select(Task.last_error)),'game_title_mismatch')
    def test_enriched_profile_reaches_existing_model_and_ignores_ram(self):
        self.enqueue();task=claim(self.engine,'owner');finish_task(self.engine,task,'owner',fixture(),1903340)
        @with_requirements
        def predict(payload,db):
            cpus=list(db.scalars(select(Hardware).where(Hardware.type=='CPU')));gpus=list(db.scalars(select(Hardware).where(Hardware.type=='GPU')))
            return predict_adaptive_fps(cpus[2],gpus[0],GAME,payload.settings,cpu_catalog=cpus,gpu_catalog=gpus)
        from types import SimpleNamespace
        with Session(self.engine) as db:
            a=predict(SimpleNamespace(game=GAME,settings={'resolution':'1080p','preset':'high'}),db)
            b=predict(SimpleNamespace(game=GAME,settings={'resolution':'1080p','preset':'high','ram_type':'DDR3','ram_channels':1,'ram_capacity_gb':4}),db)
        self.assertEqual(a['average_fps'],b['average_fps']);self.assertEqual(a['requirements_enrichment']['status'],'available')
        scenario=a['requirements_anchored_estimate'];self.assertTrue(scenario['available']);self.assertEqual(scenario['requirements']['source_url'],'https://store.steampowered.com/app/1903340/')

    def test_new_requirements_reach_1440p_and_4k_scenario(self):
        self.enqueue();task=claim(self.engine,'owner');finish_task(self.engine,task,'owner',fixture(),1903340)
        @with_requirements
        def predict(payload,db):
            cpus=list(db.scalars(select(Hardware).where(Hardware.type=='CPU')));gpus=list(db.scalars(select(Hardware).where(Hardware.type=='GPU')))
            return predict_adaptive_fps(cpus[2],gpus[0],GAME,payload.settings,cpu_catalog=cpus,gpu_catalog=gpus)
        from types import SimpleNamespace
        values=[]
        with Session(self.engine) as db:
            for resolution in ('1080p','1440p','4K'):
                r=predict(SimpleNamespace(game=GAME,settings={'resolution':resolution,'preset':'high'}),db)
                scenario=r.get('requirements_anchored_estimate') or {}
                self.assertTrue(scenario.get('available'),scenario)
                self.assertFalse(scenario.get('developer_target_used_as_measurement'))
                self.assertEqual(scenario['developer_target']['fps'],60)
                values.append(r['average_fps'])
        self.assertGreaterEqual(values[0],values[1]);self.assertGreaterEqual(values[1],values[2])

    def test_missing_appid_search_verifies_exact_title_not_first_item(self):
        self.enqueue()
        class Fake:
            calls=[]
            async def search(self,title):
                self.calls.append('search')
                return {'items':[{'id':123,'name':GAME+' Deluxe Edition Upgrade','type':'app'},{'id':1903340,'name':GAME,'type':'app'}]}
            async def details(self,appid):
                self.calls.append(appid);return fixture()
        client=Fake()
        game={'id':self.gid,'name':GAME,'aliases':[]}
        with patch('app.workers.steam_requirements_worker.local_game',return_value=game):
            asyncio.run(Worker(self.engine,client).run_once())
        self.assertEqual(client.calls,['search',1903340])
        with Session(self.engine) as db:self.assertEqual(db.get(SteamRequirements,self.gid).app_id,1903340)

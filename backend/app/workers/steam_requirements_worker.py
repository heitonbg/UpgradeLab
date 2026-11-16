"""One low-rate worker per SQLite file. Run: python -m app.workers.steam_requirements_worker."""
from __future__ import annotations
import asyncio,logging,signal,os
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.price_time import db_now
from app.db.base import engine
from app.db.models import SteamRequirements,SteamSourceState
from app.services.steam_http import SteamClient,SteamFailure,app_id
from app.services.steam_storage import ensure_schema,local_game,claim,finish_task,fail_task,reserve_request
from app.services.game_catalog import key as game_key

LOG=logging.getLogger('steam_requirements')

def title_key(value):
    return game_key(str(value).replace('™','').replace('®','').replace('©',''))

def matching_title(game,title):
    return title_key(title) in {title_key(value) for value in [game['name'],*game.get('aliases',[])]}

class Worker:
    def __init__(self,engine=engine,client=None):
        self.engine=engine;self.owner=uuid4().hex;self.client=client
    async def permit(self):
        while True:
            delay=reserve_request(self.engine)
            if delay<=0:return
            await asyncio.sleep(min(delay,5))
    def cooldown(self):
        with Session(self.engine) as db:
            row=db.get(SteamSourceState,'steam_store')
            return bool(row and row.cooldown_until and row.cooldown_until>db_now())
    async def run_once(self):
        if self.cooldown():return False
        task=claim(self.engine,self.owner)
        if task is None:return False
        try:
            game=local_game(task['game_id'])
            if not game:raise SteamFailure('unknown_catalog_game')
            with Session(self.engine) as db:
                saved=db.get(SteamRequirements,task['game_id'])
                raw=saved.app_id if saved and saved.app_id else game.get('steam_app_id') or game.get('appid')
            try:appid=app_id(raw)
            except ValueError:appid=None
            if appid is None:
                results=await self.client.search(game['name'])
                candidates=[]
                for item in results.get('items',[]):
                    if isinstance(item,dict) and item.get('type') in (None,'app','game') and matching_title(game,item.get('name','')):
                        try:candidates.append(app_id(item.get('id')))
                        except ValueError:pass
                unique=set(candidates)
                if len(unique)!=1:raise SteamFailure('appid_not_uniquely_resolved')
                appid=unique.pop()
            details=await self.client.details(appid)
            if not matching_title(game,details.get('name','')):raise SteamFailure('game_title_mismatch')
            parsed=finish_task(self.engine,task,self.owner,details,appid)
            LOG.info('steam_task id=%s status=completed parsing=%s',task['id'],(parsed or {}).get('parsing_status'))
        except SteamFailure as exc:
            fail_task(self.engine,task,self.owner,exc)
            LOG.warning('steam_task id=%s status=deferred code=%s',task['id'],exc.code)
        except Exception as exc:
            fail_task(self.engine,task,self.owner,SteamFailure('worker_'+type(exc).__name__,transient=True))
            LOG.exception('steam_task id=%s status=error',task['id'])
        return True
    async def run(self,stop=None):
        stop=stop or asyncio.Event()
        async with SteamClient(before_request=self.permit) as client:
            self.client=client
            while not stop.is_set():
                if not await self.run_once():
                    try:await asyncio.wait_for(stop.wait(),timeout=settings.steam_worker_idle_seconds)
                    except TimeoutError:pass

async def _run():
    worker=Worker();stop=asyncio.Event()
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        try:loop.add_signal_handler(sig,stop.set)
        except NotImplementedError:pass
    await worker.run(stop)

def main():
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(name)s %(message)s')
    if not settings.steam_requirements_enabled:return
    database=engine.url.database
    if engine.url.get_backend_name()!='sqlite' or not database or database==':memory:':
        raise RuntimeError('steam_worker_requires_file_sqlite')
    Path(database).resolve().parent.mkdir(parents=True,exist_ok=True)
    # OS lock covers the worker lifetime, not only the lease claim. Shared SQLite deployments have one requester.
    from scripts.startup import bootstrap_lock
    from app.services.catalog_files import CatalogError
    try:
        with bootstrap_lock(Path(database).with_name('steam-requirements-worker')):
            ensure_schema(engine)
            LOG.info('steam_worker status=started pid=%s interval=%s',os.getpid(),settings.steam_request_interval_seconds)
            asyncio.run(_run())
    except CatalogError as exc:
        if str(exc)!='bootstrap_already_running':raise
        LOG.info('steam_worker status=skipped code=another_worker')

if __name__=='__main__':main()

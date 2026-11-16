"""LOCAL TEST ONLY: fixture worker/control endpoints; never deploy this module."""
import os,sys,json,sqlite3
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(BACKEND))
r=Path(os.getenv('STEAM_E2E_DIR',str(BACKEND.parent/'.artifacts/steam-e2e'))).resolve()
r.mkdir(parents=True,exist_ok=True)
target=r/'steam-amvera-e2e.db'
os.environ.update(DATABASE_URL='sqlite:///'+target.as_posix(),AMVERA='0',STEAM_WORKER_ENABLED='false',CORS_ORIGINS='http://127.0.0.1:5174',REGARD_BOOTSTRAP_ON_START='false',REGARD_DAILY_SYNC_ENABLED='false',REGARD_DOWNLOAD_ENABLED='false')
from app.main import app
from app.db.base import engine
from app.services.steam_http import SteamFailure
from app.workers.steam_requirements_worker import Worker
from app.services.steam_storage import _hardware_for_ready
fixture=json.loads((BACKEND/'tests/fixtures/steam/1903340.json').read_text(encoding='utf-8'))
class FixtureClient:
 async def details(self,appid):
  if appid==1903340:return fixture
  return {'name':'Portal 2','type':'game','steam_appid':620,'pc_requirements':{'minimum':'<b>OS:</b> Windows','recommended':''}}
 async def search(self,title):return {'items':[]}
@app.post('/__test__/reset')
def reset():
 with engine.begin() as c:
  for name in ('steam_requirements','steam_enrichment_tasks','steam_source_state'):
   c.exec_driver_sql('DELETE FROM '+name)
 return {'ok':True}
@app.post('/__test__/work')
async def work(mode:str='ok'):
 class Client(FixtureClient):
  async def details(self,appid):
   if mode=='error':raise SteamFailure('http_503',transient=True)
   return await super().details(appid)
 worker=Worker(engine,Client()); ran=await worker.run_once()
 return {'ran':ran}
if __name__=='__main__':
 import uvicorn
 uvicorn.run(app,host='127.0.0.1',port=8005)

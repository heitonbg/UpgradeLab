import os
import json,time,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
report={};root=Path(os.getenv('STEAM_E2E_DIR',str(Path(__file__).resolve().parents[1]/'.artifacts/steam-e2e')));root.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.getenv('STEAM_E2E_BROWSER') or (r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' if os.name=='nt' else None),headless=True)
 page=b.new_page();page.set_default_timeout(20000)
 api=page.request;assert api.post('http://127.0.0.1:8005/__test__/reset').ok
 responses=[];errors=[]
 page.on('response',lambda res:responses.append(res) if '/api/calculate' in res.url and res.request.method=='POST' else None)
 page.on('pageerror',lambda error:errors.append(str(error)))
 page.goto('http://127.0.0.1:5174/?tab=calculator&scenario=upgrade');page.wait_for_timeout(1200)
 page.get_by_placeholder('Найти процессор',exact=True).fill('Ryzen 5 5600');page.get_by_role('option',name=re.compile(r'^AMD Ryzen 5 5600(?:\s|$)')).click()
 page.get_by_placeholder('Найти видеокарту',exact=True).fill('RTX 3060 Ti');page.get_by_role('option',name=re.compile(r'^GeForce RTX 3060 Ti(?:\s|$)')).click()
 page.get_by_role('button',name='Продолжить',exact=True).filter(visible=True).click()
 game=page.locator('input[placeholder="Найдите игру…"]:visible');game.fill('33 expedition');page.get_by_role('option',name='Clair Obscur: Expedition 33',exact=True).click()
 page.get_by_role('combobox',name='Разрешение и графика',exact=True).filter(visible=True).click();page.get_by_role('option',name='1080p High',exact=True).click()
 page.get_by_role('button',name='Продолжить',exact=True).filter(visible=True).click();page.get_by_role('button',name='Продолжить',exact=True).filter(visible=True).click()
 page.get_by_role('button',name='Рассчитать производительность',exact=True).click()
 page.wait_for_function("document.querySelector('.upgrade-result')!==null",timeout=90000)
 report['fallback_rendered']=True
 assert responses,'No calculate response';before=responses[-1].json();report['before_fps']=before.get('current_fps');report['before_version']=before.get('fps_result',{}).get('current',{}).get('requirements_enrichment',{}).get('version')
 for _ in range(5):
  state=api.get('http://127.0.0.1:8005/api/games/requirements',params={'game':'Clair Obscur: Expedition 33'}).json()
  if state['status']=='available':break
  assert api.post('http://127.0.0.1:8005/__test__/work').ok
 n=len(responses)
 deadline=time.monotonic()+20
 while time.monotonic()<deadline and len(responses)==n:page.wait_for_timeout(250)
 report['automatic_recalculations']=len(responses)-n
 report['state']=api.get('http://127.0.0.1:8005/api/games/requirements',params={'game':'Clair Obscur: Expedition 33'}).json()['status']
 report['after_fps']=responses[-1].json().get('current_fps')
 report['after_version']=responses[-1].json().get('fps_result',{}).get('current',{}).get('requirements_enrichment',{}).get('version')
 expect(page.locator('.upgrade-result')).to_contain_text(str(report['after_fps'])+' FPS')
 page.screenshot(path=str(root/'steam-e2e-refreshed.png'),full_page=True)
 report['page_errors']=errors
 (root/'steam-browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False));assert report['automatic_recalculations']==1;assert report['after_version'];assert not errors
 b.close()

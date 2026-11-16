import os
import json,re,time
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(os.getenv('STEAM_E2E_DIR',str(Path(__file__).resolve().parents[1]/'.artifacts/steam-e2e')));root.mkdir(parents=True,exist_ok=True)
report={};apiurl='http://127.0.0.1:8005';ui='http://127.0.0.1:5174/?tab=calculator&scenario=upgrade'
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.getenv('STEAM_E2E_BROWSER') or (r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' if os.name=='nt' else None),headless=True)
 def open_game(name):
  page=b.new_page();page.set_default_timeout(15000)
  page.add_init_script('const realTimeout=window.setTimeout;window.setTimeout=(fn,ms,...args)=>realTimeout(fn,ms===5000?100:ms,...args)')
  page.goto(ui);page.wait_for_timeout(700)
  page.get_by_placeholder('Найти процессор',exact=True).fill('Ryzen 5 5600');page.get_by_role('option',name=re.compile(r'^AMD Ryzen 5 5600(?:\s|$)')).click()
  page.get_by_placeholder('Найти видеокарту',exact=True).fill('RTX 3060 Ti');page.get_by_role('option',name=re.compile(r'^GeForce RTX 3060 Ti(?:\s|$)')).click()
  page.get_by_role('button',name='Продолжить',exact=True).filter(visible=True).click()
  game=page.locator('input[placeholder="Найдите игру…"]:visible');game.fill(name)
  label='Clair Obscur: Expedition 33' if name=='33 expedition' else name
  page.get_by_role('option',name=label,exact=True).click()
  return page
 def state(page,game):return page.request.get(apiurl+'/api/games/requirements',params={'game':game}).json()
 request=b.new_context().request
 request.post(apiurl+'/__test__/reset')
 page=open_game('Portal 2')
 for _ in range(4):
  page.request.post(apiurl+'/__test__/work')
  if state(page,'Portal 2')['status']=='no_recommended':break
 page.wait_for_timeout(500)
 report['no_recommended']=state(page,'Portal 2')['status']=='no_recommended'
 page.close();cached=open_game('Portal 2');report['negative_cache']=state(cached,'Portal 2')['status']=='no_recommended';cached.close()
 request.post(apiurl+'/__test__/reset')
 page=open_game('33 expedition');gets=[]
 page.on('request',lambda req:gets.append(req.url) if '/api/games/requirements?' in req.url else None)
 for _ in range(4):
  page.request.post(apiurl+'/__test__/work?mode=error')
  if state(page,'Clair Obscur: Expedition 33').get('task',{}).get('last_error'):break
 page.wait_for_timeout(2200);count=len(gets);page.wait_for_timeout(700)
 report['error_poll_count']=count
 report['steam_error_bounded_polling']=len(gets)==count and 0<count<=12
 report['error_state']=state(page,'Clair Obscur: Expedition 33')['status'];page.close()
 request.post(apiurl+'/__test__/reset')
 page=open_game('33 expedition');gets=[];page.on('request',lambda req:gets.append(req.url) if '/api/games/requirements?' in req.url else None)
 page.wait_for_timeout(2200);count=len(gets);page.wait_for_timeout(700)
 report['offline_poll_count']=count
 report['worker_offline_bounded_polling']=len(gets)==count and 0<count<=12
 report['offline_state']=state(page,'Clair Obscur: Expedition 33')['status'];page.close()
 request.post(apiurl+'/__test__/reset')
 page=open_game('33 expedition')
 game=page.locator('input[placeholder="Найдите игру…"]:visible');game.fill('Portal 2');page.get_by_role('option',name='Portal 2',exact=True).click()
 for _ in range(4):page.request.post(apiurl+'/__test__/work')
 page.wait_for_timeout(1500)
 report['changed_game_kept']=game.input_value()=='Portal 2'
 page.screenshot(path=str(root/'steam-e2e-switched.png'),full_page=True);page.close()
 cached=open_game('33 expedition');report['positive_cache_reopen']=state(cached,'Clair Obscur: Expedition 33')['status']=='available';cached.close()
 b.close()
(root/'steam-browser-errors-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report));assert all(report[k] for k in ('positive_cache_reopen','no_recommended','negative_cache','steam_error_bounded_polling','worker_offline_bounded_polling','changed_game_kept'))

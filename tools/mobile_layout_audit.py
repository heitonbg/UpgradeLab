import json,os
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
routes=['home','calculator&scenario=build','calculator&scenario=upgrade','calculator&scenario=custom','search','benchmarks','marketplace','account','benchmark-submit']
out=Path(__file__).resolve().parents[1]/'.artifacts/mobile-audit';out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=(r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' if os.name=='nt' else None),headless=True)
 page=b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def mock(route):
  path=urlparse(route.request.url).path
  if not path.startswith('/api/'):return route.continue_()
  if path=='/api/auth/me':
   if os.getenv('AUDIT_AUTH'):return route.fulfill(json={'id':1,'name':'Очень длинное имя пользователя','email':'mobile@example.invalid'})
   return route.fulfill(status=401,json={'detail':'Not authenticated'})
  if path in ('/api/builds','/api/my/listings'):return route.fulfill(json=[])
  if path in ('/api/hardware','/api/hardware/selectors'):return route.fulfill(json=[{'id':1,'name':'AMD Ryzen 5 5600','type':'CPU','raw_score':21500,'normalized_score':50,'socket':'AM4'},{'id':2,'name':'GeForce RTX 3060 Ti','type':'GPU','raw_score':20210,'normalized_score':60}])
  if path=='/api/listings':return route.fulfill(json=[{'id':1,'title':'GeForce RTX 5070 Gaming длинное название комплектующего','category':'GPU','price':'49990','condition':'Б/У','description':'Описание проверочного объявления','city_label':'Новокузнецк','deal_type':'sale','created_at':'2026-11-16T10:00:00Z'}])
  if path=='/api/benchmarks':return route.fulfill(json={'items':[{'settings':{'game':'Cyberpunk 2077','cpu':'AMD Ryzen 7 9800X3D','gpu':'GeForce RTX 5070 Gaming OC','resolution':'2560x1440','preset':'High','scene':'Night City','rt':False},'mean_fps':100,'one_percent_low_fps':75,'observations':3,'independent_publishers':1,'confidence':'limited'}],'total':1})
  return route.fulfill(json={'items':[],'total':0})
 page.route('**/*',mock);results=[]
 for width,height in ((320,640),(360,800),(375,812),(390,844),(414,896),(430,932),(768,1024),(1024,768),(1280,900),(1440,900),(1920,1080)):
  page.set_viewport_size({'width':width,'height':height})
  for tab in routes:
   page.goto('http://127.0.0.1:5174/?tab='+tab);page.wait_for_timeout(140)
   row=page.evaluate('''()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,header:document.querySelector('.site-header').getBoundingClientRect().height,small:[...document.querySelectorAll('p,small,label,button,a,td,th')].filter(e=>e.getClientRects().length&&e.textContent.trim()&&parseFloat(getComputedStyle(e).fontSize)<12).map(e=>({tag:e.tagName,cls:e.className,size:getComputedStyle(e).fontSize})).slice(0,8)})''')
   results.append({'tab':tab,**row})
   page.screenshot(path=str(out/(os.getenv('AUDIT_PHASE','responsive')+'-'+str(width)+'-'+tab.replace('&scenario=','-')+'.png')),full_page=True)
 (out/(os.getenv('AUDIT_PHASE','before')+'.json')).write_text(json.dumps({'results':results,'errors':errors},indent=2),encoding='utf-8')
 print(json.dumps({'overflow':[r for r in results if r['scroll']>r['width']],'small_fonts':[r for r in results if r['small']],'errors':errors,'cases':len(results)}))
 assert not errors,errors
 assert all(row['scroll']<=row['width'] and not row['small'] for row in results),'Mobile layout regression'
 b.close()

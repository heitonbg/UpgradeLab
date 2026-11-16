import json,re,os
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
out=Path(__file__).resolve().parents[1]/'.artifacts/mobile-audit';out.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=(r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' if os.name=='nt' else None),headless=True)
 page=b.new_page();errors=[];auth=True;page.on('pageerror',lambda e:errors.append(str(e)))
 hw=[{'id':1,'name':'AMD Ryzen 5 5600','type':'CPU','raw_score':21500,'normalized_score':50,'socket':'AM4'},{'id':2,'name':'GeForce RTX 3060 Ti','type':'GPU','raw_score':20210,'normalized_score':60}]
 listing={'id':1,'title':'GeForce RTX 3060 Ti очень длинное название видеокарты','price':'30000','category':'GPU','condition':'Б/У','description':'Описание тестового объявления','created_at':'2026-11-16T10:00:00Z','publication_status':'active','owner_id':1,'seller_id':1,'listing_type':'sale'}
 def mock(route):
  path=urlparse(route.request.url).path
  if not path.startswith('/api/'):return route.continue_()
  if path=='/api/auth/me':return route.fulfill(status=200 if auth else 401,json={'id':1,'name':'Тестовый пользователь','email':'test@example.invalid'} if auth else {'detail':'Not authenticated'})
  if path in ('/api/hardware','/api/hardware/selectors'):return route.fulfill(json=hw)
  if path in ('/api/listings','/api/my/listings'):return route.fulfill(json=[listing])
  if path=='/api/builds':return route.fulfill(json=[{'id':1,'created_at':'2026-11-16T10:00:00Z','config':{'scenario':'build','game':'CS2','mode':'1080p_low'},'result':{'parts':[{'type':'CPU','name':hw[0]['name']},{'type':'GPU','name':hw[1]['name']}],'total_price':80000,'fps':150,'status':'draft'}}])
  return route.fulfill(json={'items':[],'total':0,'status':'local_ready'})
 page.route('**/*',mock)
 def check(name):
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),name
  page.screenshot(path=str(out/name),full_page=True)
 def next_step():page.get_by_role('button',name='Продолжить',exact=True).filter(visible=True).click()
 for width,height in ((320,640),(390,844)):
  page.set_viewport_size({'width':width,'height':height})
  page.goto('http://127.0.0.1:5174/?tab=benchmarks');submit=page.get_by_role('button',name='Отправить свой бенчмарк',exact=True);expect(submit).to_be_visible();assert submit.bounding_box()['y']<400;submit.click();expect(page).to_have_url('http://127.0.0.1:5174/?tab=benchmark-submit')
  page.goto('http://127.0.0.1:5174/?tab=calculator&scenario=build');page.get_by_placeholder('80 000',exact=True).fill('120000')
  for step in range(4):
   check(f'form-{width}-build-step{step+1}.png')
   if step<3:next_step()
  expect(page.get_by_role('button',name='Подобрать сборки',exact=True)).to_be_visible()
  page.goto('http://127.0.0.1:5174/?tab=calculator&scenario=upgrade')
  page.get_by_placeholder('Найти процессор',exact=True).fill('5600');expect(page.get_by_role('option',name=re.compile('AMD Ryzen 5 5600'))).to_be_visible()
  box=page.get_by_role('listbox').bounding_box();assert box['x']>=0 and box['x']+box['width']<=width
  page.get_by_role('option',name=re.compile('AMD Ryzen 5 5600')).click()
  page.get_by_placeholder('Найти видеокарту',exact=True).fill('3060');page.get_by_role('option',name=re.compile('GeForce RTX 3060 Ti')).click()
  for step in range(4):
   check(f'form-{width}-upgrade-step{step+1}.png')
   if step<3:next_step()
  page.goto('http://127.0.0.1:5174/?tab=marketplace');page.get_by_role('button',name='Разместить объявление').click()
  dialog=page.get_by_role('dialog');expect(dialog).to_be_visible();page.wait_for_timeout(300);box=dialog.bounding_box();assert box['x']>=0 and box['y']>=0 and box['width']<=width and box['y']+box['height']<=height+1
  check(f'form-{width}-new-listing.png');page.get_by_role('button',name='Закрыть окно',exact=True).click();expect(dialog).not_to_be_visible();assert page.evaluate('getComputedStyle(document.body).overflow')!='hidden'
  page.goto('http://127.0.0.1:5174/?tab=account');page.locator('.saved-account-build > summary').click();check(f'form-{width}-saved-build-details.png')
  page.get_by_role('button',name='Редактировать',exact=True).click();expect(page.get_by_role('dialog')).to_be_visible();check(f'form-{width}-edit-listing.png');page.get_by_role('button',name='Закрыть окно',exact=True).click()
  auth=False;page.goto('http://127.0.0.1:5174/?tab=account');expect(page.get_by_placeholder('mail@example.com')).to_be_visible();check(f'form-{width}-login.png')
  page.locator('.auth-tabs').get_by_role('button',name='Регистрация',exact=True).click();expect(page.get_by_placeholder('Ваше имя')).to_be_visible();check(f'form-{width}-register.png');auth=True
 assert not errors,errors
 print('PASS: all build/upgrade steps, selectors within viewport, new/edit listing modals, scroll restored, saved build details, login/register; 320/390; fixture API only')
 b.close()

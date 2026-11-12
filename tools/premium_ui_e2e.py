"""Actual Edge/Playwright premium UI acceptance, localhost only.
Uses only the isolated runtime DB started for local development. Creates and
removes its own clearly named marketplace test listing. No store requests.
"""
import base64,json,re,struct,sys,time,unittest,uuid,zlib
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.artifacts/premium-ui';ART.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:5173'

def png():
 def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',32,32,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes([90,105,150])*32)*32))+chunk(b'IEND',b'')

class PremiumUI(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  info=json.loads((ROOT/'.artifacts/local-run-current.json').read_text())
  if not Path(info['database']).is_relative_to(ROOT/'.artifacts'):raise RuntimeError('isolated runtime DB required')
  cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
 @classmethod
 def tearDownClass(cls):cls.browser.close();cls.p.stop()
 def setUp(self):
  self.context=self.browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce');self.page=self.context.new_page();self.errors=[]
  self.page.on('pageerror',lambda e:self.errors.append(str(e)))
  self.page.route('**/*',lambda route:route.continue_() if urlsplit(route.request.url).hostname in ('127.0.0.1','localhost',None) else route.abort())
  self.addCleanup(self.context.close)
 def go(self,query):self.page.goto(BASE+'/?'+query,wait_until='networkidle')
 def shot(self,name):
  overlay=self.page.locator('.modal-backdrop:visible,.ui-options:visible').count()>0
  if not overlay:self.page.evaluate('window.scrollTo(0,0)')
  self.page.wait_for_timeout(250);self.page.screenshot(path=str(ART/(name+'.png')),full_page=not overlay)
 def select(self,label,option):
  self.page.get_by_role('combobox',name=label,exact=True).click();self.page.get_by_role('option',name=option,exact=True).click()
 def city(self,label='Город'):
  field=self.page.get_by_role('combobox',name=label,exact=True);field.fill('Кемерово');option=self.page.get_by_role('option').filter(has_text='Кемерово').first;expect(option).to_be_visible();option.click();expect(field).to_have_value('Кемерово')
 def login(self):
  cls=self.__class__
  if getattr(cls,'test_cookies',None):self.context.add_cookies(cls.test_cookies);return
  import sqlite3
  from contextlib import closing
  info=json.loads((ROOT/'.artifacts/local-run-current.json').read_text())
  with closing(sqlite3.connect(Path(info['database']).as_uri()+'?mode=ro',uri=True)) as db:
   row=db.execute("SELECT email FROM users WHERE name='UX проверка' AND email LIKE 'ux-%@example.test' ORDER BY id DESC LIMIT 1").fetchone()
  password='Local-test-acceptance-2026!'
  if row:response=self.context.request.post(BASE+'/api/auth/login',data={'email':row[0],'password':password},headers={'Origin':BASE});self.assertEqual(response.status,200)
  else:
   token=uuid.uuid4().hex[:10];response=self.context.request.post(BASE+'/api/auth/register',data={'email':f'ux-{token}@example.test','password':password,'name':'UX проверка'},headers={'Origin':BASE});self.assertEqual(response.status,201)
  cls.test_cookies=self.context.cookies()
 def test_01_game_combobox_keyboard_and_no_invented_fps(self):
  self.go('tab=calculator&scenario=build');field=self.page.get_by_role('combobox',name='Игра',exact=True)
  self.assertEqual(self.page.locator('.game-picker select').count(),0)
  field.fill('Cyber');expect(self.page.get_by_role('option',name=re.compile('^Cyberpunk 2077 Поддерживается'))).to_be_visible()
  expect(self.page.locator('[role=option][aria-disabled=true]').first).to_be_visible()
  self.shot('after-game');field.press('ArrowDown');field.press('Enter');expect(field).to_have_value('Cyberpunk 2077')
  self.page.get_by_role('button',name='Очистить: Игра',exact=True).click();self.page.locator('input[name=build_budget]').fill('80000');self.page.get_by_role('button',name='Продолжить',exact=False).first.click()
  expect(self.page.locator('.build-section [data-flow-heading]')).to_contain_text('Шаг 1')
  field.fill('Cyber');self.page.get_by_role('option',name=re.compile('^Cyberpunk 2077 Поддерживается')).click()
  field.click();field.press('Escape');self.assertEqual(self.page.get_by_role('listbox').count(),0);self.assertFalse(self.errors)
 def test_02_sources_constraints_city_and_contract(self):
  self.go('tab=calculator&scenario=build');self.page.locator('input[name=build_budget]').fill('80000')
  group=self.page.get_by_role('group',name='Источники предложений');self.assertEqual(group.get_by_role('button').count(),3)
  group.get_by_role('button',name='Regard',exact=True).click();expect(group.get_by_role('button',name='Regard',exact=True)).to_have_attribute('aria-pressed','true');self.shot('after-sources')
  self.page.get_by_role('button',name='Продолжить',exact=False).first.click();self.shot('after-step2')
  self.page.locator('.build-section details.advanced-settings summary').click()
  field=self.page.get_by_role('combobox',name='Фиксированный CPU',exact=True);field.fill('Ryzen 5 5600');expect(self.page.get_by_role('option').filter(has_text='Ryzen 5 5600').first).to_be_visible();self.page.get_by_role('option').filter(has_text='Ryzen 5 5600').first.click()
  expect(self.page.get_by_role('combobox',name='Платформа',exact=True)).to_be_disabled();expect(self.page.locator('.constraint-summary').filter(has_text='CPU:')).to_be_visible()
  self.page.get_by_role('button',name='Сбросить ограничения',exact=True).click();expect(self.page.get_by_role('combobox',name='Платформа',exact=True)).to_be_enabled()
  self.page.get_by_role('button',name='Продолжить',exact=False).first.click();self.city();self.page.get_by_role('combobox',name='Город',exact=True).click();self.shot('after-city');self.page.keyboard.press('Escape')
  self.page.get_by_role('button',name='Назад',exact=True).first.click();self.page.get_by_role('button',name='Продолжить',exact=False).first.click();expect(self.page.get_by_role('combobox',name='Город',exact=True)).to_have_value('Кемерово')
  self.page.get_by_role('button',name='Продолжить',exact=False).first.click()
  with self.page.expect_request(lambda r:r.url.endswith('/api/search-jobs') and r.method=='POST',timeout=15000) as pending,self.page.expect_response(lambda r:r.url.endswith('/api/search-jobs') and r.request.method=='POST',timeout=15000) as started:
   self.page.get_by_role('button',name='Подобрать сборки',exact=True).click()
  body=pending.value.post_data_json['payload'];self.assertEqual(body['price_sources'],['regard']);self.assertEqual(body['pricing_mode'],'offers');self.assertFalse(body['allow_store_fallback']);self.assertEqual(body['ram_capacity_gb'],16);self.assertEqual(body['geo_mode'],'local');self.assertFalse(self.errors)
  job=started.value.json();deadline=time.monotonic()+120
  while job['status'] in ('queued','running') and time.monotonic()<deadline:
   self.page.wait_for_timeout(750);job=self.context.request.get(BASE+'/api/search-jobs/'+job['id']).json()
  self.assertEqual(job['status'],'completed');self.page.wait_for_timeout(5500);self.shot('after-real-search');self.assertFalse(self.errors)
  (ART/'actual-search.json').write_text(json.dumps({'status':job['result'].get('status'),'parts_count':len(job['result'].get('parts',[])),'sources':body['price_sources']},ensure_ascii=False),encoding='utf-8')
 def test_03_marketplace_create_edit_photo_and_dialog_focus(self):
  self.login();self.go('tab=marketplace');created=None
  try:
   self.page.get_by_role('button',name='Разместить объявление',exact=False).first.click();dialog=self.page.get_by_role('dialog');expect(dialog).to_be_visible()
   self.select('Категория','Видеокарта');field=self.page.get_by_role('combobox',name='Модель из каталога',exact=True);field.fill('RTX 4060');self.page.get_by_role('option').filter(has_text='GeForce RTX 4060').first.click()
   dialog.get_by_role('button',name='Отмена',exact=True).focus();self.page.keyboard.press('Tab');expect(dialog.get_by_role('button',name='Закрыть окно',exact=True)).to_be_focused()
   title='[E2E] GeForce RTX 4060 8GB — UX проверка';dialog.get_by_label('Название',exact=True).fill(title)
   dialog.get_by_text('03 · Город и передача товара',exact=True).click();self.city();self.select('Способ получения','Только личная встреча')
   self.select('Тип контакта','Почта');dialog.get_by_label('Контакт',exact=True).fill('ui-test@example.test');dialog.get_by_label('Цена',exact=True).fill('25000')
   dialog.get_by_text('05 · Фотографии',exact=True).click();dialog.locator('input[type=file]').set_input_files({'name':'e2e-test.png','mimeType':'image/png','buffer':png()})
   dialog.get_by_role('button',name='Увеличить фото',exact=True).click();photo=self.page.get_by_role('dialog',name='Фото объявления',exact=True);expect(photo).to_be_visible();self.page.keyboard.press('Escape');expect(photo).not_to_be_visible();dialog=self.page.get_by_role('dialog',name='Новое объявление',exact=True)
   self.page.locator('.modal-backdrop').evaluate('(e)=>e.scrollTo(0,0)');self.shot('after-marketplace-form')
   # Escape closes the dropdown first, not its owning editor.
   dialog.get_by_role('combobox',name='Тип контакта',exact=True).click();self.page.keyboard.press('Escape');expect(dialog).to_be_visible();self.assertEqual(self.page.get_by_role('listbox').count(),0)
   dialog.get_by_role('button',name='Опубликовать',exact=True).scroll_into_view_if_needed()
   self.assertEqual(dialog.evaluate('(e)=>getComputedStyle(e).overflowY'),'visible')
   with self.page.expect_response(lambda r:r.url.endswith('/api/listings') and r.request.method=='POST') as result:dialog.get_by_role('button',name='Опубликовать',exact=True).click()
   self.assertEqual(result.value.status,201);created=result.value.json()['id'];expect(dialog).not_to_be_visible()
   self.page.get_by_role('button',name='Открыть объявление: '+title,exact=True).click();self.shot('after-listing-detail')
   self.page.get_by_role('button',name='Редактировать своё объявление',exact=True).click();editor=self.page.get_by_role('dialog');expect(editor).to_contain_text('Редактировать объявление')
   title+=' · изменено';editor.get_by_label('Название',exact=True).fill(title)
   with self.page.expect_response(lambda r:r.url.endswith('/api/listings/'+str(created)) and r.request.method in ('PUT','PATCH')) as edited:editor.get_by_role('button',name='Сохранить изменения',exact=True).click()
   self.assertEqual(edited.value.status,200);expect(editor).not_to_be_visible();self.assertFalse(self.errors)
  finally:
   if created:self.context.request.delete(BASE+'/api/listings/'+str(created),headers={'Origin':BASE})
 def test_04_responsive_widths_and_source_visibility(self):
  for width in (320,375,390,768,1024,1440,1920):
   self.page.set_viewport_size({'width':width,'height':900})
   for query in ('tab=calculator&scenario=build','tab=marketplace','tab=search'):
    self.go(query);self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width+1,(width,query))
    text=self.page.locator('body').inner_text();self.assertFalse(any(name in text for name in ('Wildberries','Citilink','Ozon','DNS','Avito')),(width,query))
   self.go('tab=calculator&scenario=build');self.shot('after-builder-'+str(width))
  self.assertFalse(self.errors)

 def test_05_result_dialog_no_fabricated_fps(self):
  # Synthetic browser response only. Never stored or shown in the live app to other sessions.
  kinds=['CPU','GPU','motherboard','memory','storage','psu','case','cooler']
  choices=[]
  for index,key in enumerate(['recommended','performance','value']):
   parts=[{'type':kind,'id':i+1+(index*10 if kind=='GPU' else 0),'name':'[E2E] '+(['Radeon RX 6600','GeForce RTX 4060','Radeon RX 6500 XT'][index] if kind=='GPU' else 'Ryzen 5 5600' if kind=='CPU' else kind),'price':[14000,22000,11000][index] if kind=='GPU' else 1000+i*500,'price_basis':'reference','price_observed_at':'2026-11-10T14:30:00Z','price_source':'Тестовая справочная цена'} for i,kind in enumerate(kinds)]
   total=sum(part['price'] for part in parts)
   choices.append({'scenario':'build','variant_key':key,'parts':parts,'total_price':total,'remaining_budget':80000-total,'fps':None,'fps_outlook':None,'status':'draft','purchase_ready':False,'prices_confirmed':False,'compatibility_notes':['Синтетические данные browser E2E, не предложение магазина.'],'price_note':'Синтетическая browser E2E fixture. Данные не сохраняются.','summary':'Проверка интерфейса на тестовых данных','actual_config':{'socket':'AM4','ram_type':'DDR4','ram_capacity_gb':16}})
  fixture={**choices[0],'alternatives':choices}
  self.page.route('**/api/search-jobs',lambda route:route.fulfill(status=200,json={'id':'browser-fixture','status':'completed','result':fixture}) if route.request.method=='POST' else route.continue_())
  self.go('tab=calculator&scenario=build');self.page.locator('input[name=build_budget]').fill('80000')
  for _ in range(3):self.page.get_by_role('button',name='Продолжить',exact=False).first.click()
  self.page.get_by_role('button',name='Подобрать сборки',exact=True).click();dialog=self.page.get_by_role('dialog');expect(dialog).to_be_visible();expect(dialog).to_contain_text('Справочная конфигурация');expect(dialog).not_to_contain_text('Цены сверены')
  self.assertEqual(dialog.evaluate('(e)=>getComputedStyle(e).maxHeight'),'none');self.assertEqual(dialog.evaluate('(e)=>getComputedStyle(e).overflowY'),'visible');self.assertEqual(dialog.locator('.build-choice-card').count(),3);self.assertTrue(all('Нет данных' in text for text in dialog.locator('.choice-fps').all_inner_texts()))
  for width in (320,375,390,768,1024,1440,1920):
   self.page.set_viewport_size({'width':width,'height':1000});self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width+1);dialog.get_by_role('button',name='Выбрать эту сборку',exact=True).first.scroll_into_view_if_needed();self.page.locator('.modal-backdrop').evaluate('(e)=>e.scrollTo(0,0)');self.shot('after-results-'+str(width)+'-fixture')
  self.page.set_viewport_size({'width':1440,'height':1000});self.shot('after-results-fixture');dialog.get_by_role('button',name='Выбрать эту сборку',exact=True).first.click();expect(dialog).not_to_be_visible();self.shot('after-build-detail-fixture');self.assertFalse(self.errors)
 def test_06_mobile_editor_and_portal_bounds(self):
  self.login()
  for width in (320,375,390,768,1024,1440,1920):
   self.page.set_viewport_size({'width':width,'height':800});self.go('tab=marketplace');self.page.get_by_role('button',name='Разместить объявление',exact=False).first.click();dialog=self.page.get_by_role('dialog');expect(dialog).to_be_visible()
   dialog.get_by_role('combobox',name='Категория',exact=True).click();box=self.page.locator('.ui-options').bounding_box();self.assertGreaterEqual(box['x'],-1);self.assertLessEqual(box['x']+box['width'],width+1)
   self.page.keyboard.press('Escape');expect(dialog).to_be_visible();dialog.get_by_role('button',name='Отмена',exact=True).scroll_into_view_if_needed();self.assertEqual(dialog.evaluate('(e)=>getComputedStyle(e).overflowY'),'visible')
   self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width+1);self.shot('after-mobile-editor-'+str(width));self.page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
  self.assertFalse(self.errors)
 def test_07_city_failure_does_not_erase_selection(self):
  self.go('tab=search');self.city();field=self.page.get_by_role('combobox',name='Город',exact=True)
  field.fill('Кемер');field.press('Escape');expect(field).to_have_value('Кемерово')
  self.page.route('**/api/cities?*',lambda route:route.fulfill(status=503,json={'detail':'offline test fixture'}))
  field.fill('Город ошибки '+uuid.uuid4().hex[:8]);expect(self.page.get_by_text('Не удалось загрузить города. Выбранный город сохранён.',exact=False).first).to_be_visible();field.press('Escape');expect(field).to_have_value('Кемерово');self.assertFalse(self.errors)

 def test_08_unsaved_dialog_can_cancel_and_discard(self):
  self.login();self.go('tab=marketplace');self.page.get_by_role('button',name='Разместить объявление',exact=False).first.click()
  editor=self.page.get_by_role('dialog');editor.get_by_label('Название',exact=True).fill('Не сохранённый тестовый черновик')
  editor.get_by_role('button',name='Закрыть окно',exact=True).click()
  confirm=self.page.get_by_role('dialog',name='Закрыть без сохранения?',exact=True);expect(confirm).to_be_visible();self.shot('after-unsaved-dialog')
  confirm.get_by_role('button',name='Продолжить редактирование',exact=True).click()
  editor=self.page.get_by_role('dialog');expect(editor.get_by_label('Название',exact=True)).to_have_value('Не сохранённый тестовый черновик')
  editor.get_by_role('button',name='Закрыть окно',exact=True).click();confirm=self.page.get_by_role('dialog',name='Закрыть без сохранения?',exact=True);confirm.get_by_role('button',name='Не сохранять',exact=True).click();expect(self.page.get_by_role('dialog')).not_to_be_visible()
  self.assertNotEqual(self.page.evaluate('document.body.style.overflow'),'hidden');self.assertFalse(self.errors)

 def test_09_delivery_cities_survive_mode_change(self):
  self.login();self.go('tab=marketplace');self.page.get_by_role('button',name='Разместить объявление',exact=False).first.click();editor=self.page.get_by_role('dialog')
  editor.get_by_text('03 · Город и передача товара',exact=True).click();self.select('Способ получения','Отправка в выбранные города');self.city('Город доставки');editor.get_by_role('button',name='Добавить город',exact=True).click();expect(editor.locator('.delivery-fields li')).to_contain_text('Кемерово')
  self.select('Способ получения','Самовывоз в моём городе');self.select('Способ получения','Отправка в выбранные города');expect(editor.locator('.delivery-fields li')).to_contain_text('Кемерово')
  editor.get_by_role('button',name='Закрыть окно',exact=True).click();self.page.get_by_role('dialog',name='Закрыть без сохранения?',exact=True).get_by_role('button',name='Не сохранять',exact=True).click();self.assertFalse(self.errors)

 def test_10_cpu_work_presents_proxy_not_unselected_game(self):
  parts=[{'type':kind,'name':'[E2E] '+kind,'price':1000,'price_basis':'reference'} for kind in ['CPU','GPU','motherboard','memory','storage','psu','case','cooler']]
  result={'scenario':'build','workload':'cpu_work','objective':'performance','selection_score':21000,'fps':999,'parts':parts,'total_price':8000,'remaining_budget':72000,'status':'draft','purchase_ready':False,'prices_confirmed':False,'compatibility_notes':['Синтетическая E2E fixture, не офер.'],'price_note':'Синтетическая E2E fixture, не офер.'}
  self.page.route('**/api/search-jobs',lambda route:route.fulfill(status=200,json={'id':'cpu-work-fixture','status':'completed','result':result}) if route.request.method=='POST' else route.continue_())
  self.go('tab=calculator&scenario=build');self.select('Назначение','Работа с нагрузкой на CPU');expect(self.page.get_by_role('combobox',name='Игра',exact=True)).not_to_be_visible();self.page.locator('input[name=build_budget]').fill('80000')
  for _ in range(3):self.page.get_by_role('button',name='Продолжить',exact=False).first.click()
  self.page.get_by_role('button',name='Подобрать сборки',exact=True).click();dialog=self.page.get_by_role('dialog');expect(dialog).to_contain_text('CPU Mark');expect(dialog).not_to_contain_text('999');dialog.get_by_role('button',name='Выбрать эту сборку',exact=True).click();expect(self.page.locator('.build-summary')).to_contain_text('CPU Mark');expect(self.page.locator('.build-summary')).not_to_contain_text('999');self.shot('after-cpu-work-fixture');self.assertFalse(self.errors)

if __name__=='__main__':unittest.main(verbosity=2)

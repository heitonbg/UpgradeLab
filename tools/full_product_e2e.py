"""Real staging browser acceptance. No intercepted API responses or admin token."""
import json,time,uuid,unittest,sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import premium_ui_e2e as old
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'.artifacts/product-readiness-20261111/e2e';ART.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:5177'
old.BASE=BASE;old.ART=ART
class RealProduct(old.PremiumUI):
 @classmethod
 def setUpClass(cls):
  cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True)
 def go(self,query):
  with self.page.expect_response(lambda r:r.url.endswith('/api/hardware'),timeout=60000) as hardware:
   self.page.goto(BASE+'/?'+query,wait_until='domcontentloaded')
  self.assertEqual(hardware.value.status,200);hardware.value.body();self.page.locator('main').wait_for()
 def login(self):
  cls=self.__class__
  if getattr(cls,'test_cookies',None):self.context.add_cookies(cls.test_cookies);return
  database=ROOT/'.artifacts/product-readiness-20261111/pc_upgrade_e2e.db'
  with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
   row=db.execute("select email from users where name=? and email like 'e2e-%@example.test' order by id desc limit 1",('E2E изолированный тест',)).fetchone()
  payload={'email':row[0] if row else 'e2e-'+uuid.uuid4().hex[:10]+'@example.test','password':'Local-e2e-test-2026!'}
  if row:response=self.context.request.post(BASE+'/api/auth/login',data=payload,headers={'Origin':BASE});self.assertEqual(response.status,200,response.text())
  else:
   response=self.context.request.post(BASE+'/api/auth/register',data={**payload,'name':'E2E изолированный тест'},headers={'Origin':BASE});self.assertEqual(response.status,201,response.text())
  cls.test_cookies=self.context.cookies()
 def test_01_game_combobox_keyboard_and_no_invented_fps(self):
  self.go('tab=calculator&scenario=build');field=self.page.get_by_role('combobox',name='Игра',exact=True)
  field.fill('Cyber');option=self.page.get_by_role('option').filter(has_text='Cyberpunk 2077').first;expect(option).to_be_visible();option.click();expect(field).to_have_value('Cyberpunk 2077')
  field.fill('Unknown E2E game');expect(self.page.get_by_role('option')).to_have_count(0);self.shot('game-no-data-real')
 def test_11_public_catalog_and_history(self):
  self.go('tab=search');panel=self.page.locator('.regard-public-catalog');expect(panel).to_be_visible()
  expect(panel.locator('article')).to_have_count(24);self.shot('catalog-real')
  card=panel.locator('article').first;card.locator('summary').click();card.get_by_role('button',name='7 дней',exact=True).click();expect(card.locator('svg[aria-label="Дневные наблюдения цены без интерполяции"]')).to_be_visible();self.shot('history-real')
  panel.get_by_label('Поиск по модели',exact=True).fill('Ryzen 5 5600');expect(panel.locator('article').first).to_contain_text('5600')
  self.page.set_viewport_size({'width':390,'height':844});self.shot('catalog-mobile-real');self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),391)
 def test_12_actual_build_and_saved(self):
  self.login();self.go('tab=calculator&scenario=build');self.page.locator('input[name=build_budget]').fill('80000')
  for _ in range(3):self.page.get_by_role('button',name='Продолжить',exact=False).first.click()
  self.page.get_by_role('button',name='Подобрать сборки',exact=True).click()
  dialog=self.page.get_by_role('dialog');expect(dialog.get_by_role('button',name='Выбрать эту сборку',exact=True).first).to_be_visible(timeout=120000);self.shot('build-real')
  dialog.get_by_role('button',name='Выбрать эту сборку',exact=True).first.click();self.shot('build-detail-real');self.assertFalse(self.errors)
  with self.page.expect_response(lambda r:r.url.endswith('/api/builds') and r.request.method=='POST',timeout=120000) as saved:
   self.page.get_by_role('button',name='Сохранить сборку',exact=True).click()
  self.assertEqual(saved.value.status,201,saved.value.text());ident=saved.value.json()['id']
  self.go('tab=account');expect(self.page.get_by_role('heading',name='Сохранённые сборки и расчёты',exact=True)).to_be_visible();self.page.reload(wait_until='domcontentloaded');self.shot('saved-reopened-real')
  builds=self.context.request.get(BASE+'/api/builds').json();item=next(b for b in builds if b['id']==ident);self.assertIsNone(item['price_review']['current_total']);self.assertEqual(len(item['result']['parts']),8)
  self.assertEqual(self.context.request.delete(BASE+'/api/builds/'+str(ident),headers={'Origin':BASE}).status,204)
 def test_13_manual_editor(self):
  self.go('tab=calculator&scenario=build');self.page.locator('input[name=build_budget]').fill('80000');self.page.get_by_role('button',name='Продолжить',exact=False).first.click()
  self.page.locator('.build-section details.advanced-settings summary').click();self.page.get_by_role('checkbox',name='Автоматически подобрать все комплектующие',exact=False).uncheck();expect(self.page.locator('.manual-parts')).to_be_visible();self.shot('manual-real')
  matrix=json.loads((ROOT/'.artifacts/product-readiness-20261111/matrix-real.json').read_text(encoding='utf-8'))
  result=next(item['result'] for item in matrix if item['budget']==80000 and item['sources']==['regard']);parts={part['type']:part for part in result['parts']}
  for label,kind in [('Фиксированный CPU','CPU'),('Фиксированный GPU','GPU')]:
   field=self.page.get_by_role('combobox',name=label,exact=True);field.fill(parts[kind]['name']);option=self.page.get_by_role('option').filter(has_text=parts[kind]['name']).first;expect(option).to_be_visible();option.click()
  for index,kind in enumerate(['motherboard','memory','storage','psu','case','cooler']):
   inputs=self.page.locator('.manual-part-row').nth(index).locator('input');inputs.nth(0).fill(parts[kind]['name']);inputs.nth(1).fill(str(parts[kind]['price']))
  self.shot('manual-filled-real')
  for _ in range(2):self.page.get_by_role('button',name='Продолжить',exact=False).first.click()
  self.page.get_by_role('button',name='Подобрать сборки',exact=True).click();dialog=self.page.get_by_role('dialog');expect(dialog.get_by_role('button',name='Выбрать эту сборку',exact=True).first).to_be_visible(timeout=120000);self.shot('manual-result-real')

 def test_14_upgrade_real(self):
  self.go('tab=calculator&scenario=upgrade')
  for label,query in [('Процессор','Ryzen 5 5600'),('Видеокарта','GTX 1650')]:
   field=self.page.get_by_role('combobox',name=label,exact=True);field.fill(query);option=self.page.get_by_role('option').filter(has_text=query).first;expect(option).to_be_visible(timeout=30000);option.click()
  self.page.get_by_label('Общий объём, ГБ',exact=True).fill('16')
  for _ in range(3):self.page.get_by_role('button',name='Продолжить',exact=False).first.click()
  self.page.get_by_role('button',name='Рассчитать производительность',exact=True).click();expect(self.page.locator('.upgrade-result')).to_be_visible(timeout=120000);self.shot('upgrade-real');self.assertFalse(self.errors)
# Existing acceptance cases using only actual API and ordinary UI.
for name in list(vars(old.PremiumUI)):
 if name.startswith('test_') and name not in {'test_01_game_combobox_keyboard_and_no_invented_fps','test_03_marketplace_create_edit_photo_and_dialog_focus','test_04_responsive_widths_and_source_visibility','test_06_mobile_editor_and_portal_bounds','test_08_unsaved_dialog_can_cancel_and_discard','test_09_delivery_cities_survive_mode_change'}:
  setattr(RealProduct,name,None)
if __name__=='__main__':unittest.main(verbosity=2)

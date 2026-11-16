import os
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=(r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' if os.name=='nt' else None),headless=True)
 page=b.new_page(viewport={'width':390,'height':844});counts={'gpu':0};errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def mock(route):
  path=urlparse(route.request.url).path
  if not path.startswith('/api/'):return route.continue_()
  if path=='/api/auth/me':return route.fulfill(status=401,json={'detail':'Not authenticated'})
  if path in ('/api/hardware','/api/listings'):return route.fulfill(json=[])
  if path=='/api/benchmarks/gpu-reference':counts['gpu']+=1
  return route.fulfill(json={'items':[],'total':0})
 page.route('**/*',mock);page.goto('http://127.0.0.1:5174/?tab=benchmarks')
 expect(page.get_by_role('button',name='Открыть меню')).to_be_visible()
 expect(page.locator('#site-navigation')).not_to_be_visible()
 assert page.locator('.site-header').bounding_box()['height']<=80
 page.get_by_role('button',name='Открыть меню').click();expect(page.locator('#site-navigation')).to_be_visible()
 page.get_by_role('button',name='Комплектующие',exact=True).click();expect(page.locator('#site-navigation')).not_to_be_visible();expect(page).to_have_url('http://127.0.0.1:5174/?tab=search')
 page.get_by_role('button',name='Открыть меню').click();page.get_by_role('button',name='Бенчмарки',exact=True).click()
 expect(page.locator('#benchmark-filters')).not_to_be_visible()
 page.get_by_role('button',name='Фильтры и сортировка').click();expect(page.locator('#benchmark-filters')).to_be_visible()
 page.get_by_placeholder('Cyberpunk 2077',exact=True).fill('Cyberpunk');page.get_by_role('button',name='Применить фильтры').click();expect(page.locator('#benchmark-filters')).not_to_be_visible()
 assert counts['gpu']==0
 page.get_by_text('Дополнительные GPU-данные FPSHQ',exact=True).click();expect(page.locator('.fpshq-reference')).to_be_visible();expect(page.locator('.fpshq-reference form')).to_be_visible();page.wait_for_timeout(150);assert 1<=counts['gpu']<=2,counts
 page.set_viewport_size({'width':1280,'height':900});expect(page.locator('#site-navigation')).to_be_visible();expect(page.locator('#benchmark-filters')).to_be_visible();expect(page.get_by_role('button',name='Открыть меню')).not_to_be_visible()
 assert not errors,errors
 print('PASS mobile menu/routes, compact header, filters apply/close, lazy GPU table and its filters, desktop preserved; API mocked')
 b.close()

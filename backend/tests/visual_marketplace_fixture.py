"""Local trusted-app visual fixtures. No runtime browser source is enabled."""
import base64,json,struct,zlib,threading
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
DIST=ROOT/'frontend/dist'
OUT=ROOT/'.artifacts/iteration7';OUT.mkdir(parents=True,exist_ok=True)
cities=json.loads((ROOT/'backend/app/data/cities.json').read_text(encoding='utf-8'))
def png(w,h):
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    raw=(b'\x00'+bytes([80,120,160])*w)*h
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
    return 'data:image/png;base64,'+base64.b64encode(data).decode()
rows=[]
for i,(w,h) in enumerate([(80,600),(600,80),(300,300),(2400,1800)]):
    rows.append(dict(id=i+1,title='GeForce RTX 3060 Ti '+str(i),condition='Б/У',price='15000',
       contact='https://t.me/iwrawww',contact_type='telegram',description='Локальная визуальная фикстура',
       listing_type='sale',photo_url=png(w,h),created_at='2026-11-09T12:00:00Z',updated_at=None,
       availability_confirmed_at=None,seller_availability='not_confirmed',publication_status='active',
       city_id='ru:kemerovo',city_label='Кемерово · Кузбасс',category='GPU',hardware_id=2))
rows.append({**rows[0],'id':5,'photo_url':'http://127.0.0.1:1/'+('very-long-'*100)+'.png'})
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(DIST),**kwargs)
    def log_message(self,*args):pass
    def do_GET(self):
        path=self.path.split('?')[0]
        routes={'/api/cities':cities,'/api/listings':rows,'/api/my/listings':rows,'/api/builds':[],
           '/api/auth/me':{'id':1,'email':'fixture@example.test','name':'Визуальная фикстура'},
           '/api/prices/status':{'coverage':{},'updated_at':None},
           '/api/hardware':[{'id':1,'name':'AMD Ryzen 5 5600','type':'CPU','raw_score':10000,'normalized_score':50,'socket':'AM4'},
                            {'id':2,'name':'GeForce RTX 3060 Ti','type':'GPU','raw_score':10000,'normalized_score':50,'vram':8}]}
        if path in routes:
            data=json.dumps(routes[path],ensure_ascii=False).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
        else:super().do_GET()
server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
origin='http://127.0.0.1:'+str(server.server_port)
report=[]
patches=[]
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True,
            args=['--disable-background-networking','--disable-component-update'])
        context=browser.new_context(service_workers='block',reduced_motion='reduce')
        def route_request(route):
            from urllib.parse import urlsplit
            path=urlsplit(route.request.url).path
            if '/api/' in path:
                path=path[path.index('/api/'):]
                fixtures={'/api/cities':cities,'/api/listings':rows,'/api/my/listings':rows,'/api/builds':[],
                    '/api/auth/me':{'id':1,'email':'fixture@example.test','name':'Визуальная фикстура'},
                    '/api/prices/status':{'coverage':{},'updated_at':None},
                    '/api/hardware':[{'id':1,'name':'AMD Ryzen 5 5600','type':'CPU','raw_score':10000,'normalized_score':50,'socket':'AM4'},
                                     {'id':2,'name':'GeForce RTX 3060 Ti','type':'GPU','raw_score':10000,'normalized_score':50,'vram':8}]}
                if path.startswith('/api/listings/') and route.request.method=='PATCH':
                    payload=json.loads(route.request.post_data)
                    row=next(row for row in rows if row['id']==int(path.rsplit('/',1)[1]))
                    row.update(payload);patches.append(payload)
                    city=next((city for city in cities if city['city_id']==row['city_id']),None)
                    if city:row['city_label']=city['name']+' · '+city['region']
                    route.fulfill(status=200,content_type='application/json',body=json.dumps(row))
                else:
                    route.fulfill(status=200,content_type='application/json',body=json.dumps(fixtures.get(path,{})))
            elif route.request.url.startswith(origin+'/'):
                route.continue_()
            else:
                route.abort()
        context.route('**/*',route_request)
        page=context.new_page()
        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        for width in [320,375,430,768,1280,1920]:
            page.set_viewport_size({'width':width,'height':1000})
            page.goto(origin,wait_until='networkidle')
            page.get_by_role('button',name='Биржа',exact=True).first.click()
            page.screenshot(path=str(OUT/'before-cards.png'),full_page=True)
            if errors: print('PAGE_ERRORS',errors)
            page.locator('.listing-tile').first.wait_for()
            for frame in page.locator('.listing-image-frame').all(): frame.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            overflow=page.evaluate('document.documentElement.scrollWidth>window.innerWidth')
            boxes=page.locator('.listing-image-frame').evaluate_all('(els)=>els.map(e=>({width:e.clientWidth,height:e.clientHeight,overflow:e.scrollWidth>e.clientWidth+1}))')
            assert not overflow,(width,'page overflow')
            assert all(not box['overflow'] and abs(box['width']/box['height']-4/3)<.04 for box in boxes),(width,boxes)
            page.screenshot(path=str(OUT/f'market-{width}.png'),full_page=True)
            page.locator('.listing-open').nth(1).click()
            page.get_by_role('button',name='Увеличить фото').click()
            page.screenshot(path=str(OUT/f'zoom-{width}.png'),full_page=False)
            page.get_by_role('button',name='Закрыть окно').last.click()
            page.get_by_role('button',name='Редактировать своё объявление').click()
            page.locator('.listing-form').wait_for()
            assert page.locator('.listing-form input[type="checkbox"]').count()==1
            assert page.get_by_text('Предпросмотр:',exact=False).count()>0
            assert not page.evaluate('document.documentElement.scrollWidth>window.innerWidth'),(width,'form overflow')
            page.screenshot(path=str(OUT/f'edit-{width}.png'),full_page=False)
            form=page.locator('.listing-form')
            form.get_by_label('Цена',exact=True).fill(str(16000+width))
            dismiss=lambda dialog:dialog.dismiss()
            page.on('dialog',dismiss)
            form.get_by_role('button',name='Отмена',exact=True).click()
            page.remove_listener('dialog',dismiss)
            assert form.is_visible(),'Unsaved changes were lost'
            form.get_by_label('Тип контакта',exact=True).select_option('phone')
            form.get_by_label('Контакт',exact=True).fill('8 (996) 123-45-67')
            assert form.get_by_role('link',name='Позвонить',exact=True).get_attribute('href')=='tel:+79961234567'
            form.locator('.city-picker input').fill('Кемь · Республика Карелия')
            form.get_by_role('button',name='Сохранить изменения',exact=True).click()
            form.wait_for(state='detached')
            assert patches[-1]['contact']=='+79961234567'
            assert patches[-1]['city_id']=='ru:kem'
            assert patches[-1]['price']==str(16000+width)
            report.append({'width':width,'card_count':len(boxes),'overflow':False,'edit_and_zoom':True})
        assert not errors,errors
        context.close();browser.close()
finally:
    server.shutdown();server.server_close()
(OUT/'visual-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))

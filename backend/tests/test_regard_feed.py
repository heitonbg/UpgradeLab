"""Real-format Regard fixtures; no shop requests."""
import sys,unittest,tempfile,json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.regard_feed import RegardFeedAdapter,compare_feeds
from app.services.catalog_files import CatalogError

def xlsx(rows):
 from io import BytesIO
 from xml.sax.saxutils import escape
 out=BytesIO()
 with ZipFile(out,'w',ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
  z.writestr('xl/workbook.xml','<workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Price" r:id="r1"/></sheets></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
  xml='<worksheet><sheetData>'
  for number,values in rows:
   xml+=f'<row r="{number}">'+''.join(f'<c r="{col}{number}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>' for col,v in values.items())+'</row>'
  z.writestr('xl/worksheets/sheet1.xml',xml+'</sheetData></worksheet>')
 return out.getvalue()
BASE=[(18,{'A':'Прайс-лист актуален на 09.11.2026, 17:30'}),(21,{'A':'ID','D':'Производитель','E':'PN','F':'Наименование','G':'Цена, руб.','H':'Гарантия, мес.'}),(23,{'A':'Комплектующие для ПК'}),(24,{'A':'Процессоры'}),(25,{'A':'123','D':'AMD','E':'PN-123','F':'Процессор AMD Ryzen 5 5600 OEM','G':'5000'})]
class RegardReaderTests(unittest.TestCase):
 def test_real_structure_and_provenance(self):
  r=RegardFeedAdapter().read(xlsx(BASE));self.assertEqual(len(r.rows),1);row=r.rows[0][1]
  self.assertEqual(row['external_product_id'],'123');self.assertEqual(row['category'],'CPU');self.assertEqual(row['price'],'5000');self.assertEqual(row['source_updated_at'],'2026-11-09T14:30:00+00:00')
  self.assertEqual(row['product_url'],'');self.assertEqual(row['availability'],'');self.assertIn('sha256',r.metadata)
 def test_nested_cooling_only_cpu_coolers(self):
  rows=BASE+[(26,{'A':'Системы охлаждения'}),(27,{'B':'Компоненты СЖО'}),(28,{'C':'Водоблоки'}),(29,{'A':'124','F':'Водоблок CPU','G':'2000'}),(30,{'B':'Кулеры для процессоров'}),(31,{'A':'125','F':'Кулер DeepCool AG400','G':'2000'}),(32,{'A':'Мониторы'}),(33,{'A':'126','F':'Монитор','G':'10000'})]
  r=RegardFeedAdapter().read(xlsx(rows));self.assertEqual([v['category'] for _,v in r.rows],['CPU','cooler']);self.assertEqual(r.metadata['product_rows'],4)
 def test_structure_drift_rejected(self):
  with self.assertRaises(CatalogError):RegardFeedAdapter().read(xlsx([r for r in BASE if r[0]!=21]))
 def test_missing_or_invalid_date_rejected(self):
  with self.assertRaises(CatalogError):RegardFeedAdapter().read(xlsx([r for r in BASE if r[0]!=18]))
 def test_duplicate_id_rejected(self):
  with self.assertRaises(CatalogError):RegardFeedAdapter().read(xlsx(BASE+[(26,{'A':'123','F':'Other','G':'6000'})]))
 def test_change_detection(self):
  old=[{'external_product_id':'1','price':'100','title':'CPU'},{'external_product_id':'2','price':'200','title':'GPU'}]
  new=[{'external_product_id':'1','price':'110','title':'CPU'},{'external_product_id':'3','price':'300','title':'RAM'}]
  r=compare_feeds(old,new);self.assertEqual(r['price_changed'],['1']);self.assertEqual(r['new'],['3']);self.assertEqual(r['missing'],['2'])
 def test_unchanged_ignores_received_time(self):
  a={'external_product_id':'1','price':'100','title':'CPU','source_updated_at':'old'}
  self.assertEqual(compare_feeds([a],[{**a,'source_updated_at':'new'}])['unchanged'],['1'])
 def test_suspicious_shrink_detected(self):
  old=[{'external_product_id':str(i),'price':'100','title':'CPU'} for i in range(10)]
  self.assertTrue(compare_feeds(old,old[:3])['suspicious_shrink'])

class ClosedRegardImportTests(unittest.TestCase):
 def setUp(self):
  import tempfile
  from datetime import datetime,timezone
  from unittest.mock import patch
  from sqlalchemy import create_engine
  from sqlalchemy.orm import Session
  from app.db.models import Base,Hardware
  from scripts.regard_feed import schema
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.engine=create_engine('sqlite:///'+(self.root/'private.analysis.db').as_posix());Base.metadata.create_all(self.engine);self.addCleanup(self.engine.dispose)
  with Session(self.engine) as db:db.add(Hardware(id=1,type='CPU',name='AMD Ryzen 5 5600',socket='AM4',raw_score=21000,normalized_score=50));db.commit()
  self.file=self.root/'price.xlsx';self.file.write_bytes(xlsx(BASE));self.mapping=self.root/'schema.json';self.mapping.write_text(json.dumps(schema()),encoding='utf-8')
  self.rights={'source':'regard','development':True,'public_display':False,'commercial':False,'automatic_download':False,'basis':'Owner-authorized synthetic local test','owner_confirmed_by':'test owner','confirmed_at':'2026-11-09T15:00:00Z'}
  self.addCleanup(patch.stopall);patch('app.core.price_time.utc_now',return_value=datetime(2026,11,9,16,tzinfo=timezone.utc)).start();patch('socket.socket',side_effect=AssertionError('No network')).start()
 def plan(self):
  from app.services.catalog_import import prepare_import
  return prepare_import(self.engine,self.file,self.mapping)
 def apply(self,plan=None,**extra):
  from app.services.catalog_import import apply_import
  return apply_import(self.engine,self.file,self.mapping,plan or self.plan(),self.rights,analysis=True,**extra)
 def test_private_search_needs_database_bound_context(self):
  from sqlalchemy.orm import Session
  from app.services.catalog_access import closed_catalog_analysis
  from app.services.offers import available_offers
  report=self.apply();self.assertEqual(report['materialized_offers'],1);self.assertEqual(report['published'],0)
  with Session(self.engine) as db:
   self.assertEqual(available_offers(db,['regard']),[])
   with closed_catalog_analysis(self.engine):
    row=available_offers(db,['regard'])[0];attrs=json.loads(row.attributes)
    self.assertEqual(row.origin,'catalog_import');self.assertEqual(row.url,'https://www.regard.ru/product/123')
    self.assertNotIn('price_verification',attrs);self.assertEqual(attrs['catalog_import']['external_product_id'],'123');self.assertEqual(attrs['catalog_import']['availability'],'unknown')
   self.assertEqual(available_offers(db,['regard']),[])
 def test_analysis_rejects_working_database_name(self):
  from sqlalchemy import create_engine
  from app.services.catalog_access import closed_catalog_analysis
  engine=create_engine('sqlite:///'+(self.root/'working.db').as_posix())
  try:
   with self.assertRaises(ValueError),closed_catalog_analysis(engine):pass
  finally:engine.dispose()
 def test_context_cannot_grant_another_database(self):
  from sqlalchemy import create_engine
  from sqlalchemy.orm import Session
  from app.services.catalog_access import closed_catalog_analysis,analysis_enabled
  other=create_engine('sqlite:///'+(self.root/'another.analysis.db').as_posix())
  try:
   with closed_catalog_analysis(self.engine),Session(other) as db:self.assertFalse(analysis_enabled(db))
  finally:other.dispose()
 def test_repeat_import_idempotent(self):
  from sqlalchemy.orm import Session
  from sqlalchemy import select,func
  from app.db.models import StoreOffer,CatalogObservation
  plan=self.plan();self.apply(plan);r=self.apply(plan);self.assertTrue(r['idempotent'])
  with Session(self.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(StoreOffer)),1);self.assertEqual(db.scalar(select(func.count()).select_from(CatalogObservation)),1)
 def test_original_file_change_requires_new_preview(self):
  from app.services.catalog_import import apply_import
  p=self.plan();self.file.write_bytes(xlsx(BASE+[(26,{'A':'124','F':'Процессор AMD Ryzen 5 5600 OEM','G':'6000'})]))
  with self.assertRaises(CatalogError):apply_import(self.engine,self.file,self.mapping,p,self.rights,analysis=True)
 def test_price_change_keeps_offer_id_and_history(self):
  from sqlalchemy.orm import Session
  from sqlalchemy import select,func
  from app.db.models import StoreOffer,CatalogObservation
  self.apply();rows=[(n,{**v,'G':'5500'} if n==25 else v) for n,v in BASE];self.file.write_bytes(xlsx(rows));self.apply()
  with Session(self.engine) as db:
   row=db.scalar(select(StoreOffer));self.assertEqual(row.id,1);self.assertEqual(row.price_rub,5500);self.assertNotIn('price_verification',json.loads(row.attributes));self.assertEqual(db.scalar(select(func.count()).select_from(CatalogObservation)),2)
 def test_unknown_stock_and_delivery_never_become_public(self):
  from sqlalchemy.orm import Session
  from app.services.offers import search_offers
  from app.schemas.offers import SearchOffers
  from app.services.catalog_access import closed_catalog_analysis
  self.apply()
  with Session(self.engine) as db,closed_catalog_analysis(self.engine):
   p=SearchOffers(query='Ryzen 5 5600',category='CPU',sources=['regard']);p._catalog_only=True
   found=search_offers(db,p)['offers'];self.assertEqual(len(found),1);self.assertIsNone(found[0]['price_verified_at']);self.assertEqual(found[0]['geography']['location_status'],'location_unknown')
  with Session(self.engine) as db:
   public=search_offers(db,p);self.assertTrue(public['search_cached']);self.assertEqual(public['offers'],[])
 def test_public_audience_cannot_use_analysis_mode(self):
  from app.services.catalog_import import apply_import
  with self.assertRaises(CatalogError):apply_import(self.engine,self.file,self.mapping,self.plan(),self.rights,analysis=True,audience='public-noncommercial')

 def test_missing_product_hidden_without_deletion_after_reviewed_shrink(self):
  from sqlalchemy import select,func
  from sqlalchemy.orm import Session
  from app.db.models import CatalogProduct,StoreOffer
  from app.services.catalog_access import closed_catalog_analysis
  from app.services.offers import available_offers
  many=BASE+[(26,{'A':'124','F':'Процессор AMD Ryzen 5 5600 OEM','G':'5100'}),(27,{'A':'125','F':'Процессор AMD Ryzen 5 5600 OEM','G':'5200'})]
  self.file.write_bytes(xlsx(many));self.apply();self.file.write_bytes(xlsx(many[:-1]));plan=self.plan()
  with self.assertRaises(CatalogError):self.apply(plan)
  self.apply(plan,allow_shrink=True)
  with Session(self.engine) as db,closed_catalog_analysis(self.engine):
   self.assertEqual(db.scalar(select(func.count()).select_from(CatalogProduct)),3)
   self.assertEqual(db.scalar(select(func.count()).select_from(StoreOffer)),3)
   self.assertEqual(len(available_offers(db,['regard'])),2)
 def test_new_feed_time_does_not_create_card_confirmation(self):
  from sqlalchemy.orm import Session
  from sqlalchemy import select
  from app.db.models import StoreOffer
  self.apply();rows=[(n,{'A':'Прайс-лист актуален на 09.11.2026, 17:31'} if n==18 else v) for n,v in BASE]
  self.file.write_bytes(xlsx(rows));self.apply()
  with Session(self.engine) as db:self.assertNotIn('price_verification',json.loads(db.scalar(select(StoreOffer)).attributes))
 def test_invalid_daily_file_leaves_previous_offer(self):
  from sqlalchemy.orm import Session
  from sqlalchemy import select
  from app.db.models import StoreOffer
  self.apply();self.file.write_bytes(b'not an xlsx')
  with self.assertRaises(CatalogError):self.apply()
  with Session(self.engine) as db:self.assertEqual(db.scalar(select(StoreOffer)).price_rub,5000)

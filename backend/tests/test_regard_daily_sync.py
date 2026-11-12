"""Transactional daily sync on tiny native XLSX fixtures, never network."""
import unittest,json
from unittest.mock import patch
from sqlalchemy import select,func
from sqlalchemy.orm import Session
import test_regard_feed as fixtures
from test_regard_feed import xlsx,BASE
from app.db.models import CatalogDailyPrice,CatalogSyncRun,CatalogProduct
from app.services.regard_sync import synchronize,sync_lock,download
from app.services.catalog_files import CatalogError

class DailySyncTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.ClosedRegardImportTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
 def sync(self):
  f=self.fixture
  return synchronize(f.engine,f.mapping,f.rights,file=f.file,analysis=True,min_products=1)
 def test_success_and_identical_receipt(self):
  first=self.sync()
  with patch('app.services.regard_feed.RegardFeedAdapter.read',side_effect=AssertionError('identical bytes must not be parsed')):second=self.sync()
  self.assertTrue(second['receipt']['idempotent'])
  with Session(self.fixture.engine) as db:
   self.assertEqual(db.scalar(select(func.count()).select_from(CatalogDailyPrice)),1)
   self.assertEqual(db.get(CatalogDailyPrice,('regard:123','2026-11-09')),None)
   self.assertEqual([r.status for r in db.scalars(select(CatalogSyncRun).order_by(CatalogSyncRun.started_at))],['succeeded','unchanged'])
 def test_failure_rolls_back_catalog_and_history(self):
  self.sync()
  f=self.fixture;f.file.write_bytes(xlsx(BASE[:-1]+[(25,{'A':'123','F':'AMD Ryzen 5 5600 OEM','G':'5100'})]))
  with patch('app.services.catalog_history.record_prices',side_effect=RuntimeError('simulate storage failure')):
   with self.assertRaises(RuntimeError):self.sync()
  with Session(f.engine) as db:
   row=db.scalar(select(CatalogDailyPrice));self.assertEqual(row.price_kopecks,500000)
   item=db.scalar(select(CatalogProduct));self.assertEqual(float(json.loads(item.payload)['price']),5000)
   self.assertIn('failed',[r.status for r in db.scalars(select(CatalogSyncRun))])
 def test_authorized_automatic_download_uses_same_import_and_cleans_spool(self):
  import tempfile
  from pathlib import Path
  from test_regard_download import FakeTransport
  from app.db.models import CatalogAccess
  f=self.fixture;rights={**f.rights,'automatic_download':True}
  with Session(f.engine) as db:
   db.add(CatalogAccess(source='regard',rights=json.dumps(rights),public_enabled=0,fixture=0));db.commit()
  original=tempfile.TemporaryDirectory;directories=[]
  def workspace(*args,**kwargs):
   obj=original(*args,**kwargs);directories.append(Path(obj.name));return obj
  with patch('app.services.regard_sync.settings.regard_download_enabled',True),patch('app.services.regard_sync.settings.regard_price_url','https://www.regard.ru/api/site/pricelist'),patch('app.services.source_permissions.network_allowed',return_value=True),patch('app.services.regard_sync.tempfile.TemporaryDirectory',side_effect=workspace):
   result=synchronize(f.engine,f.mapping,rights,analysis=True,min_products=1,transport=FakeTransport())
  self.assertEqual(result['receipt']['accepted'],1);self.assertEqual(result['download']['status'],200)
  self.assertTrue(all(not path.exists() for path in directories))
  with Session(f.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(CatalogDailyPrice)),1)

 def test_older_source_date_does_not_replace_last_catalog(self):
  self.sync();f=self.fixture
  old=[(n,dict(values)) for n,values in BASE]
  old[0]=(18,{'A':'Прайс-лист актуален на 08.11.2026, 17:30'})
  f.file.write_bytes(xlsx(old))
  with self.assertRaisesRegex(CatalogError,'older_than_last_success'):self.sync()
  with Session(f.engine) as db:
   self.assertEqual(db.scalar(select(CatalogDailyPrice)).source_day,'2026-11-09')
   self.assertEqual(db.scalar(select(func.count()).select_from(CatalogProduct)),1)

 def test_process_lock_rejects_second_executor(self):
  with sync_lock(self.fixture.engine):
   with self.assertRaisesRegex(CatalogError,'sync_already_running'):self.sync()
 def test_small_or_damaged_input_never_changes_products(self):
  f=self.fixture;self.sync();f.file.write_bytes(b'not a zip')
  with self.assertRaises(Exception):self.sync()
  with Session(f.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(CatalogProduct)),1)
 def test_unauthorized_download_never_calls_transport(self):
  with patch('app.services.regard_sync.settings.regard_download_enabled',False):
   with self.assertRaisesRegex(CatalogError,'automatic_download_not_authorized'):download(self.fixture.engine,self.fixture.root,transport=object())

if __name__=='__main__':unittest.main()

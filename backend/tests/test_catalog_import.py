"""Real import operations on temporary SQLite; all network is forbidden."""
import sys,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from app.db.models import Base,StoreOffer,CatalogProduct,CatalogObservation,CatalogAccess,OfferSearch,SavedBuild
from app.services.catalog_import import prepare_import,apply_import,parse_money,normalize
from app.schemas.catalog import CatalogSchema
from app.services.catalog_files import CatalogError
from app.services.catalog_access import fixture_catalog
from app.schemas.offers import SearchOffers
from app.services.offers import search_offers,available_offers
from app.core.config import settings
from app.services.builds import BuildRequest,assemble
from app.services.price_verification import verify_build_prices
from scripts.catalog_fixture import rows,schema,rights,csv_bytes,xlsx_bytes,seed,NOW

class CatalogImportTests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    self.engine=create_engine('sqlite:///'+(self.root/'test.fixture.db').as_posix(),connect_args={'timeout':10})
    Base.metadata.create_all(self.engine);self.addCleanup(self.engine.dispose)
    with Session(self.engine) as db:seed(db)
    self.addCleanup(patch.stopall)
    patch('app.core.price_time.utc_now',return_value=datetime(2026,11,9,12,5,tzinfo=timezone.utc)).start()
    self.net=patch('socket.socket',side_effect=AssertionError('No network')).start()
    self.schema=self.root/'schema.json';self.file=self.root/'prices.csv';self.write()
 def write(self,values=None,config=None,fmt='csv'):
    config=config or schema(fmt);self.schema.write_text(json.dumps(config),encoding='utf-8')
    self.file=self.root/('prices.'+fmt)
    self.file.write_bytes(xlsx_bytes(values or rows()) if fmt=='xlsx' else csv_bytes(values or rows()))
 def prepare(self):return prepare_import(self.engine,self.file,self.schema)
 def apply(self,plan=None,**kw):return apply_import(self.engine,self.file,self.schema,plan or self.prepare(),rights(),fixture=True,**kw)
 def offers(self,fixture=False):
    with Session(self.engine) as db:
      if fixture:
       with fixture_catalog():return list(available_offers(db))
      return list(available_offers(db))
 def test_csv_preview_is_readonly_and_apply_finds_gpu(self):
    plan=self.prepare();self.assertEqual(plan['report']['accepted'],8);self.assertEqual(plan['report']['publishable'],8)
    self.assertEqual(self.offers(),[])
    self.apply(plan)
    with Session(self.engine) as db,fixture_catalog():
      result=search_offers(db,SearchOffers(query='RTX 5060',category='GPU',sources=['regard']))
      self.assertEqual(len(result['offers']),1)
      self.assertEqual(result['offers'][0]['origin'],'catalog_import')
      self.assertIsNone(result['offers'][0]['price_verified_at'])
      self.assertEqual(result['offers'][0]['price_rub'],20000)
    self.net.assert_not_called()
 def test_catalog_estimates_survive_24_hours_but_not_72(self):
    self.apply()
    with patch('app.core.price_time.utc_now',return_value=datetime(2026,11,11,12,tzinfo=timezone.utc)):
      self.assertEqual(len(self.offers(True)),8)
      from app.services.offers import fresh
      self.assertTrue(all(not fresh(row) for row in self.offers(True)))
    with patch('app.core.price_time.utc_now',return_value=datetime(2026,11,12,12,0,1,tzinfo=timezone.utc)):
      self.assertEqual(self.offers(True),[])
 def test_manual_catalog_48_hours_uses_server_price_and_stays_draft(self):
    self.apply()
    with Session(self.engine) as db,fixture_catalog(),patch('app.core.price_time.utc_now',return_value=datetime(2026,11,11,12,tzinfo=timezone.utc)):
      rows=available_offers(db,['regard'])
      parts={r.category:{'name':r.name,'price':1,'offer_id':r.id} for r in rows if r.category not in ('CPU','GPU')}
      request=BuildRequest(scenario='build',budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['regard'],**parts)
      result=assemble(request,db)
      self.assertEqual(len(result['parts']),8)
      self.assertEqual(result['status'],'draft')
      self.assertFalse(result['purchase_ready'])
      self.assertFalse(result['prices_confirmed'])
      self.assertTrue(all(p['price_freshness']=='stale' for p in result['parts']))
      self.assertTrue(all(p['price']>1 for p in result['parts']))
 def test_catalog_permission_resolution_is_once_per_query(self):
    self.apply()
    from app.services import catalog_access
    with patch.object(catalog_access,'analysis_enabled',wraps=catalog_access.analysis_enabled) as resolved:
      self.assertEqual(len(self.offers(True)),8)
      self.assertEqual(resolved.call_count,1)
 def test_xlsx_works(self):
    self.write(fmt='xlsx');plan=self.prepare()
    self.assertEqual(plan['report']['publishable'],8);self.apply(plan)
    self.assertEqual(len(self.offers(True)),8)
 def test_cyrillic_cp1251_explicit(self):
    values=rows();values[0][1]='Процессор AMD Ryzen 5 5600'
    config=schema();config['encoding']='cp1251'
    self.write(values,config);self.file.write_bytes(csv_bytes(values,'cp1251'))
    self.assertEqual(self.prepare()['report']['accepted'],8)
 def test_money_exact_separators(self):
    for decimal,thousands,value,expected in [(',',' ','12 345,00','12345.00'),(',','.','12.345,67','12345.67'),('.',',','12,345.67','12345.67')]:
      config=schema();config.update(decimal_separator=decimal,thousands_separator=thousands)
      self.assertEqual(str(parse_money(value,CatalogSchema(**config))),expected)
 def test_missing_invalid_negative_unknown_currency(self):
    for column,value in [(3,''),(3,'NaN'),(3,'-1'),(3,'1e9'),(3,'123 / month'),(4,'USD'),(3,'1 23,00')]:
      with self.subTest(value=value):
        values=rows();values[0][column]=value;self.write(values)
        plan=self.prepare();self.assertEqual(plan['report']['rejected'],1)
 def test_unknown_category(self):
    values=rows();values[0][2]='Other';self.write(values)
    self.assertEqual(self.prepare()['report']['errors'][0]['reason'],'unknown_category')
 def test_duplicate_sku_excludes_both(self):
    values=rows();values[1][0]=values[0][0];self.write(values)
    plan=self.prepare();self.assertEqual(plan['report']['rejected'],2)
 def test_idempotent_old_plan_and_fresh_preview(self):
    plan=self.prepare();self.apply(plan)
    self.assertTrue(self.apply(plan)['idempotent'])
    self.assertEqual(self.prepare()['report']['unchanged'],8)
    with Session(self.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(StoreOffer)),8)
 def test_change_price_has_history_and_warning(self):
    self.apply();values=rows();values[1][3]='40000';self.write(values)
    plan=self.prepare();self.assertTrue(plan['report']['warnings']);self.apply(plan)
    with Session(self.engine) as db:
      self.assertEqual(db.scalar(select(StoreOffer).where(StoreOffer.category=='GPU')).price_rub,40000)
      self.assertEqual(db.scalar(select(func.count()).select_from(CatalogObservation)),9)
 def test_ti_vram_and_unknown_model(self):
    for name,match in [('GeForce RTX 5060 Ti','ambiguous'),('GeForce RTX 5060 Ti 16GB','matched'),
                       ('GeForce RTX 5060 Ti 8GB','matched'),('GeForce RTX 5070 Ti 16GB','unmatched'),
                       ('GeForce RTX 5060 Laptop 8GB','unmatched')]:
      with self.subTest(name=name):
        values=rows();values[1][1]=name;self.write(values)
        row=self.prepare()['rows'][1];self.assertEqual(row['matching'],match)
        if 'Ti 16' in name and '5060' in name:self.assertEqual(row['hardware_id'],4)
 def test_ram_generation_and_kit_preserved(self):
    values=rows();values[3][1]='DDR5 2x16GB';self.write(values)
    plan=self.prepare();self.assertEqual(plan['rows'][3]['title'],'DDR5 2x16GB')
 def test_invalid_url(self):
    for url in ['http://localhost/a','https://www.regard.ru.evil/product/123/','javascript:alert(1)']:
      values=rows();values[0][7]=url;self.write(values)
      self.assertEqual(self.prepare()['report']['rejected'],1)
 def test_missing_url_or_date_is_staged_without_fake_value(self):
    values=rows();values[0][7]='';values[1][6]='';self.write(values)
    plan=self.prepare();self.assertEqual(plan['report']['publishable'],6);self.apply(plan)
    self.assertIsNone(plan['rows'][0]['product_url']);self.assertIsNone(plan['rows'][1]['source_updated_at'])
 def test_regard_original_product_id_creates_only_preliminary_unknown_offer_url(self):
    from types import SimpleNamespace
    config=CatalogSchema(source='regard',version='regard-native-test',input_adapter='regard-native-v1',format='xlsx',
      columns={'external_product_id':'id','brand':'brand','title':'title','category':'category','price':'price',
               'source_updated_at':'updated','product_url':'url','availability':'availability'},
      categories={'GPU':'GPU'},availability={'no':'out_of_stock'},currency='RUB',decimal_separator='.',thousands_separator='none')
    raw={'id':'733527','brand':'NVIDIA','title':'GeForce RTX 5060 8GB','category':'GPU','price':'20000',
         'updated':NOW,'url':'','availability':''}
    hardware=[SimpleNamespace(id=2,type='GPU',name='GeForce RTX 5060',vram=8,raw_score=25000)]
    with patch('app.core.price_time.utc_now',return_value=datetime(2026,11,9,12,5,tzinfo=timezone.utc)):
      item=normalize(raw,config,hardware)
      self.assertEqual(item['product_url'],'https://www.regard.ru/product/733527')
      self.assertEqual(item['product_url_origin'],'regard_external_product_id')
      self.assertEqual(item['availability'],'unknown')
      self.assertTrue(item['preliminary_eligible'])
      self.assertFalse(item['eligible'])
      unavailable=normalize({**raw,'availability':'no'},config,hardware)
      self.assertFalse(unavailable['preliminary_eligible'])
 def test_fractional_price_is_exact_but_not_rounded_for_optimizer(self):
    values=rows();values[1][3]='20000,25';self.write(values)
    plan=self.prepare();self.assertEqual(plan['rows'][1]['price'],'20000.25')
    self.assertFalse(plan['rows'][1]['eligible']);self.apply(plan)
    self.assertEqual(len(self.offers(True)),7)
 def test_corrupt_xlsx_and_wrong_extension(self):
    self.write(fmt='xlsx');self.file.write_bytes(b'not a workbook')
    with self.assertRaises(CatalogError):self.prepare()
    self.file=self.file.with_suffix('.xls');self.file.write_bytes(b'abc')
    with self.assertRaises(CatalogError):self.prepare()
 def test_file_limit(self):
    self.file.write_bytes(b'a'*(8*1024*1024+1))
    with self.assertRaises(CatalogError):self.prepare()
 def test_partial_file_does_not_delete_absent_products(self):
    self.apply();self.write(rows()[:1]);self.apply()
    self.assertEqual(len(self.offers(True)),8)
 def test_cancel_preview_has_no_writes(self):
    self.prepare();self.assertEqual(self.offers(True),[])
    with Session(self.engine) as db:self.assertEqual(db.scalar(select(func.count()).select_from(CatalogProduct)),0)
 def test_apply_transaction_failure_rolls_back(self):
    from sqlalchemy import event
    count=[0]
    def fail(mapper,connection,target):
      count[0]+=1
      if count[0]==4:raise RuntimeError('fixture rollback')
    event.listen(StoreOffer,'before_insert',fail)
    try:
      with self.assertRaises(RuntimeError):self.apply()
    finally:event.remove(StoreOffer,'before_insert',fail)
    with Session(self.engine) as db:
      self.assertEqual(db.scalar(select(func.count()).select_from(StoreOffer)),0)
      self.assertEqual(db.scalar(select(func.count()).select_from(CatalogAccess)),0)
 def test_concurrent_identical_apply_has_one_set(self):
    plan=self.prepare()
    with ThreadPoolExecutor(max_workers=2) as pool:
      reports=list(pool.map(lambda _:self.apply(plan),range(2)))
    self.assertEqual(sum(r['idempotent'] for r in reports),1);self.assertEqual(len(self.offers(True)),8)
 def test_permission_gate_and_no_public_fixture(self):
    self.apply();self.assertEqual(self.offers(),[])
    with self.assertRaises(CatalogError):apply_import(self.engine,self.file,self.schema,self.prepare(),rights(),audience='public-commercial',fixture=True)
    denied=rights();denied['development']=False
    with self.assertRaises(CatalogError):apply_import(self.engine,self.file,self.schema,self.prepare(),denied,fixture=True)
 def test_full_pc_is_draft_without_network_or_fake_verification(self):
    self.apply()
    with Session(self.engine) as db,fixture_catalog(),patch.object(settings,'offers_live_search',False),patch.object(settings,'offers_feed_urls','{}'):
      result=assemble(BuildRequest(scenario='build',auto_parts=True,budget=60000,target_fps=60,game='Red Dead Redemption 2',
          mode='1440p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['regard'],
          allow_store_fallback=False,allow_platform_change=False),db)
      self.assertEqual(result['status'],'draft');self.assertEqual(len(result['parts']),8)
      self.assertLessEqual(result['total_price'],60000)
      self.assertTrue(all(p.get('price_verified_at') is None for p in result['parts']))
    self.net.assert_not_called()
 def test_checked_at_and_saved_history_are_not_changed_by_import(self):
    self.apply()
    with Session(self.engine) as db:
      db.add(OfferSearch(key='sentinel',checked_at=datetime(2026,11,8),statuses='[]'))
      db.add(SavedBuild(user_id=1,created_at=datetime(2026,11,8),data='{"history":123}'));db.commit()
    values=rows();values[1][3]='25000';self.write(values);self.apply()
    with Session(self.engine) as db:
      self.assertEqual(db.get(OfferSearch,'sentinel').checked_at,datetime(2026,11,8))
      self.assertEqual(db.scalar(select(SavedBuild)).data,'{"history":123}')
      self.assertTrue(all('price_verification' not in json.loads(r.attributes) for r in db.scalars(select(StoreOffer))))
      with patch('app.services.price_verification.source_blocked',return_value=True):
        verify_build_prices(db,{'parts':[{'offer_id':r.id} for r in db.scalars(select(StoreOffer))]})
      self.assertTrue(all('price_verification' not in json.loads(r.attributes) for r in db.scalars(select(StoreOffer))))
    self.net.assert_not_called()
 def test_tampered_file_or_plan_requires_new_preview(self):
    plan=self.prepare();self.file.write_bytes(csv_bytes(rows()[:1]))
    with self.assertRaises(CatalogError):self.apply(plan)
    self.write();plan=self.prepare();plan['rows'][0]['price']='1.00'
    with self.assertRaises(CatalogError):self.apply(plan)
 def test_formula_xlsx_is_rejected(self):
    self.write(fmt='xlsx');self.file.write_bytes(xlsx_bytes(rows(),formula=True))
    with self.assertRaises(CatalogError):self.prepare()
 def test_missing_columns_and_unsafe_html(self):
    self.file.write_bytes(b'Not;A;Schema\n1;2;3\n')
    with self.assertRaises(CatalogError):self.prepare()
    values=rows();values[0][1]='<script>alert(1)</script>';self.write(values)
    self.assertEqual(self.prepare()['report']['rejected'],1)

 def rewrite_zip(self,updates):
    from io import BytesIO
    from zipfile import ZipFile,ZIP_DEFLATED
    original=self.file.read_bytes();out=BytesIO()
    with ZipFile(BytesIO(original)) as src,ZipFile(out,'w',ZIP_DEFLATED) as dst:
      files={name:src.read(name) for name in src.namelist()};files.update(updates)
      for name,data in files.items():dst.writestr(name,data)
    self.file.write_bytes(out.getvalue())
 def test_zip_bomb_and_unsafe_xml_are_rejected(self):
    self.write(fmt='xlsx');self.rewrite_zip({'xl/bomb.xml':'x'*1000000})
    with self.assertRaises(CatalogError):self.prepare()
    self.write(fmt='xlsx');self.rewrite_zip({'xl/workbook.xml':'<!DOCTYPE x [<!ENTITY a "x">]><x/>'})
    with self.assertRaises(CatalogError):self.prepare()
 def test_sheet_selection_and_limits(self):
    self.write(fmt='xlsx');self.file.write_bytes(xlsx_bytes(rows(),sheets=2))
    with self.assertRaises(CatalogError):self.prepare()
    config=schema('xlsx');config['sheet']='Sheet1';self.schema.write_text(json.dumps(config),encoding='utf-8')
    self.assertEqual(self.prepare()['report']['accepted'],8)
    self.file.write_bytes(xlsx_bytes(rows(),sheets=9))
    with self.assertRaises(CatalogError):self.prepare()
 def test_csv_row_and_cell_limits(self):
    from app.services import catalog_files
    with patch.object(catalog_files,'MAX_ROWS',2):
      with self.assertRaises(CatalogError):self.prepare()
    values=rows();values[0][1]='a'*4097;self.write(values)
    with self.assertRaises(CatalogError):self.prepare()
 def test_changed_schema_requires_repreview(self):
    plan=self.prepare();config=schema();config['version']='changed';self.schema.write_text(json.dumps(config),encoding='utf-8')
    with self.assertRaises(CatalogError):self.apply(plan)
    self.assertEqual(self.offers(True),[])
 def test_out_of_stock_hides_offer_without_deleting_history(self):
    self.apply();values=rows();values[1][5]='no';self.write(values);self.apply()
    self.assertEqual(len(self.offers(True)),7)
    with Session(self.engine) as db:
      self.assertEqual(db.scalar(select(func.count()).select_from(StoreOffer)),8)
      self.assertEqual(db.scalar(select(func.count()).select_from(CatalogObservation)),9)
 def test_real_private_import_does_not_publish(self):
    config=schema();config['fixture']=False;self.write(config=config)
    result=apply_import(self.engine,self.file,self.schema,self.prepare(),rights())
    self.assertEqual(result['published'],0);self.assertEqual(result['materialized_offers'],0)
    with Session(self.engine) as db:
      self.assertEqual(db.scalar(select(func.count()).select_from(CatalogProduct)),8)
    self.assertEqual(self.offers(),[])
 def test_avito_import_is_denied(self):
    config=schema();config['source']='avito';self.write(config=config)
    permission=rights();permission['source']='avito'
    with self.assertRaisesRegex(CatalogError,'source_access_denied'):
      apply_import(self.engine,self.file,self.schema,self.prepare(),permission,fixture=True,allow_rejected=True)
 def test_missing_source_date_is_not_freshened(self):
    values=rows();values[0][6]='';self.write(values);plan=self.prepare()
    self.assertIsNone(plan['rows'][0]['source_updated_at']);self.assertFalse(plan['rows'][0]['eligible'])
    self.apply(plan);self.assertEqual(len(self.offers(True)),7)
 def test_offline_demo_end_to_end(self):
    from scripts.catalog_demo import run
    result=run(self.root/'demo')
    self.assertEqual(result['csv']['preview']['read'],11)
    self.assertEqual(result['csv']['preview']['accepted'],10)
    self.assertTrue(result['xlsx']['replay_idempotent'])
    self.assertEqual(len(result['search']['offers']),1)
    self.assertEqual(result['build']['status'],'draft')
    self.assertEqual(result['build']['total_price'],54500)
    self.net.assert_not_called()

 def test_private_offer_id_cannot_leak_via_saved_or_manual_build(self):
    from app.services.saved_prices import linked_offer
    from fastapi import HTTPException
    self.apply()
    with Session(self.engine) as db:
      offer=db.scalar(select(StoreOffer).where(StoreOffer.category=='motherboard'))
      self.assertIsNone(linked_offer(db,{'offer_id':offer.id,'url':offer.url,'name':offer.name,'type':'motherboard'}))
      request=BuildRequest(scenario='build',budget=60000,game='Red Dead Redemption 2',mode='1440p_high',socket='AM4',
        ram_type='DDR4',ram_capacity_gb=16,motherboard={'name':offer.name,'price':offer.price_rub,'offer_id':offer.id})
      with self.assertRaises(HTTPException) as error:assemble(request,db)
      self.assertEqual(error.exception.status_code,400)
 def test_excel_numeric_date_is_observation_not_import_time(self):
    from io import BytesIO
    from zipfile import ZipFile
    import re
    self.write(fmt='xlsx')
    with ZipFile(BytesIO(self.file.read_bytes())) as src:sheet=src.read('xl/worksheets/sheet1.xml').decode()
    # Excel serial 46335 is 2026-11-09; numeric date styles are converted without executing Excel.
    serial=(datetime(2026,11,9)-datetime(1899,12,30)).days
    sheet=re.sub(r'<c r="G2".*?</c>',f'<c r="G2" s="1"><v>{serial}</v></c>',sheet)
    self.rewrite_zip({'xl/worksheets/sheet1.xml':sheet,'xl/styles.xml':'<styleSheet><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>'})
    self.assertEqual(self.prepare()['rows'][0]['source_updated_at'],'2026-11-09T00:00:00Z')
 def test_failed_update_preserves_previous_offers(self):
    from sqlalchemy import event
    self.apply();values=rows();values[0][3]='6000';values[1][3]='25000';self.write(values)
    def fail(*args):raise RuntimeError('rollback')
    event.listen(StoreOffer,'before_update',fail)
    try:
      with self.assertRaises(RuntimeError):self.apply()
    finally:event.remove(StoreOffer,'before_update',fail)
    with Session(self.engine) as db:
      self.assertEqual(db.scalar(select(StoreOffer.price_rub).where(StoreOffer.category=='GPU')),20000)
      self.assertEqual(db.scalar(select(func.count()).select_from(CatalogObservation)),8)

 def test_public_permission_and_revocation(self):
    config=schema();config['fixture']=False;self.write(config=config)
    permission=rights();permission['public_display']=True
    report=apply_import(self.engine,self.file,self.schema,self.prepare(),permission,audience='public-noncommercial')
    self.assertEqual(report['published'],8);self.assertEqual(len(self.offers()),8)
    with Session(self.engine) as db:
      access=db.get(CatalogAccess,'regard');access.public_enabled=0;db.commit()
    self.assertEqual(self.offers(),[])
 def test_5070_and_5070_ti_are_distinct(self):
    from app.db.models import Hardware
    with Session(self.engine) as db:
      for index,name in enumerate(('GeForce RTX 5070','GeForce RTX 5070 Ti'),6):
        db.add(Hardware(id=index,type='GPU',name=name,vram=12,raw_score=30000,normalized_score=80))
      db.commit()
    values=rows();values[1][1]='GeForce RTX 5070 12GB';self.write(values)
    self.assertEqual(self.prepare()['rows'][1]['hardware_id'],6)
    values[1][1]='GeForce RTX 5070 Ti 12GB';self.write(values)
    self.assertEqual(self.prepare()['rows'][1]['hardware_id'],7)
 def test_conflicting_ddr_attributes_are_ambiguous(self):
    config=schema();config['attributes']={'ram_type':'Currency'}
    values=rows();values[3][4]='DDR5';config['columns'].pop('currency');config['currency']='RUB'
    self.write(values,config);row=self.prepare()['rows'][3]
    self.assertEqual(row['matching'],'ambiguous');self.assertFalse(row['eligible'])

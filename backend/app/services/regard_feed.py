"""Bounded streaming adapter for the owner-supplied native Regard XLSX.
No network, invented product URLs, stock claims or second offer model.
"""
import hashlib,re,time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile,BadZipFile
from xml.etree import ElementTree as ET
from app.services.catalog_files import CatalogError,checked,xml,lname

CATEGORIES={'Процессоры':'CPU','Видеокарты':'GPU','Материнские платы':'motherboard','Оперативная память':'memory','Накопители SSD':'storage','Блоки питания':'psu','Корпуса':'case'}
MAX_ROWS=100000;MAX_STRINGS=250000;MAX_EXPANDED=64*1024*1024
@dataclass
class RegardRead:
 rows:list
 metadata:dict

class RegardFeedAdapter:
 version='regard-native-xlsx-v1'
 def __init__(self,utc_offset_minutes=180):
  if not -720<=utc_offset_minutes<=840:raise CatalogError('invalid_feed_timezone')
  self.offset=utc_offset_minutes
 def read(self,data):
  start=time.perf_counter()
  if len(data)>8*1024*1024:raise CatalogError('file_too_large')
  try:
   with ZipFile(BytesIO(data)) as archive:
    infos=archive.infolist();names=[i.filename for i in infos]
    if len(infos)>512 or len(set(names))!=len(names) or sum(i.file_size for i in infos)>MAX_EXPANDED:raise CatalogError('zip_limit')
    for i in infos:
     path=PurePosixPath(i.filename);low=i.filename.lower()
     if path.is_absolute() or '..' in path.parts or chr(92) in i.filename:raise CatalogError('unsafe_zip_path')
     if i.file_size>48*1024*1024 or i.file_size>max(i.compress_size,1)*150:raise CatalogError('zip_ratio_limit')
     if any(t in low for t in ('vba','macrosheet','activex','embeddings/','externallinks/')):raise CatalogError('active_xlsx_content')
    types=xml(archive.read('[Content_Types].xml'))
    if any('macroenabled' in str(e.attrib).lower() for e in types):raise CatalogError('macros_forbidden')
    if not any(e.get('PartName')=='/xl/workbook.xml' and e.get('ContentType')=='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml' for e in types):raise CatalogError('wrong_workbook_content_type')
    book=xml(archive.read('xl/workbook.xml'));sheets=[e for e in book.iter() if lname(e)=='sheet']
    if len(sheets)!=1:raise CatalogError('regard_sheet_structure_changed')
    rid=next((v for k,v in sheets[0].attrib.items() if k.endswith('}id')),None)
    rels=xml(archive.read('xl/_rels/workbook.xml.rels'));rel=next((e for e in rels if e.get('Id')==rid),None)
    if rel is None or rel.get('TargetMode')=='External':raise CatalogError('invalid_sheet_target')
    target=rel.get('Target','');target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
    if not target.startswith('xl/worksheets/') or '..' in PurePosixPath(target).parts or chr(92) in target:raise CatalogError('invalid_sheet_target')
    opened=time.perf_counter();shared=[]
    if 'xl/sharedStrings.xml' in names:
     for e in self.entries(archive,'xl/sharedStrings.xml','si'):
      shared.append(checked(''.join(t.text or '' for t in e.iter() if lname(t)=='t')))
      if len(shared)>MAX_STRINGS:raise CatalogError('shared_string_limit')
    rows=[];path=['','',''];products=0;count=0;stamp=None;header=False;seen=set();categories=Counter()
    previous=0
    for e in self.entries(archive,target,'row'):
     count+=1
     try:number=int(e.get('r'))
     except (ValueError,TypeError):raise CatalogError('invalid_row_reference') from None
     if number<=previous or number>MAX_ROWS or count>MAX_ROWS:raise CatalogError('row_limit')
     previous=number;values={}
     for c in e:
      if lname(c)!='c':continue
      if any(lname(t)=='f' for t in c):raise CatalogError('formula_forbidden')
      ref=c.get('r','');match=re.fullmatch(r'([A-H])'+str(number),ref)
      if not match:raise CatalogError('regard_columns_changed')
      col=match[1]
      if col in values:raise CatalogError('duplicate_cell')
      kind=c.get('t','n');raw=next((v.text or '' for v in c if lname(v)=='v'),'')
      if kind=='s':
       try:
        index=int(raw)
        if index<0:raise ValueError()
        raw=shared[index]
       except (ValueError,IndexError):raise CatalogError('invalid_shared_string') from None
      elif kind=='inlineStr':raw=''.join(v.text or '' for v in c.iter() if lname(v)=='t')
      elif kind not in ('n','str','b'):raise CatalogError('unsupported_cell_type')
      values[col]=checked(raw).strip()
     if number==18:
      m=re.fullmatch(r'Прайс-лист актуален на (\d{2}\.\d{2}\.\d{4}), (\d{2}:\d{2})',values.get('A',''))
      if not m:raise CatalogError('regard_date_structure_changed')
      try:stamp=datetime.strptime(' '.join(m.groups()),'%d.%m.%Y %H:%M').replace(tzinfo=timezone(timedelta(minutes=self.offset))).astimezone(timezone.utc).isoformat()
      except ValueError:raise CatalogError('invalid_source_date') from None
     if number==21:
      expected={'A':'ID','D':'Производитель','E':'PN','F':'Наименование','G':'Цена, руб.','H':'Гарантия, мес.'}
      if any(values.get(k)!=v for k,v in expected.items()):raise CatalogError('regard_header_changed')
      header=True
     if number<23:continue
     ident=values.get('A','')
     if ident.isdecimal() and values.get('F'):
      products+=1
      category=CATEGORIES.get(path[0])
      if path[0]=='Системы охлаждения' and path[1]=='Кулеры для процессоров':category='cooler'
      if category:
       if ident in seen:raise CatalogError('duplicate_product_id')
       seen.add(ident)
       categories[category]+=1
       rows.append((number,{'external_product_id':ident,'vendor_code':values.get('E',''),'brand':values.get('D',''),'title':values['F'],'price':values.get('G',''),'category':category,'source_updated_at':stamp or '', 'product_url':'','availability':'','description':'Категория прайса: '+' / '.join(v for v in path if v)+'; гарантия: '+values.get('H','')}))
     elif not values.get('F') and not values.get('G'):
      for index,col in enumerate('ABC'):
       if values.get(col):path[index:]=[values[col]]+['']*(2-index);break
    if not header or stamp is None:raise CatalogError('regard_structure_changed')
    if not rows or not products:raise CatalogError('regard_no_products')
    return RegardRead(rows,{'schema_version':self.version,'sha256':hashlib.sha256(data).hexdigest(),'excel_rows':previous,'physical_rows':count,'product_rows':products,'selected_rows':len(rows),'categories':dict(categories),'source_updated_at':stamp,'source_utc_offset_minutes':self.offset,'timezone_basis':'Explicit analysis configuration; timezone not provided by XLSX','open_seconds':opened-start,'parse_seconds':time.perf_counter()-opened})
  except (BadZipFile,KeyError,ET.ParseError,UnicodeError,RuntimeError) as error:
   if isinstance(error,CatalogError):raise
   raise CatalogError('invalid_regard_xlsx') from None
 @staticmethod
 def entries(archive,name,tag):
  # Scan declarations before iterparse; never expand DTD/entity declarations.
  with archive.open(name) as stream:
   tail=b''
   while block:=stream.read(65536):
    sample=(tail+block).upper()
    if b'<!DOCTYPE' in sample or b'<!ENTITY' in sample or b'\x00' in sample:raise CatalogError('unsafe_xml')
    tail=sample[-16:]
  with archive.open(name) as stream:
   parents=[]
   for event,e in ET.iterparse(stream,events=('start','end')):
    if event=='start':parents.append(e);continue
    if lname(e)==tag:
     yield e
     if len(parents)>1:parents[-2].remove(e)
     e.clear()
    parents.pop()

def compare_feeds(old,new):
 def indexed(rows):
  result={}
  for row in rows:
   key=str(row.get('external_product_id',''))
   if not key or key in result:raise CatalogError('duplicate_product_id')
   result[key]=row
  return result
 a,b=indexed(old),indexed(new);result={k:[] for k in ('new','missing','price_changed','changed','unchanged')}
 result['new']=sorted(b.keys()-a.keys());result['missing']=sorted(a.keys()-b.keys())
 for key in sorted(a.keys()&b.keys()):
  fields=('title','category','brand','vendor_code','price')
  kind='price_changed' if a[key].get('price')!=b[key].get('price') else 'changed' if any(a[key].get(f)!=b[key].get(f) for f in fields) else 'unchanged'
  result[kind].append(key)
 result['suspicious_shrink']=bool(a and len(b)<len(a)*.7)
 return result

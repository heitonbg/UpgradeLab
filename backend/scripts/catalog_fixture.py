"""Synthetic catalogue fixtures; never downloaded shop offers."""
import csv,json
from datetime import datetime,timezone
from io import StringIO,BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree.ElementTree import Element,SubElement,tostring
from pathlib import Path
NOW='2026-11-09T12:00:00Z'
HEADERS=['ID','Title','Category','Price','Currency','Availability','Updated','URL']
PRODUCTS=[
 ('CPU','AMD Ryzen 5 5600','5000'),
 ('GPU','GeForce RTX 5060 8GB','20000'),
 ('motherboard','ASRock B450M-HDV R4.0 DDR4','10000'),
 ('memory','DDR4 2x8GB','9000'),
 ('storage','Samsung 870 EVO 500GB','3000'),
 ('psu','MSI MAG A650BN 650W','3500'),
 ('case','DeepCool CC560','3000'),
 ('cooler','DeepCool AG400','1000')]
def rows(now=NOW):
    return [[str(i),name,category,price,'RUB','yes',now,
             f'https://www.regard.ru/product/{990000000+i}/fixture-not-a-real-offer']
            for i,(category,name,price) in enumerate(PRODUCTS,1)]
def schema(fmt='csv'):
    return {'source':'regard','version':'fixture-1-not-regard-schema','format':fmt,'fixture':True,
      'columns':dict(zip(['sku','title','category','price','currency','availability','source_updated_at','product_url'],HEADERS)),
      'categories':{row[0]:row[0] for row in PRODUCTS},'availability':{'yes':'in_stock','no':'out_of_stock'},
      'decimal_separator':',','thousands_separator':' ','delimiter':';'}
def rights():
    return {'source':'regard','development':True,'public_display':False,'commercial':False,'automatic_download':False,
            'basis':'Synthetic fixture created locally; no licence for real shop data',
            'owner_confirmed_by':'Fixture developer','confirmed_at':NOW}
def csv_bytes(values,encoding='utf-8'):
    out=StringIO();writer=csv.writer(out,delimiter=';');writer.writerow(HEADERS);writer.writerows(values)
    return out.getvalue().encode(encoding)
def xlsx_bytes(values,formula=False,sheets=1):
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    doc=Element('worksheet',xmlns=ns);data=SubElement(doc,'sheetData')
    for index,values_row in enumerate([HEADERS,*values],1):
        row=SubElement(data,'row',r=str(index))
        for column,value in enumerate(values_row):
            cell=SubElement(row,'c',r=chr(65+column)+str(index),t='inlineStr')
            if formula and index==2 and column==3:SubElement(cell,'f').text='1+1'
            inline=SubElement(cell,'is');SubElement(inline,'t').text=str(value)
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>')
        archive.writestr('xl/workbook.xml','<workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="Sheet{i}" sheetId="{i}" r:id="r{i}"/>' for i in range(1,sheets+1))+'</sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="r{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1,sheets+1))+'</Relationships>')
        for i in range(1,sheets+1):archive.writestr(f'xl/worksheets/sheet{i}.xml',tostring(doc))
    return out.getvalue()
def seed(db):
    from app.db.models import Hardware
    db.add_all([
      Hardware(id=1,type='CPU',name='AMD Ryzen 5 5600',socket='AM4',raw_score=21000,normalized_score=50),
      Hardware(id=2,type='GPU',name='GeForce RTX 5060',vram=8,raw_score=25000,normalized_score=60),
      Hardware(id=3,type='GPU',name='GeForce RTX 5060 Ti',vram=8,raw_score=29000,normalized_score=70),
      Hardware(id=4,type='GPU',name='GeForce RTX 5060 Ti',vram=16,raw_score=29000,normalized_score=70),
      Hardware(id=5,type='CPU',name='AMD Ryzen 5 5600G',socket='AM4',raw_score=19000,normalized_score=40)])
    db.commit()

"""Bounded CSV/OpenXML reader. No formulas, macros, external fetch or archive extraction."""
import csv
import re
from datetime import datetime,timedelta
from decimal import Decimal,InvalidOperation
from io import StringIO,BytesIO
from pathlib import PurePosixPath
from zipfile import ZipFile,BadZipFile
from xml.etree import ElementTree as ET

MAX_BYTES=8*1024*1024
MAX_EXPANDED=32*1024*1024
MAX_ROWS=20000
MAX_COLS=64
MAX_VALUE=4096

class CatalogError(ValueError):pass

def checked(value):
    value='' if value is None else str(value)
    if len(value)>MAX_VALUE or any(ord(c)<32 and c not in '\t\n\r' for c in value):
        raise CatalogError('value_limit')
    return value

def xml(data):
    try:
        if len(data)>8*1024*1024:raise CatalogError('xml_size_limit')
        text=data.decode('utf-8-sig')
        if '\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise CatalogError('unsafe_xml')
        return ET.fromstring(text)
    except (UnicodeError,ET.ParseError):
        raise CatalogError('invalid_xlsx_xml') from None

def lname(element):return element.tag.rsplit('}',1)[-1]

def read_table(data,schema):
    if schema.input_adapter=='regard-native-v1':
        from app.services.regard_feed import RegardFeedAdapter
        return RegardFeedAdapter(schema.source_utc_offset_minutes).read(data).rows
    if len(data)>MAX_BYTES:raise CatalogError('file_too_large')
    if schema.format=='csv':
        if data.startswith(b'PK') or b'\x00' in data:raise CatalogError('wrong_file_type')
        try:
            text=data.decode(schema.encoding)
            csv.field_size_limit(MAX_VALUE)
            if any(len(line)>MAX_COLS*(MAX_VALUE+10) for line in StringIO(text)):
                raise CatalogError('row_width_limit')
            rows=[]
            for values in csv.reader(StringIO(text),delimiter=schema.delimiter,strict=True):
                if len(rows)>MAX_ROWS+schema.header_row:raise CatalogError('row_limit')
                if len(values)>MAX_COLS:raise CatalogError('column_limit')
                rows.append(values)
        except (UnicodeError,csv.Error):raise CatalogError('invalid_csv_or_encoding') from None
        if len(rows)>MAX_ROWS+schema.header_row:raise CatalogError('row_limit')
    else:
        rows=read_xlsx(data,schema)
    if len(rows)<schema.header_row:raise CatalogError('missing_header')
    header=[checked(v).strip() for v in rows[schema.header_row-1]]
    if len(header)>MAX_COLS or len(set(header))!=len(header):raise CatalogError('invalid_header')
    needed=set(schema.columns.values())|set(schema.attributes.values())
    if not needed.issubset(header):raise CatalogError('missing_columns')
    result=[]
    for number,values in enumerate(rows[schema.header_row:],schema.header_row+1):
        if len(values)>MAX_COLS or len(values)>len(header):raise CatalogError('column_limit')
        if not any(str(v).strip() for v in values):continue
        if len(result)>=MAX_ROWS:raise CatalogError('row_limit')
        result.append((number,dict(zip(header,[checked(v) for v in values]+['']*(len(header)-len(values))))))
    return result

def read_xlsx(data,schema):
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos=archive.infolist()
            if len(infos)>512 or sum(i.file_size for i in infos)>MAX_EXPANDED:raise CatalogError('zip_limit')
            names=[i.filename for i in infos]
            if len(names)!=len(set(names)):raise CatalogError('duplicate_zip_entry')
            for info in infos:
                path=PurePosixPath(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename:raise CatalogError('unsafe_zip_path')
                if info.file_size>MAX_EXPANDED or info.file_size>max(1,info.compress_size)*150:
                    raise CatalogError('zip_ratio_limit')
                lowered=info.filename.lower()
                if any(token in lowered for token in ('vba','macrosheet','activex','embeddings/','externallinks/')):
                    raise CatalogError('active_xlsx_content')
            def load(name):
                try:return xml(archive.read(name))
                except KeyError:raise CatalogError('invalid_xlsx_structure') from None
            types=load('[Content_Types].xml')
            if any('macroenabled' in str(e.attrib).lower() for e in types):raise CatalogError('macros_forbidden')
            if not any(e.get('PartName')=='/xl/workbook.xml' and e.get('ContentType')==
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml' for e in types):
                raise CatalogError('wrong_workbook_content_type')
            book=load('xl/workbook.xml')
            epoch1904=any(lname(e)=='workbookPr' and e.get('date1904') in ('1','true') for e in book)
            date_styles=set()
            if 'xl/styles.xml' in names:
                styles=load('xl/styles.xml')
                custom={int(e.get('numFmtId')):e.get('formatCode','') for e in styles.iter() if lname(e)=='numFmt'}
                xfs=next((e for e in styles if lname(e)=='cellXfs'),[])
                for index,entry in enumerate(xfs):
                    fmt=int(entry.get('numFmtId','0'))
                    code=re.sub(r'"[^"]*"|\[[^\]]*\]','',custom.get(fmt,'')).lower()
                    if 14<=fmt<=22 or fmt in (45,46,47) or re.search(r'y+|d+',code):
                        date_styles.add(index)
            sheets=[e for e in book.iter() if lname(e)=='sheet']
            if not sheets or len(sheets)>8:raise CatalogError('sheet_limit')
            if schema.sheet:
                chosen=next((s for s in sheets if s.get('name')==schema.sheet),None)
                if chosen is None:raise CatalogError('sheet_not_found')
            elif len(sheets)==1:chosen=sheets[0]
            else:raise CatalogError('sheet_must_be_explicit')
            rels=load('xl/_rels/workbook.xml.rels')
            rid=next((v for k,v in chosen.attrib.items() if k.endswith('}id')),None)
            rel=next((e for e in rels if e.get('Id')==rid),None)
            if rel is None or rel.get('TargetMode')=='External':raise CatalogError('invalid_sheet_target')
            target=rel.get('Target','')
            path=PurePosixPath(target)
            if '..' in path.parts or '\\' in target:raise CatalogError('invalid_sheet_target')
            target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            if not target.startswith('xl/worksheets/'):raise CatalogError('invalid_sheet_target')
            shared=[]
            if 'xl/sharedStrings.xml' in names:
                for entry in load('xl/sharedStrings.xml'):
                    shared.append(checked(''.join(e.text or '' for e in entry.iter() if lname(e)=='t')))
                    if len(shared)>50000:raise CatalogError('shared_string_limit')
            rows=[]
            for row in load(target).iter():
                if lname(row)!='row':continue
                if len(rows)>MAX_ROWS+schema.header_row:raise CatalogError('row_limit')
                try:row_number=int(row.get('r',str(len(rows)+1)))
                except ValueError:raise CatalogError('invalid_row_reference') from None
                if row_number<=len(rows) or row_number>MAX_ROWS+schema.header_row:raise CatalogError('row_limit')
                rows.extend([[] for _ in range(row_number-len(rows)-1)])
                values=[]
                for cell in row:
                    if lname(cell)!='c':continue
                    if any(lname(e)=='f' for e in cell):raise CatalogError('formula_forbidden')
                    ref=cell.get('r','')
                    letters=''.join(c for c in ref if 'A'<=c<='Z')
                    if not letters:raise CatalogError('invalid_cell_reference')
                    column=0
                    for c in letters:column=column*26+ord(c)-64
                    if column>MAX_COLS or column<=len(values):raise CatalogError('column_limit')
                    values.extend(['']*(column-len(values)))
                    kind=cell.get('t','n')
                    raw=next((e.text or '' for e in cell if lname(e)=='v'),'')
                    if kind=='s':
                        try:
                            offset=int(raw)
                            if not 0<=offset<len(shared):raise ValueError()
                            raw=shared[offset]
                        except (ValueError,IndexError):raise CatalogError('invalid_shared_string') from None
                    elif kind=='inlineStr':raw=''.join(e.text or '' for e in cell.iter() if lname(e)=='t')
                    elif kind not in ('n','str','b','d'):raise CatalogError('unsupported_cell_type')
                    if kind=='n' and int(cell.get('s','0')) in date_styles:
                        try:
                            serial=Decimal(raw)
                            if not serial.is_finite() or abs(serial)>1000000 or not epoch1904 and int(serial)==60:raise ValueError()
                            base=datetime(1904,1,1) if epoch1904 else datetime(1899,12,31) if serial<60 else datetime(1899,12,30)
                            raw=(base+timedelta(microseconds=int(serial*Decimal(86400000000)))).isoformat()
                        except (ValueError,InvalidOperation,OverflowError):raise CatalogError('invalid_excel_date') from None
                    values[column-1]=checked(raw)
                rows.append(values)
            return rows
    except (BadZipFile,RuntimeError,ET.ParseError,ValueError,KeyError,OverflowError) as error:
        if isinstance(error,CatalogError):raise
        raise CatalogError('invalid_xlsx') from None

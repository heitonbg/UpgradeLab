"""Two-phase local catalogue import. No network calls or application startup side effects."""
import csv,hashlib,json,re,time
from collections import Counter
from datetime import datetime
from decimal import Decimal,InvalidOperation
from pathlib import Path
from types import SimpleNamespace
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.core import price_time
from app.core.price_time import as_utc,iso_utc,as_naive_utc,OBSERVATION_SKEW
from app.db.models import Hardware,StoreOffer,CatalogProduct,CatalogAccess,CatalogImport,CatalogObservation
from app.schemas.catalog import CatalogSchema,CatalogRights
from app.schemas.offers import OfferInput,store_url
from app.services.catalog_files import CatalogError,read_table,MAX_BYTES
from app.services.offers import signature,model_signatures,component_listing,title_category,consistent_hardware_title
from app.services.network_policy import validate_url,NetworkPolicyError
from app.services.offer_safety import safe_offers
from app.services.component_quality import quality_check,invalid_manual_part
from app.services.automatic_builds import memory_configuration
from app.services.builds import board_socket
from app.services.gaming_selection import is_case_offer

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def digest(value):return hashlib.sha256(value if isinstance(value,bytes) else canonical(value).encode()).hexdigest()
def key_text(value):return str(value).strip().casefold().replace('С‘','Рµ')

def read_local(path,limit=MAX_BYTES):
    try:
        path=Path(path)
        if not path.is_file() or path.stat().st_size>limit:raise CatalogError('file_missing_or_too_large')
        with path.open('rb') as stream:data=stream.read(limit+1)
        if len(data)>limit:raise CatalogError('file_too_large')
        return data
    except OSError:raise CatalogError('file_read_failed') from None

def load_schema(path):
    raw=read_local(path,65536)
    try:return CatalogSchema.model_validate_json(raw)
    except ValueError:raise CatalogError('invalid_schema') from None

def parse_money(value,schema):
    value=str(value).strip().replace('\u00a0',' ').replace('\u202f',' ')
    if not value:raise CatalogError('price_missing')
    parts=value.split(schema.decimal_separator)
    if len(parts)>2 or len(parts)==2 and not re.fullmatch(r'\d{1,2}',parts[1]):
        raise CatalogError('invalid_price')
    integer=parts[0];group=schema.thousands_separator
    if group!='none' and group in integer:
        if not re.fullmatch(r'\d{1,3}(?:'+re.escape(group)+r'\d{3})+',integer):
            raise CatalogError('ambiguous_price_grouping')
        integer=integer.replace(group,'')
    if not re.fullmatch(r'\d+',integer):raise CatalogError('invalid_price')
    try:price=Decimal(integer+('.'+parts[1] if len(parts)==2 else ''))
    except InvalidOperation:raise CatalogError('invalid_price') from None
    if not price.is_finite() or not 0<price<=100000000:raise CatalogError('invalid_price')
    return price.quantize(Decimal('0.01'))

def model_match(hardware,row):
    category=row['category'];name=row['title']
    if category in ('CPU','GPU'):
        if not component_listing(name) or re.search(r'laptop|mobile|max-q|РЅРѕСѓС‚Р±СѓРє',name,re.I):
            return None,'unmatched'
        sig=signature(name,category)
        if not sig or len(model_signatures(name,category))!=1:return None,'ambiguous'
        if row.get('model') and signature(row['model'],category)!=sig:return None,'ambiguous'
        pool=[h for h in hardware if h.type==category and signature(h.name,category)==sig and consistent_hardware_title(name,h,category)]
        if category=='GPU':
            sizes={int(v) for v in re.findall(r'\b(\d+)\s*(?:gb|РіР±)\b',name,re.I)}
            if len(sizes)>1:return None,'ambiguous'
            if sizes:pool=[h for h in pool if h.vram in sizes]
            brand=key_text(row.get('brand',''))
            if brand in ('amd','intel') and sig.startswith(('rtx','gtx','gt')):return None,'unmatched'
        elif row.get('brand'):
            brand=key_text(row['brand'])
            if brand in ('intel','amd'):
                pool=[h for h in pool if brand in h.name.casefold()]
        return (pool[0].id,'matched') if len(pool)==1 else (None,'ambiguous' if len(pool)>1 else 'unmatched')
    obj=SimpleNamespace(name=name,category=category,attributes=canonical(row['attributes']),condition='new',source=row['source'])
    if invalid_manual_part(name,category):return None,'unmatched'
    if category in ('memory','motherboard'):
        named_ram=set(re.findall(r'DDR[45]',name.upper()))
        declared_ram=row['attributes'].get('ram_type')
        if len(named_ram)>1 or declared_ram and named_ram and declared_ram not in named_ram:
            return None,'ambiguous'
        if category=='motherboard' and row['attributes'].get('socket') and board_socket(name) and row['attributes']['socket']!=board_socket(name):
            return None,'ambiguous'
    if category=='memory':
        info=memory_configuration(obj)
        return (None,'structured') if info and info['ram_type'] in ('DDR4','DDR5') and info['capacity_gb']>=8 and info['modules'] in (1,2) else (None,'unmatched')
    if category=='motherboard':
        socket=row['attributes'].get('socket') or board_socket(name)
        return (None,'structured') if socket and any(token in name.upper() for token in ('DDR4','DDR5','B450','B550','A520','B650')) else (None,'unmatched')
    if category=='case':return (None,'structured') if is_case_offer(obj) else (None,'unmatched')
    valid=any(quality_check(obj,socket)[0] for socket in ('AM4','AM5','LGA1700'))
    return (None,'structured') if valid else (None,'unmatched')

def normalize(raw,schema,hardware):
    values={field:raw[column].strip() for field,column in schema.columns.items()}
    if any('<' in v or '>' in v or v.startswith(('=','@')) for k,v in values.items() if k not in ('price',)):
        raise CatalogError('unsafe_text')
    if values.get('source_id') not in (None,'',schema.source):raise CatalogError('source_mismatch')
    title=values.get('title','')
    if not 2<=len(title)<=300:raise CatalogError('invalid_title')
    category=schema.categories.get(values.get('category',''))
    if category is None:category=title_category(title) if not values.get('category') else None
    if category is None:raise CatalogError('unknown_category')
    inferred=title_category(title)
    if inferred and inferred!=category:raise CatalogError('category_mismatch')
    currency=values.get('currency') or schema.currency
    if currency not in ('RUB','RUR','в‚Ѕ'):raise CatalogError('unsupported_currency')
    price=parse_money(values.get('price',''),schema)
    url=values.get('product_url') or None
    url_origin='source_file'
    if url is None and schema.input_adapter=='regard-native-v1':
        external_id=values.get('external_product_id','')
        if re.fullmatch(r'[1-9][0-9]{0,15}',external_id):
            url=f'https://www.regard.ru/product/{external_id}'
            url_origin='regard_external_product_id'
    if url:
        if not store_url(schema.source,url):raise CatalogError('invalid_product_url')
        url=validate_url(url).url
    image=values.get('image_url') or None
    if image:
        try:image=validate_url(image).url
        except NetworkPolicyError:raise CatalogError('invalid_image_url') from None
    identity=None
    for field in ('external_product_id','sku','vendor_code'):
        value=values.get(field)
        if value:
            if identity is None and (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,99}',value) or '..' in value):
                raise CatalogError('invalid_product_id')
            identity=identity or field+':'+value
    if identity is None:
        if url is None:raise CatalogError('missing_identity')
        identity='url:'+digest(url)
    stamp=values.get('source_updated_at') or None
    if stamp:
        if schema.date_format:
            try:stamp=datetime.strptime(stamp,schema.date_format)
            except ValueError:raise CatalogError('invalid_source_date') from None
        stamp=as_utc(stamp)
        if stamp is None or stamp>price_time.utc_now()+OBSERVATION_SKEW:raise CatalogError('invalid_source_date')
    attributes={}
    for field,column in schema.attributes.items():
        value=raw[column].strip()
        if not value:continue
        if field in ('capacity_gb','modules','watts'):
            if not value.isdecimal() or not 0<int(value)<1000000:raise CatalogError('invalid_attribute')
            value=int(value)
        elif field in ('sockets','board_formats','psu_formats'):
            value=[v.strip() for v in value.split('|') if v.strip()]
        attributes[field]=value
    if values.get('description'):attributes['description']=values['description']
    if schema.geography:attributes['geography']=schema.geography.model_dump(mode='json')
    attributes.update(schema.technical)
    availability=schema.availability.get(key_text(values.get('availability','')),'unknown')
    quantity=values.get('quantity') or None
    if quantity is not None:
        if not quantity.isdecimal() or len(quantity)>9:raise CatalogError('invalid_quantity')
        quantity=int(quantity)
        if quantity==0:availability='out_of_stock'
    row={**values,'source':schema.source,'external_key':identity,'title':title,
         'normalized_title':' '.join(title.split()),'category':category,'price':str(price),'currency':'RUB',
         'product_url':url,'image_url':image,'source_updated_at':iso_utc(stamp),
         'availability':availability,'quantity':quantity,'attributes':attributes}
    row['product_url_origin']=url_origin if url else None
    hardware_id,matching=model_match(hardware,row)
    row.update(hardware_id=hardware_id,matching=matching)
    reasons=[]
    if matching not in ('matched','structured'):reasons.append(matching)
    if url is None:reasons.append('missing_product_url')
    if stamp is None:reasons.append('unknown_source_date')
    if availability!='in_stock':reasons.append('availability_'+availability)
    if price!=price.to_integral_value():reasons.append('fractional_price_not_supported_by_optimizer')
    quality_ok=False
    if matching in ('matched','structured') and url and stamp and price==price.to_integral_value():
        offer=OfferInput(source=schema.source,name=title,category=category,price_rub=int(price),url=url,
                         observed_at=stamp,attributes=attributes,model_name=values.get('model') or None)
        candidate=SimpleNamespace(id=0,source=schema.source,name=title,category=category,price_rub=int(price),
                                  hardware_id=hardware_id,condition='new',attributes=canonical(attributes),url=url)
        quality_ok=bool(safe_offers([candidate],{h.id:h for h in hardware}))
        if not quality_ok:reasons.append('quality_rejected')
    row['analysis_eligible']=bool(schema.input_adapter=='regard-native-v1' and matching in ('matched','structured') and stamp is not None and price==price.to_integral_value() and availability!='out_of_stock' and quality_ok)
    # Unknown stock can support a preliminary Regard estimate, never a confirmed offer.
    row['preliminary_eligible']=bool(row['analysis_eligible'] and url and availability=='unknown')
    row['eligible']=not reasons
    row['reasons']=reasons
    row['key']=digest([schema.source,identity])
    return row

def hardware_snapshot(db):
    return [{column.name:getattr(row,column.name) for column in Hardware.__table__.columns}
            for row in db.scalars(select(Hardware).order_by(Hardware.id))]

def source_snapshot(db,source):
    result=[]
    for row in db.scalars(select(CatalogProduct).where(CatalogProduct.source==source).order_by(CatalogProduct.key)):
        offer=db.get(StoreOffer,row.offer_id) if row.offer_id else None
        result.append([row.key,row.payload,row.offer_id,
             [offer.price_rub,offer.name,offer.observed_at,offer.origin,offer.attributes] if offer else None])
    access=db.get(CatalogAccess,source)
    result.append(['@access',access.rights,access.public_enabled,access.fixture] if access else ['@access',None])
    return result

def prepare_import(engine,file,schema_path,*,received_at=None,metrics=None):
    started=time.perf_counter()
    schema=load_schema(schema_path)
    path=Path(file)
    if path.suffix.lower()!='.'+schema.format:raise CatalogError('extension_mismatch')
    data=read_local(file)
    opened=time.perf_counter()
    table=read_table(data,schema)
    parsed=time.perf_counter()
    with Session(engine) as db:
        hardware_data=hardware_snapshot(db)
        state=source_snapshot(db,schema.source)
        previous={p.key:json.loads(p.payload) for p in db.scalars(select(CatalogProduct).where(CatalogProduct.source==schema.source))}
    hardware=[SimpleNamespace(**values) for values in hardware_data]
    received=iso_utc(received_at)
    if received_at and (received is None or as_utc(received)>price_time.utc_now()):raise CatalogError('invalid_received_date')
    normalizing=time.perf_counter()
    rows=[];errors=[]
    for number,raw in table:
        try:
            row=normalize(raw,schema,hardware);row['row_number']=number;rows.append(row)
        except (CatalogError,ValueError,TypeError) as error:
            code=str(error) if isinstance(error,CatalogError) else 'invalid_row'
            errors.append({'row':number,'reason':code})
    if metrics is not None:metrics.update(file_read_seconds=opened-started,parse_seconds=parsed-opened,normalization_seconds=time.perf_counter()-normalizing)
    identities=Counter(r['key'] for r in rows)
    urls=Counter(r['product_url'] for r in rows if r['product_url'])
    valid=[]
    for row in rows:
        if identities[row['key']]>1 or row['product_url'] and urls[row['product_url']]>1:
            errors.append({'row':row['row_number'],'reason':'duplicate_identity_or_url'})
        else:valid.append(row)
    counts={'new':0,'updated':0,'unchanged':0}
    warnings=[]
    for row in valid:
        old=previous.get(row['key'])
        compared={k:v for k,v in row.items() if k!='row_number'}
        change='new' if old is None else 'unchanged' if old==compared else 'updated'
        counts[change]+=1
        if old and Decimal(old['price']) and abs(Decimal(row['price'])/Decimal(old['price'])-1)>Decimal('0.5'):
            warnings.append({'row':row['row_number'],'reason':'price_change_over_50_percent'})
    report={'read':len(table),'accepted':len(valid),'rejected':len(errors),'publishable':sum(r['eligible'] for r in valid),
            'preliminary_candidates':sum(bool(r.get('preliminary_eligible')) for r in valid),
            'matching':dict(Counter(r['matching'] for r in valid)),
            'categories':dict(Counter(r['category'] for r in valid)),**counts,
            'errors':errors,'warnings':warnings,'staged':[
                {'row':r['row_number'],'reasons':r['reasons']} for r in valid if not r['eligible']],
            'price_min':min((r['price'] for r in valid),key=Decimal,default=None),
            'price_max':max((r['price'] for r in valid),key=Decimal,default=None)}
    plan={'source':schema.source,'file_sha256':digest(data),'schema_sha256':digest(schema.model_dump()),
          'hardware_sha256':digest(hardware_data),'source_sha256':digest(state),'received_at':received,
          'complete':schema.complete,'fixture':schema.fixture,'report':report,'rows':valid}
    plan['plan_sha256']=digest(plan)
    return plan

def apply_import(engine,file,schema_path,prepared,rights,*,audience='development',fixture=False,allow_rejected=False,analysis=False,allow_shrink=False):
    import_schema=load_schema(schema_path)
    if analysis:
        from app.services.catalog_access import analysis_database
        analysis_database(engine)
        if audience!='development' or fixture:raise CatalogError('analysis_must_remain_private')
    if audience not in ('development','public-noncommercial','public-commercial'):raise CatalogError('invalid_audience')
    try:permission=CatalogRights.model_validate(rights)
    except ValueError:raise CatalogError('invalid_rights_record') from None
    source=permission.source
    if source=='avito':raise CatalogError('source_access_denied')
    if not permission.development or not as_utc(permission.confirmed_at) or as_utc(permission.confirmed_at)>price_time.utc_now():
        raise CatalogError('development_permission_required')
    public=audience!='development'
    if public and (not permission.public_display or audience=='public-commercial' and not permission.commercial):
        raise CatalogError('public_permission_required')
    plan=prepare_import(engine,file,schema_path,received_at=prepared.get('received_at'))
    if digest({k:v for k,v in prepared.items() if k!='plan_sha256'})!=prepared.get('plan_sha256'):
        raise CatalogError('invalid_prepared_plan')
    if source!=plan['source'] or any(plan[k]!=prepared.get(k) for k in
            ('file_sha256','schema_sha256','hardware_sha256','fixture','received_at')):
        raise CatalogError('prepared_input_changed')
    if analysis and load_schema(schema_path).input_adapter!='regard-native-v1':raise CatalogError('analysis_requires_regard_adapter')
    if plan['fixture'] and not fixture:raise CatalogError('fixture_requires_explicit_mode')
    if fixture and not plan['fixture']:raise CatalogError('real_data_cannot_use_fixture_mode')
    if plan['report']['rejected'] and not allow_rejected:raise CatalogError('preview_has_rejected_rows')
    receipt_key=digest([source,plan['file_sha256'],plan['schema_sha256'],plan['hardware_sha256'],
                        permission.model_dump(),audience,fixture,analysis])
    db=Session(engine)
    try:
        db.execute(text('BEGIN IMMEDIATE'))
        existing=db.get(CatalogImport,receipt_key)
        if existing:
            result=json.loads(existing.report);db.rollback()
            return {**result,'idempotent':True}
        if plan['plan_sha256']!=prepared['plan_sha256']:
            raise CatalogError('concurrent_catalog_change_repreview')
        if digest(source_snapshot(db,source))!=plan['source_sha256'] or digest(hardware_snapshot(db))!=plan['hardware_sha256']:
            raise CatalogError('concurrent_catalog_change_repreview')
        if analysis or import_schema.complete:
            old_keys=set(db.scalars(select(CatalogProduct.key).where(CatalogProduct.source==source)))
            new_keys={r['key'] for r in plan['rows']}
            if old_keys and len(new_keys)<len(old_keys)*.7 and not allow_shrink:raise CatalogError('suspicious_assortment_shrink')
        from app.services.catalog_history import check_dates,record_prices
        source_stamp=check_dates(db,plan) if import_schema.input_adapter=='regard-native-v1' else None
        access=db.get(CatalogAccess,source) or CatalogAccess(source=source)
        access.rights=canonical(permission.model_dump());access.public_enabled=int(public);access.fixture=int(fixture)
        db.add(access)
        now=price_time.db_now()
        report={**plan['report'],'source':source,'import_key':receipt_key,'file_sha256':plan['file_sha256'],'schema_sha256':plan['schema_sha256'],'schema_version':import_schema.version,'published':0,'materialized_offers':0,'idempotent':False}
        for raw in plan['rows']:
            row={k:v for k,v in raw.items() if k!='row_number'}
            item=db.get(CatalogProduct,row['key'])
            previous=item.payload if item else None
            item=item or CatalogProduct(key=row['key'],source=source,external_key=row['external_key'])
            if previous!=canonical(row):
                db.add(CatalogObservation(product_key=row['key'],import_key=receipt_key,payload=canonical(row) if previous is None else canonical({'event':'updated','changed':{k:row.get(k) for k in row if json.loads(previous).get(k)!=row.get(k)}}),imported_at=now))
            item.payload=canonical(row)
            if ((row['eligible'] or row.get('preliminary_eligible')) and (public or fixture)) or (analysis and row.get('analysis_eligible')):
                product_url=row['product_url'] or '/?tab=search&catalog_source=regard&product_id='+row['external_product_id']
                offer=db.get(StoreOffer,item.offer_id) if item.offer_id else None
                by_url=db.scalar(select(StoreOffer).where(StoreOffer.url==product_url))
                if by_url and (offer is None or by_url.id!=offer.id):raise CatalogError('existing_url_conflict')
                offer=offer or StoreOffer(url=product_url)
                # Never overwrite a later page observation with an older catalogue.
                if offer.observed_at and as_utc(offer.observed_at)>as_utc(row['source_updated_at']):
                    raise CatalogError('older_than_current_offer')
                metadata={'catalog_import':{'source_updated_at':row['source_updated_at'],'received_at':plan['received_at'],
                    'file_sha256':plan['file_sha256'],'schema_version':import_schema.version,'analysis_only':analysis,'internal_reference':not bool(row['product_url']),
                    'imported_at':iso_utc(now),'price_exact':row['price'],'availability':row['availability'],
                    'availability_warning':'Наличие не указано в прайс-листе' if row['availability']=='unknown' else None,
                    'product_url_origin':row.get('product_url_origin'),
                    'product_key':row['key'],'external_product_id':row.get('external_product_id'),'external_key':row['external_key'],'schema_sha256':plan['schema_sha256'],'fixture':fixture},
                    **row['attributes'],'raw_title':row['title'],'normalized_title':row['normalized_title'],
                    'catalog_product':{k:row.get(k) for k in
                        ('sku','vendor_code','brand','model','description','image_url','quantity')}}
                if offer.id:
                    old=json.loads(offer.attributes or '{}')
                    if (offer.price_rub==int(Decimal(row['price'])) and current_same_date(offer,row)
                            and offer.url==product_url and offer.name==row['normalized_title']
                            and offer.hardware_id==row['hardware_id'] and offer.category==row['category']
                            and offer.condition=='new'):
                        # Keep an existing genuine card check only for the exact same observation/price.
                        if 'price_verification' in old:metadata['price_verification']=old['price_verification']
                        if 'last_verified_price' in old:metadata['last_verified_price']=old['last_verified_price']
                offer.url=product_url
                offer.source=source;offer.name=row['normalized_title'];offer.category=row['category']
                offer.price_rub=int(Decimal(row['price']));offer.condition='new';offer.hardware_id=row['hardware_id']
                offer.observed_at=as_naive_utc(row['source_updated_at']);offer.origin='catalog_import'
                offer.attributes=canonical(metadata)
                db.add(offer);db.flush();item.offer_id=offer.id;report['materialized_offers']+=1
                if public and not fixture:report['published']+=1
            db.add(item);db.flush()
        if analysis or import_schema.complete:
            for missing in db.scalars(select(CatalogProduct).where(CatalogProduct.source==source,CatalogProduct.key.not_in(new_keys))):
                payload=json.loads(missing.payload)
                if not payload.get('missing_from_feed'):
                    payload['missing_from_feed']=True;missing.payload=canonical(payload)
                    db.add(CatalogObservation(product_key=missing.key,import_key=receipt_key,payload=canonical({"event":"missing","changed":{"missing_from_feed":True}}),imported_at=now))
        db.add(CatalogImport(key=receipt_key,source=source,created_at=now,report=canonical(report)))
        if source_stamp:
            report['source_updated_at']=source_stamp
            staged=report.pop('staged',[])
            report['staged_count']=len(staged);report['staged_sample']=staged[:20]
            record_prices(db,plan,receipt_key,import_schema.source_utc_offset_minutes,source_stamp)
            db.get(CatalogImport,receipt_key).report=canonical(report)
        db.commit();return report
    except Exception:
        db.rollback();raise
    finally:db.close()

def current_same_date(offer,row):
    return as_utc(offer.observed_at)==as_utc(row['source_updated_at'])

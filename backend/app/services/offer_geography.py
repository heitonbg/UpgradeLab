"""One request scope for search, full builds and upgrades; never infer geography."""
import json
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from app.core.price_time import is_fresh
from app.schemas.geography import GeoQuery,GeoEvidence
_scope=ContextVar('offer_query_scope',default=None)

@contextmanager
def offer_scope(payload):
    token=_scope.set(payload)
    try:yield
    finally:_scope.reset(token)

def query_scope():return _scope.get()

def evidence(row):
    try:return GeoEvidence.model_validate(json.loads(row.attributes).get('geography',{}))
    except (ValueError,TypeError):return GeoEvidence()

def geo_details(row,payload=None):
    payload=payload or query_scope() or GeoQuery()
    g=evidence(row);fresh=g.checked_at is not None and is_fresh(g.checked_at,timedelta(hours=24))
    local=bool(payload.city_id and g.city_id==payload.city_id and fresh and g.basis and (
        g.location_kind=='seller_declared' and g.availability=='seller_declared' or
        g.location_kind=='store_stock' and g.availability=='in_stock'))
    delivery=g.delivery
    deliver=bool(payload.city_id and delivery and (payload.city_id in delivery.city_ids or delivery.mode=='russia') and delivery.mode in ('cities','russia') and
                 is_fresh(delivery.checked_at,timedelta(hours=24)))
    return {'city_id':g.city_id,'target_city_id':payload.city_id,'location_status':g.location_kind if g.city_id and fresh and g.basis else 'location_unknown',
        'availability_status':g.availability if fresh else 'unknown',
        'local_match':local,'delivery_status':delivery.kind if deliver else 'unknown',
        'delivery_cost_rub':0 if local else delivery.cost_rub if deliver else None,
        'delivery_match':deliver,'delivery_cost_unknown':bool(not local and (not deliver or delivery.cost_rub is None))}

def filter_geography(rows,payload=None):
    payload=payload or query_scope() or GeoQuery()
    result=[]
    for row in rows:
        if getattr(payload,'condition','any')!='any' and row.condition!=payload.condition:continue
        g=geo_details(row,payload)
        if g['availability_status']=='unavailable':continue
        if payload.geo_mode=='local' and not g['local_match']:continue
        if payload.geo_mode=='delivery' and not (g['local_match'] or g['delivery_match']):continue
        if payload.max_price is not None and row.price_rub>payload.max_price:continue
        result.append(row)
    return result

def costed(row):
    payload=query_scope()
    if payload is None or payload.geo_mode!='delivery':return row
    g=geo_details(row,payload);fee=g['delivery_cost_rub']
    if fee is None or fee==0:return row
    data={c.name:getattr(row,c.name) for c in row.__table__.columns} if hasattr(row,'__table__') else vars(row).copy()
    attrs=json.loads(row.attributes);attrs['_costed_goods_price']=row.price_rub;attrs['_costed_delivery']=fee
    data.update(price_rub=row.price_rub+fee,attributes=json.dumps(attrs,ensure_ascii=False))
    return SimpleNamespace(**data)

def financial_evidence(result,db,payload):
    from app.db.models import StoreOffer,Hardware
    variants=[result,*result.get('alternatives',[])]
    for variant in variants:
        variant.setdefault('purchase_ready',False)
        unknown=False;seller=False
        technical=[]
        for part in variant.get('parts',[]):
            row=db.get(StoreOffer,part.get('offer_id')) if part.get('offer_id') else None
            if row is None:continue
            g=geo_details(row,payload);seller|=row.source=='upgradelab';unknown|=not g['local_match'] and (payload.geo_mode!='delivery' or g['delivery_cost_unknown'])
            part.update(geography=g,price_origin=row.origin,listing_fingerprint=json.loads(row.attributes).get('listing_fingerprint'),goods_price_rub=row.price_rub,
                        delivery_cost_rub=g['delivery_cost_rub'] if payload.geo_mode in ('local','delivery') else None)
            if row.source=='upgradelab':part.update(price_status='seller_declared',price_verified_at=None)
        parts_by_type={p.get('type'):p for p in variant.get('parts',[])}
        from app.services.technical_evidence import storage_status,psu_status
        board_part=parts_by_type.get('motherboard',{});drive_part=parts_by_type.get('storage',{});supply_part=parts_by_type.get('psu',{})
        board=db.get(StoreOffer,board_part.get('offer_id')) if board_part.get('offer_id') else None
        drive=db.get(StoreOffer,drive_part.get('offer_id')) if drive_part.get('offer_id') else None
        supply=db.get(StoreOffer,supply_part.get('offer_id')) if supply_part.get('offer_id') else None
        if board and drive:
            evidence=storage_status(board,drive);drive_part['compatibility']=evidence;technical.append(evidence)
        if supply:
            cpu=db.get(Hardware,parts_by_type.get('CPU',{}).get('id')) if parts_by_type.get('CPU',{}).get('id') else None
            gpu=db.get(Hardware,parts_by_type.get('GPU',{}).get('id')) if parts_by_type.get('GPU',{}).get('id') else None
            evidence=psu_status(supply,cpu,gpu);supply_part['compatibility']=evidence;technical.append(evidence)
        from app.services.physical_fit import physical_fit
        gpu_part=parts_by_type.get('GPU',{});case_part=parts_by_type.get('case',{});cooler_part=parts_by_type.get('cooler',{})
        physical_rows=[db.get(StoreOffer,p['offer_id']) if p.get('offer_id') else None for p in (gpu_part,case_part,cooler_part)]
        physical=physical_fit(board,physical_rows[0],physical_rows[1],supply,physical_rows[2])
        variant['physical_compatibility']=physical
        technical.append(physical)
        variant['compatibility_status']='incompatible' if any(e['status']=='incompatible' for e in technical) else 'unknown' if any(e['status']=='unknown' for e in technical) else 'compatible' if technical else 'unknown'
        if variant['compatibility_status']!='compatible':
            variant['purchase_ready']=False
        variant['delivery_cost_unknown']=unknown
        variant['total_includes_known_delivery']=payload.geo_mode=='delivery'
        variant['technical_compatibility_confirmed']=variant['compatibility_status']=='compatible'
        variant['financial_scope']='goods_and_known_delivery' if payload.geo_mode=='delivery' else 'goods_only'
        warnings=[]
        if unknown:warnings.append('Стоимость доставки неизвестна; итог покупки не подтверждён.')
        if variant['compatibility_status']!='compatible':warnings.append('Недостаточно технических характеристик для гарантии совместимости.')
        if seller:warnings.append('Цена и наличие частного продавца являются его заявлением.')
        if warnings:variant['price_note']=' '.join(warnings)
        variant['payable_total_rub']=variant.get('total_price') if variant.get('purchase_ready') else None
        if unknown:
            variant['purchase_ready']=False
            variant['payable_total_rub']=None
        variant.setdefault('status','draft' if len(variant.get('parts',[]))==8 else 'partial')
        variant['prices_confirmed']=variant.get('status')=='complete' and not seller
        if variant.get('status')=='complete' and (seller or unknown or variant['compatibility_status']!='compatible'):
            variant.update(status='draft',purchase_ready=False)
        if not variant.get('purchase_ready'):variant['payable_total_rub']=None
    if result.get('search_report'):
        result['search_report']['result_mode']=result.get('status')
    return result

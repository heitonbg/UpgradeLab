"""Read-only planning inventory. Historic observations are never live offers.

The existing technical solver is reused within a request-local inventory scope.
No reference row is inserted into SQLite or refreshed with a fake timestamp.
"""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace
from sqlalchemy import select
from fastapi import HTTPException
from app.db.models import StoreOffer,Hardware,HardwarePrice
from app.core.price_time import past_utc,iso_utc
_inventory=ContextVar('planning_inventory',default=None)
_mode=ContextVar('planning_price_mode',default=None)
def price_mode():return _mode.get()
@contextmanager
def price_mode_scope(mode):
    token=_mode.set(mode)
    try:yield
    finally:_mode.reset(token)

def scoped_inventory():return _inventory.get()

@contextmanager
def inventory_scope(rows):
    token=_inventory.set(rows)
    try:yield
    finally:_inventory.reset(token)

def reference_inventory(db):
    from app.services.catalog_access import filter_catalog
    from app.services.offer_safety import safe_offers
    hardware={h.id:h for h in db.scalars(select(Hardware))}
    public=filter_catalog(db,list(db.scalars(select(StoreOffer))))
    rows=safe_offers(public,hardware)
    result=[]
    for row in rows:
        data=json.loads(row.attributes)
        if not past_utc(row.observed_at) or data.get('optimizer_eligible') is False:continue
        data.pop('price_verification',None);data.pop('last_verified_price',None)
        data.update(reference_basis={'source':row.source,'observed_at':iso_utc(row.observed_at),'url':row.url,'offer_id':row.id,'price':row.price_rub,'listing_fingerprint':data.get('listing_fingerprint')})
        result.append(SimpleNamespace(id=-len(result)-1,source='reference',name=row.name,category=row.category,
            price_rub=row.price_rub,hardware_id=row.hardware_id,observed_at=row.observed_at,
            condition=row.condition,url=row.url,origin='reference',attributes=json.dumps(data)))
    for quote in db.scalars(select(HardwarePrice)):
        hw=hardware.get(quote.hardware_id)
        if quote.source not in ('passmark','avito_snapshot') or not hw or hw.type not in ('CPU','GPU') or quote.price_rub<=0 or not past_utc(quote.observed_at):continue
        # These public price snapshots already belong to Hardware. They provide
        # planning prices, never evidence of today's stock or local delivery.
        result.append(SimpleNamespace(id=-len(result)-1,source='reference',name=hw.name,category=hw.type,
            price_rub=quote.price_rub,hardware_id=hw.id,observed_at=quote.observed_at,
            condition='used' if quote.market=='used_ru' else 'new',url=quote.source_url,origin='reference',attributes=json.dumps({
                'reference_basis':{'source':quote.source,'observed_at':iso_utc(quote.observed_at),'url':quote.source_url}})))
    from app.services.offer_geography import query_scope
    condition=getattr(query_scope(),'condition','any')
    return [r for r in result if condition=='any' or r.condition==condition]

def planning_build(payload,db):
    from app.services.offers import available_offers
    from app.services.adaptive_builds import solve_profiles
    reference=reference_inventory(db)
    real=available_offers(db,payload.price_sources) if payload.pricing_mode=='hybrid' else []
    from app.services.automatic_builds import board_matches,memory_matches
    from app.services.component_quality import quality_check
    from app.services.adaptive_builds import platform_candidates
    profiles=platform_candidates(payload)
    def technically_eligible(row):
        if row.category=='motherboard':return any(board_matches(row,p) for p in profiles)
        if row.category=='memory':return any(memory_matches(row,p) for p in profiles)
        if row.category in ('psu','cooler','storage'):return quality_check(row,payload.socket)[0] is not None
        return True
    real=[r for r in real if technically_eligible(r)]
    present={r.category for r in real}
    rows=[*real,*[r for r in reference if r.category not in present]]
    missing=set(('CPU','GPU','motherboard','memory','storage','psu','case','cooler'))-{r.category for r in rows}
    if missing:raise HTTPException(400,'Недостаточно исходных цен для полной сборки: '+', '.join(sorted(missing))+'. Справочные цены не выдумываются; загрузите разрешённые данные или укажите детали вручную.')
    expanded=[*real,*reference]
    try:
        with inventory_scope(rows):
            result=solve_profiles(payload,db,{r.id for r in rows},observed=True)
    except HTTPException as error:
        if payload.pricing_mode!='hybrid' or error.status_code!=400:raise
        with inventory_scope(expanded):
            result=solve_profiles(payload,db,{r.id for r in expanded},observed=True)
    else:
        if payload.pricing_mode=='hybrid':
            try:
                with inventory_scope(expanded):
                    comparison=solve_profiles(payload,db,{r.id for r in expanded},observed=True)
            except HTTPException as error:
                if error.status_code!=400:raise
            else:
                candidates=[comparison,*comparison.get('alternatives',[])]
                score=lambda v:v.get('selection_score',v.get('fps',0))
                best=max(candidates,key=lambda v:(score(v),-v['total_price']))
                identity=lambda v:tuple((p.get('type'),p.get('id'),p.get('offer_id')) for p in v.get('parts',[]))
                if (score(best)>score(result) or
                    (score(best)==score(result) and best['total_price']<result['total_price'])) and identity(best)!=identity(result):
                    best={**{k:v for k,v in best.items() if k!='alternatives'},'variant_key':'hybrid_comparison','title':'Альтернатива со справочными ценами',
                          'summary':'Более выгодный расчёт; справочные цены и наличие требуют проверки.'}
                    existing=[v for v in result.get('alternatives',[]) if identity(v) not in (identity(result),identity(best))]
                    primary={k:v for k,v in result.items() if k!='alternatives'}
                    result['alternatives']=[primary,best,*existing][:3]
    reference_by_id={r.id:r for r in expanded if r.source=='reference'}
    for variant in [result,*result.get('alternatives',[])]:
        used_reference=False
        for part in variant.get('parts',[]):
            row=reference_by_id.get(part.get('offer_id'))
            if row is None:continue
            used_reference=True
            part.update(offer_id=None,price_basis='reference',price_origin='reference',price_status='reference',
                price_trust='reference_estimate',price_source='Справочная оценка',price_verified_at=None,price_observed_at=iso_utc(row.observed_at),
                reference_basis=json.loads(row.attributes)['reference_basis'],
                purchase_warning=(part.get('purchase_warning','')+' Справочная цена из прошлого наблюдения; наличие и текущая стоимость не подтверждены.').strip())
        variant.update(pricing_mode=payload.pricing_mode,status='draft',purchase_ready=False,prices_confirmed=False,
            price_note='Справочный расчёт по исходным наблюдениям. Наличие, доставка и текущая стоимость справочных позиций не подтверждены.' if used_reference else 'Предварительные реальные предложения; перед покупкой требуется повторная проверка.')
    return result

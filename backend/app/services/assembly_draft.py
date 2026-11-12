"""A compatible estimate from real observations when live shops are unavailable."""
import json
from app.core.price_time import past_utc, iso_utc
from fastapi import HTTPException
from app.services.adaptive_builds import solve_profiles
from app.services.offers import available_offers
from app.services.component_quality import quality_check


def quote_evidence(row):
    data=json.loads(row.attributes)
    verification=data.get('price_verification',{})
    history=data.get('last_verified_price',{})
    raw=verification.get('checked_at') if verification.get('status')=='verified' else history.get('checked_at')
    checked=past_utc(raw)
    # Only genuinely legacy rows without explicit verification/history metadata
    # can use the page-read timestamp. Malformed/future metadata is not evidence.
    if not verification and not history and row.origin=='product_page':
        checked=past_utc(row.observed_at)
    from app.services.catalog_freshness import catalog_price_state
    catalog = catalog_price_state(row.observed_at) if row.origin == 'catalog_import' else {}
    return {**catalog, 'price_status':'previously_verified' if checked is not None else 'catalog_import' if row.origin=='catalog_import' else 'unconfirmed',
            'price_last_verified_at':iso_utc(checked),
            'price_observed_at':iso_utc(row.observed_at),
            'price_verified_at':None,
            'imported_at':data.get('catalog_import',{}).get('imported_at'),
            'stock_status':data.get('catalog_import',{}).get('availability','unknown')}


def observed_rows(db,sources):
    # Keep all model, condition and fraud filters. Only live confirmation is
    # relaxed, visibly, and only for observations younger than 24 hours.
    return [row for row in available_offers(db,sources,include_unavailable=True)
            if row.origin=='feed' or row.price_rub>300]


def draft_build(payload,db,preferred_source=None):
    rows=observed_rows(db,payload.price_sources)
    lookup={row.id:row for row in rows}
    historical={row.id for row in rows if row.origin in ('product_page','feed') or
                json.loads(row.attributes).get('last_verified_price')}
    def model_key(row):
        if row.category not in ('storage','psu','cooler'):return None
        quality=quality_check(row,payload.socket)[0]
        return (row.category,quality['model'],quality.get('capacity_gb')) if quality else None
    known_models={key for row in rows if row.id in historical for key in [model_key(row)] if key}
    # Do not reintroduce a dubious search price for a cooler/PSU/SSD when a
    # successful page observation of that same model is already available.
    eligible={row.id for row in rows if row.id in historical or row.source==preferred_source or
              model_key(row) not in known_models}
    reliable_categories={row.category for row in rows if row.id in historical}
    preferred_and_reliable={row.id for row in rows if row.id in eligible and (row.id in historical or
                            row.source==preferred_source or row.category not in reliable_categories)}
    pools=[preferred_and_reliable,historical,eligible]
    for ids in pools:
        if not ids:continue
        try:
            result=solve_profiles(payload,db,ids,preferred_source=preferred_source,observed=True)
        except HTTPException as error:
            if error.status_code!=400:raise
            continue
        for variant in [result,*result.get('alternatives',[])]:
            variant['status']='draft'
            variant['purchase_ready']=False
            variant['price_note']='Предварительный расчёт по последним полученным предложениям. Текущие цены и наличие не подтверждены; итог покупки может отличаться.'
            for item in variant['parts']:
                row=lookup.get(item.get('offer_id'))
                if row:item.update(quote_evidence(row))
        return result
    return None

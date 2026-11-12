"""Compact, source-dated 14-calendar-day price history, never saved-build history."""
import json
from datetime import timedelta,timezone
from decimal import Decimal
from sqlalchemy import select,delete
from fastapi import HTTPException
from app.core import price_time
from app.core.price_time import as_utc
from app.db.models import CatalogDailyPrice,CatalogPriceCorrection,CatalogProduct,CatalogImport,CatalogAccess
from app.services.catalog_files import CatalogError

def source_day(stamp,offset):
    value=as_utc(stamp)
    if value is None:raise CatalogError('missing_source_date')
    return value.astimezone(timezone(timedelta(minutes=offset))).date().isoformat()

def check_dates(db,plan):
    dates=[as_utc(r['source_updated_at']) for r in plan['rows']]
    if not dates or any(d is None for d in dates):raise CatalogError('missing_source_date')
    if len(set(dates))!=1:raise CatalogError('mixed_source_dates')
    for receipt in db.scalars(select(CatalogImport).where(CatalogImport.source==plan['source'])):
        previous=json.loads(receipt.report).get('source_updated_at')
        if previous and min(dates)<as_utc(previous):raise CatalogError('older_than_last_success')
    return min(dates).isoformat()

def record_prices(db,plan,import_key,offset,stamp):
    cutoff=(price_time.utc_now().astimezone(timezone(timedelta(minutes=offset))).date()-timedelta(days=13)).isoformat()
    from sqlalchemy.dialects.sqlite import insert
    existing={(key,day):(price,receipt) for key,day,price,receipt in db.execute(select(CatalogDailyPrice.product_key,CatalogDailyPrice.source_day,CatalogDailyPrice.price_kopecks,CatalogDailyPrice.import_key).where(CatalogDailyPrice.source==plan['source']))}
    prices=[];corrections=[]
    for row in plan['rows']:
        day=source_day(row['source_updated_at'],offset)
        if day<cutoff:continue
        price=Decimal(row['price'])*100
        if price!=price.to_integral_value():raise CatalogError('fractional_kopeck')
        previous=existing.get((row['key'],day))
        if previous and previous[0]!=int(price):corrections.append(dict(product_key=row['key'],source_day=day,previous_price_kopecks=previous[0],previous_import_key=previous[1],import_key=import_key))
        prices.append(dict(product_key=row['key'],source_day=day,source=plan['source'],price_kopecks=int(price),import_key=import_key))
    db.flush()
    for index in range(0,len(prices),100):
        statement=insert(CatalogDailyPrice).values(prices[index:index+100])
        db.execute(statement.on_conflict_do_update(index_elements=['product_key','source_day'],set_={'price_kopecks':statement.excluded.price_kopecks,'import_key':statement.excluded.import_key}))
    if corrections:db.execute(insert(CatalogPriceCorrection),corrections)
    db.execute(delete(CatalogDailyPrice).where(CatalogDailyPrice.source==plan['source'],CatalogDailyPrice.source_day<cutoff))
    keys=select(CatalogProduct.key).where(CatalogProduct.source==plan['source'])
    db.execute(delete(CatalogPriceCorrection).where(CatalogPriceCorrection.product_key.in_(keys),CatalogPriceCorrection.source_day<cutoff))
    # SavedBuild JSON and legacy audit records remain intact.

def price_history(db,key,days=7):
    if days not in (7,14):raise HTTPException(422,'Допустимы 7 или 14 дней')
    item=db.get(CatalogProduct,key)
    access=db.get(CatalogAccess,item.source) if item else None
    from app.services.catalog_access import validated_rights
    rights=validated_rights(access) if access else None
    if not item or not access or not access.public_enabled or access.fixture or not rights or not rights.public_display:raise HTTPException(404,'История недоступна')
    # Regard source calendar explicitly uses the operator-configured timezone.
    from app.core.config import settings
    today=price_time.utc_now().astimezone(timezone(timedelta(minutes=settings.regard_source_utc_offset_minutes))).date()
    cutoff=(today-timedelta(days=days-1)).isoformat()
    rows=list(db.scalars(select(CatalogDailyPrice).where(CatalogDailyPrice.product_key==key,CatalogDailyPrice.source_day>=cutoff).order_by(CatalogDailyPrice.source_day)))
    values=[r.price_kopecks for r in rows]
    return {'product_id':key,'source':item.source,'days':days,'observations':[{'date':r.source_day,'price_rub':r.price_kopecks/100,'sync_id':r.import_key} for r in rows],
        'minimum':min(values)/100 if values else None,'maximum':max(values)/100 if values else None,
        'mean':sum(values)/len(values)/100 if values else None,'change_rub':(values[-1]-values[0])/100 if len(values)>1 else None,
        'last_source_day':rows[-1].source_day if rows else None,'note':'Наблюдения прайса; текущая цена и наличие не подтверждены.'}

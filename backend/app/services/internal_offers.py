"""SQLite adapter for active, owner-linked catalogue listings. No HTTP or invented models."""
import json
from types import SimpleNamespace
from sqlalchemy import select
from fastapi import HTTPException
from app.db.models import Listing,ListingOwner,User,Hardware,StoreOffer,ListingDelivery
from app.core.price_time import iso_utc,as_naive_utc
from app.services.listing_validation import validate_model,seller_availability

def valid_listing(db,listing):
    if not listing or listing.listing_type!='sale' or listing.condition=='Неисправное' or seller_availability(listing)!='seller_declared':return None
    owner=db.get(ListingOwner,listing.id)
    if not owner or not db.get(User,owner.user_id):return None
    if listing.category not in ('CPU','GPU','memory','motherboard','storage','psu','case','cooler'):return None
    from app.services.store_providers import money
    try:price=money(listing.price)
    except ValueError:return None
    if not 0<price<=100000000:return None
    return owner,price

def live_internal(db,row):
    if row.source!='upgradelab':return True
    try:
        ident=json.loads(row.attributes)['listing_id'];listing=db.get(Listing,ident)
        info=valid_listing(db,listing)
        if not info:return False
        if row.condition!=('new' if listing.condition=='Новое' else 'used'):return False
        from app.services.listing_specs import assess_listing
        assessment=assess_listing(db,listing)
        stored=json.loads(row.attributes)
        if stored.get('listing_fingerprint')!=assessment['fingerprint']:return False
        if stored.get('optimizer_eligible') and not assessment['assessment']['optimizer_eligible']:return False
        if json.loads(row.attributes).get('seller_specs',{})!=listing.characteristics:return False
        delivery=db.get(ListingDelivery,ident)
        declared=json.loads(delivery.evidence) if delivery else None
        if json.loads(row.attributes).get('geography',{}).get('delivery')!=declared:return False
        return bool(info and listing.title==row.name and info[1]==json.loads(row.attributes).get('_costed_goods_price',row.price_rub) and listing.hardware_id==row.hardware_id
            and listing.category==row.category and json.loads(row.attributes).get('geography',{}).get('city_id')==listing.city_id
            and json.loads(row.attributes).get('seller_confirmed_at')==iso_utc(listing.availability_confirmed_at))
    except (ValueError,TypeError,KeyError):return False

def sync_internal(db):
    listings=list(db.scalars(select(Listing).join(ListingOwner).join(User,ListingOwner.user_id==User.id).where(
        Listing.publication_status=='active')))
    existing={row.url:row for row in db.scalars(select(StoreOffer).where(StoreOffer.source=='upgradelab'))}
    changed=False
    for listing in listings:
        info=valid_listing(db,listing)
        if not info:continue
        owner,price=info;url=f'/?tab=marketplace&listing={listing.id}'
        row=existing.get(url) or StoreOffer(source='upgradelab',url=url)
        geography={'city_id':listing.city_id,'location_kind':'seller_declared','availability':'seller_declared',
            'checked_at':iso_utc(listing.availability_confirmed_at),'basis':'Продавец подтвердил наличие объявления'}
        delivery=db.get(ListingDelivery,listing.id)
        if delivery:
            try:geography['delivery']=json.loads(delivery.evidence)
            except ValueError:pass
        from app.services.listing_specs import assess_listing
        technical=assess_listing(db,listing)
        if technical['assessment']['state']=='contradictory':continue
        attrs={**technical['attributes'],'technical_assessment':technical['assessment'],'optimizer_eligible':technical['assessment']['optimizer_eligible'],
            'listing_fingerprint':technical['fingerprint'],'seller_specs':listing.characteristics,'listing_id':listing.id,'seller_id':owner.user_id,'seller_name':db.get(User,owner.user_id).name,
            'created_at':iso_utc(listing.created_at),'updated_at':iso_utc(listing.updated_at),
            'seller_confirmed_at':iso_utc(listing.availability_confirmed_at),'geography':geography,
            'description':listing.description or ''}
        row.name=listing.title;row.category=listing.category;row.price_rub=price
        row.condition='new' if listing.condition=='Новое' else 'used';row.hardware_id=listing.hardware_id
        row.observed_at=as_naive_utc(listing.updated_at or listing.created_at);row.origin='seller_declared'
        row.attributes=json.dumps(attrs,ensure_ascii=False);db.add(row)
        changed=changed or row.id is None or db.is_modified(row,include_collections=False)
    db.flush()
    return changed

"""Cached jobs are not an authorization bypass or a stale listing catalogue."""
import json,hashlib
from sqlalchemy import select
from app.db.models import Listing,ListingOwner,ListingDelivery,ListingDetails,CatalogAccess,StoreOffer

def listing_revision(db):
    data=[tuple(row) for row in db.execute(select(Listing.id,Listing.title,Listing.price,Listing.city_id,
        Listing.hardware_id,Listing.category,Listing.condition,Listing.publication_status,Listing.updated_at,Listing.availability_confirmed_at))]
    data.extend(tuple(row) for row in db.execute(select(ListingOwner.listing_id,ListingOwner.user_id)))
    data.extend(tuple(row) for row in db.execute(select(CatalogAccess.source,CatalogAccess.rights,CatalogAccess.public_enabled)))
    data.extend(tuple(row) for row in db.execute(select(ListingDelivery.listing_id,ListingDelivery.evidence)))
    data.extend(tuple(row) for row in db.execute(select(ListingDetails.listing_id,ListingDetails.data)))
    return hashlib.sha256(json.dumps(data,default=str,sort_keys=True).encode()).hexdigest()

def current_result(db,value):
    from app.services.catalog_access import filter_catalog
    if isinstance(value,list):return all(current_result(db,v) for v in value)
    if not isinstance(value,dict):return True
    ident=value.get('offer_id')
    if isinstance(ident,int):
        row=db.get(StoreOffer,ident)
        if row is None or not filter_catalog(db,[row]):return False
        if row.source=='upgradelab':
            attrs=json.loads(row.attributes)
            if not attrs.get('optimizer_eligible',True):return False
            if value.get('listing_fingerprint') and value['listing_fingerprint']!=attrs.get('listing_fingerprint'):return False
            listing=db.get(Listing,json.loads(row.attributes).get('listing_id'))
            if listing is None or str(listing.price)!=str(row.price_rub):return False
            snapshot_price=value.get('goods_price_rub',value.get('price',value.get('avg_price')))
            if snapshot_price is not None and snapshot_price!=row.price_rub:return False
            geography=value.get('geography',{})
            if geography.get('delivery_match') and not geography.get('local_match'):
                actual=json.loads(row.attributes).get('geography',{}).get('delivery',{})
                if actual.get('cost_rub')!=geography.get('delivery_cost_rub') or (geography.get('target_city_id') not in actual.get('city_ids',[]) and actual.get('mode')!='russia'):return False
    return all(current_result(db,v) for v in value.values() if isinstance(v,(dict,list)))

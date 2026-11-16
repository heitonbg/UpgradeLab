"""Cached jobs are not an authorization bypass or a stale listing catalogue."""
import json,hashlib
from sqlalchemy import select
from app.db.models import Listing,ListingOwner,ListingDelivery,ListingDetails,CatalogAccess,StoreOffer,Hardware,User

def listing_revision(db):
    data=[tuple(row) for row in db.execute(select(Listing.id,Listing.title,Listing.price,Listing.city_id,
        Listing.hardware_id,Listing.category,Listing.condition,Listing.publication_status,Listing.updated_at,Listing.availability_confirmed_at))]
    data.extend(tuple(row) for row in db.execute(select(ListingOwner.listing_id,ListingOwner.user_id)))
    data.extend(tuple(row) for row in db.execute(select(CatalogAccess.source,CatalogAccess.rights,CatalogAccess.public_enabled)))
    data.extend(tuple(row) for row in db.execute(select(ListingDelivery.listing_id,ListingDelivery.evidence)))
    data.extend(tuple(row) for row in db.execute(select(ListingDetails.listing_id,ListingDetails.data)))
    return hashlib.sha256(json.dumps(data,default=str,sort_keys=True).encode()).hexdigest()

def current_result(db,value,offers=None,listings=None,catalog_states=None,owners=None,deliveries=None,users=None):
    from app.services.catalog_access import filter_catalog
    if isinstance(value,list):return all(current_result(db,v,offers,listings,catalog_states,owners,deliveries,users) for v in value)
    if not isinstance(value,dict):return True
    ident=value.get('offer_id')
    if isinstance(ident,int):
        row=offers.get(ident) if offers is not None else db.get(StoreOffer,ident)
        if row is None:return False
        if catalog_states is not None:
            from app.services.internal_offers import live_internal
            if not catalog_states.get(ident,row.origin!='catalog_import') or not live_internal(
                    db,row,listings=listings,owners=owners,deliveries=deliveries,users=users,
                    assessments=current_result._batch.get('assessments') if getattr(current_result,'_batch',None) else None,
                    reference_rows=current_result._batch.get('reference_rows') if getattr(current_result,'_batch',None) else None):return False
        elif not filter_catalog(db,[row]):return False
        if row.source=='upgradelab':
            attrs=json.loads(row.attributes)
            if not attrs.get('optimizer_eligible',True):return False
            if value.get('listing_fingerprint') and value['listing_fingerprint']!=attrs.get('listing_fingerprint'):return False
            listing_id=json.loads(row.attributes).get('listing_id')
            listing=listings.get(listing_id) if listings is not None else db.get(Listing,listing_id)
            if listing is None or str(listing.price)!=str(row.price_rub):return False
            snapshot_price=value.get('goods_price_rub',value.get('price',value.get('avg_price')))
            if snapshot_price is not None and snapshot_price!=row.price_rub:return False
            geography=value.get('geography',{})
            if geography.get('delivery_match') and not geography.get('local_match'):
                actual=json.loads(row.attributes).get('geography',{}).get('delivery',{})
                if actual.get('cost_rub')!=geography.get('delivery_cost_rub') or (geography.get('target_city_id') not in actual.get('city_ids',[]) and actual.get('mode')!='russia'):return False
    return all(current_result(db,v,offers,listings,catalog_states,owners,deliveries,users) for v in value.values() if isinstance(v,(dict,list)))


def current_result_many(db,values):
    """Revalidate all offer references with bounded SQL queries during polling."""
    from sqlalchemy import select
    from app.services.catalog_access import visible_catalog_ids
    offer_ids=set();listing_ids=set()
    def collect(value):
        if isinstance(value,list):
            for item in value:collect(item)
        elif isinstance(value,dict):
            ident=value.get('offer_id')
            if isinstance(ident,int):offer_ids.add(ident)
            for child in value.values():
                if isinstance(child,(dict,list)):collect(child)
    collect(values)
    if not offer_ids:return True
    offers={row.id:row for row in db.scalars(select(StoreOffer).where(StoreOffer.id.in_(offer_ids)))}
    listing_ids={json.loads(row.attributes).get('listing_id') for row in offers.values() if row.source=='upgradelab'}
    listing_ids.discard(None)
    listings={row.id:row for row in db.scalars(select(Listing).where(Listing.id.in_(listing_ids)))} if listing_ids else {}
    owners={row.listing_id:row for row in db.scalars(select(ListingOwner).where(ListingOwner.listing_id.in_(listing_ids)))} if listing_ids else {}
    deliveries={row.listing_id:row for row in db.scalars(select(ListingDelivery).where(ListingDelivery.listing_id.in_(listing_ids)))} if listing_ids else {}
    users=set(db.scalars(select(User.id).where(User.id.in_({owner.user_id for owner in owners.values()})))) if owners else set()
    states=visible_catalog_ids(db)
    from app.services.listing_specs import assess_listing
    hardware_ids={row.hardware_id for row in listings.values() if row.hardware_id is not None}
    hardware={row.id:row for row in db.scalars(select(Hardware).where(Hardware.id.in_(hardware_ids)))} if hardware_ids else {}
    from app.db.models import CatalogProduct
    reference_rows=list(db.scalars(select(StoreOffer).join(CatalogProduct,CatalogProduct.offer_id==StoreOffer.id)))
    assessments={ident:assess_listing(db,row,preloaded_refs=reference_rows,hardware_by_id=hardware) for ident,row in listings.items()}
    current_result._batch={'assessments':assessments,'reference_rows':reference_rows}
    try:return current_result(db,values,offers,listings,states,owners,deliveries,users)
    finally:current_result._batch=None

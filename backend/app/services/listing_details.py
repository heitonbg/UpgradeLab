"""Atomic seller details and safe public views."""
import json
from app.db.models import ListingDetails,ListingDelivery,ListingOwner,User
from app.core.price_time import db_now
from app.schemas.geography import DeliveryEvidence

def save_details(db,listing,specs):
    row=db.get(ListingDetails,listing.id) or ListingDetails(listing_id=listing.id)
    row.data=json.dumps(specs,ensure_ascii=False,sort_keys=True);db.add(row);listing.details=row

def save_delivery(db,listing,spec):
    row=db.get(ListingDelivery,listing.id)
    if row is not None and row in db.deleted:
        db.flush()
        row=None
    if spec is None:
        if row:db.delete(row)
        return
    evidence=DeliveryEvidence(**spec.model_dump(),checked_at=db_now(),kind='seller_declared',basis='Условия передачи заявлены продавцом')
    row=row or ListingDelivery(listing_id=listing.id);row.evidence=evidence.model_dump_json();db.add(row)

def delivery_view(db,listing):
    row=db.get(ListingDelivery,listing.id)
    if row:
        try:
            result=DeliveryEvidence.model_validate_json(row.evidence).model_dump(mode='json')
            from app.services.cities import city_name
            result['city_labels']={c:city_name(c) for c in result['city_ids']}
            result['cost_kind']='unknown' if result['cost_rub'] is None else 'free' if result['cost_rub']==0 else 'fixed'
            return result
        except ValueError:return None
    return None

def listing_view(db,listing):
    from app.services.listing_specs import assess_listing
    listing.delivery=delivery_view(db,listing);listing.technical_assessment=assess_listing(db,listing)['assessment']
    owner=db.get(ListingOwner,listing.id);person=db.get(User,owner.user_id) if owner else None
    listing.seller_name=person.name if person else None
    return listing

from fastapi import APIRouter, status, HTTPException, Response
from app.api.deps import DBSession
from app.api.account import AuthUser
from app.db.models import Listing, ListingOwner, ListingDelivery
from sqlalchemy import select
from app.crud import listing as listing_crud
from app.schemas.listing import ListingCreate, ListingOut, ListingUpdate
from app.services.listing_validation import validate_model
from app.core.price_time import db_now
from app.services.listing_details import listing_view,save_details,save_delivery

router = APIRouter(prefix="/api", tags=["listings"])


@router.get("/listings", response_model=list[ListingOut])
def get_listings(db: DBSession, city_id: str | None = None):
    from app.services.cities import BY_ID
    if city_id is not None and city_id not in BY_ID:
        raise HTTPException(422,"Неизвестный город")
    return [listing_view(db,row) for row in listing_crud.list_recent(db,city_id)]


@router.post("/listings", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
def create_listing(payload: ListingCreate, db: DBSession, user: AuthUser):
    if payload.city_id is None:
        raise HTTPException(422,"Для нового объявления выберите город из справочника")
    validate_model(db, payload)
    listing = listing_crud.create(db, payload)
    db.add(ListingOwner(listing_id=listing.id, user_id=user.id))
    save_details(db,listing,payload.characteristics)
    if payload.delivery is not None:save_delivery(db,listing,payload.delivery)
    db.commit()
    db.refresh(listing)
    return listing_view(db,listing)


@router.get("/my/listings", response_model=list[ListingOut])
def my_listings(db: DBSession, user: AuthUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return [listing_view(db,row) for row in db.scalars(select(Listing).join(ListingOwner).where(ListingOwner.user_id == user.id).order_by(Listing.id.desc()))]


@router.delete("/listings/{listing_id}", status_code=204)
def delete_listing(listing_id: int, db: DBSession, user: AuthUser):
    owner = db.get(ListingOwner, listing_id)
    if not owner or owner.user_id != user.id:
        raise HTTPException(404, "Объявление не найдено")
    listing = db.get(Listing, listing_id)
    delivery=db.get(ListingDelivery,listing_id)
    if delivery:db.delete(delivery)
    db.delete(owner)
    db.delete(listing)
    db.commit()


@router.get("/cities")
def cities(q: str = ""):
    from app.services.cities import search_cities
    if len(q)>100:
        raise HTTPException(422,"Слишком длинный запрос")
    return search_cities(q)


@router.patch("/listings/{listing_id}", response_model=ListingOut)
def update_listing(listing_id: int, payload: ListingUpdate, db: DBSession, user: AuthUser):
    owner = db.get(ListingOwner,listing_id)
    if not owner or owner.user_id != user.id:
        raise HTTPException(404,"Объявление не найдено")
    listing = db.get(Listing,listing_id)
    if not listing:
        raise HTTPException(404,"Объявление не найдено")
    changes=payload.model_dump(exclude_unset=True)
    merged={name:getattr(listing,name) for name in ListingCreate.model_fields if name not in ('confirm_availability','delivery')}
    if 'category' in changes and changes['category']!=listing.category:
        if 'characteristics' not in changes:merged['characteristics']={}
        if 'hardware_id' not in changes:merged['hardware_id']=None
    elif 'title' in changes and changes['title']!=listing.title and 'hardware_id' not in changes:merged['hardware_id']=None
    merged.update(changes)
    # Changing contact kind must be explicit; preserve old free-text contacts
    # when only description or photo is edited.
    if 'contact' in changes and 'contact_type' not in changes:
        merged['contact_type']=None
    from pydantic import ValidationError
    try:
        validated=ListingCreate.model_validate(merged)
    except ValidationError:
        raise HTTPException(422,"Проверьте поля объявления: город, контакт, фото и условия обмена") from None
    if listing.city_id is not None and validated.city_id is None:
        raise HTTPException(422,"Выберите город из справочника")
    validate_model(db,validated)
    material={'title','price','city_id','hardware_id','category','condition','publication_status','listing_type','characteristics'}
    if any(getattr(listing,key)!=value for key,value in changes.items() if key in material):
        listing.availability_confirmed_at=None
        delivery=db.get(ListingDelivery,listing_id)
        if delivery:db.delete(delivery)
    for name,value in validated.model_dump(exclude={'confirm_availability','characteristics','delivery'}).items():
        setattr(listing,name,value)
    if 'characteristics' in changes or 'category' in changes:save_details(db,listing,validated.characteristics)
    if 'delivery' in changes:save_delivery(db,listing,validated.delivery)
    listing.updated_at=db_now()
    if validated.confirm_availability and listing.publication_status=='active':
        listing.availability_confirmed_at=db_now()
    if listing.publication_status!='active':
        listing.availability_confirmed_at=None
    db.commit();db.refresh(listing)
    return listing_view(db,listing)


from app.schemas.listing_details import SellerDelivery as SellerDeliveryRequest

@router.put('/listings/{listing_id}/delivery')
def declare_delivery(listing_id:int,payload:SellerDeliveryRequest,db:DBSession,user:AuthUser):
    owner=db.get(ListingOwner,listing_id)
    if not owner or owner.user_id!=user.id:raise HTTPException(404,'Объявление не найдено')
    listing=db.get(Listing,listing_id)
    if listing is None:raise HTTPException(404,'Объявление не найдено')
    save_delivery(db,listing,payload);db.commit()
    from app.services.listing_details import delivery_view
    return delivery_view(db,listing)

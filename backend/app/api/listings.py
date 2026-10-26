from fastapi import APIRouter, status, HTTPException
from app.api.deps import DBSession
from app.api.account import AuthUser
from app.db.models import Listing, ListingOwner
from sqlalchemy import select
from app.crud import listing as listing_crud
from app.schemas.listing import ListingCreate, ListingOut

router = APIRouter(prefix="/api", tags=["listings"])


@router.get("/listings", response_model=list[ListingOut])
def get_listings(db: DBSession):
    return listing_crud.list_recent(db)


@router.post("/listings", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
def create_listing(payload: ListingCreate, db: DBSession, user: AuthUser):
    listing = listing_crud.create(db, payload)
    db.add(ListingOwner(listing_id=listing.id, user_id=user.id))
    db.commit()
    db.refresh(listing)
    return listing


@router.get("/my/listings", response_model=list[ListingOut])
def my_listings(db: DBSession, user: AuthUser):
    return list(db.scalars(select(Listing).join(ListingOwner).where(ListingOwner.user_id == user.id).order_by(Listing.id.desc())))


@router.delete("/listings/{listing_id}", status_code=204)
def delete_listing(listing_id: int, db: DBSession, user: AuthUser):
    owner = db.get(ListingOwner, listing_id)
    if not owner or owner.user_id != user.id:
        raise HTTPException(404, "Объявление не найдено")
    listing = db.get(Listing, listing_id)
    db.delete(owner)
    db.delete(listing)
    db.commit()

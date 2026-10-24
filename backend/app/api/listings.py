from fastapi import APIRouter, status
from app.api.deps import DBSession
from app.crud import listing as listing_crud
from app.schemas.listing import ListingCreate, ListingOut

router = APIRouter(prefix="/api", tags=["listings"])


@router.get("/listings", response_model=list[ListingOut])
def get_listings(db: DBSession):
    return listing_crud.list_recent(db)


@router.post("/listings", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
def create_listing(payload: ListingCreate, db: DBSession):
    return listing_crud.create(db, payload)
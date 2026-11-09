from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Listing
from app.schemas.listing import ListingCreate


def list_recent(db: Session, city_id=None) -> list[Listing]:
    stmt = select(Listing).where(Listing.publication_status == "active")
    if city_id is not None:
        stmt = stmt.where(Listing.city_id == city_id)
    stmt = stmt.order_by(Listing.created_at.desc(), Listing.id.desc())
    return list(db.scalars(stmt))


def create(db: Session, payload: ListingCreate) -> Listing:
    from app.core.price_time import db_now
    data = payload.model_dump(exclude={'confirm_availability'})
    listing = Listing(**data, created_at=db_now(), updated_at=db_now(),
        availability_confirmed_at=db_now() if payload.confirm_availability and payload.publication_status == 'active' else None)
    db.add(listing)
    db.flush()
    return listing

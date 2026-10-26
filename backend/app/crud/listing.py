from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Listing
from app.schemas.listing import ListingCreate


def list_recent(db: Session) -> list[Listing]:
    stmt = select(Listing).order_by(Listing.created_at.desc(), Listing.id.desc())
    return list(db.scalars(stmt))


def create(db: Session, payload: ListingCreate) -> Listing:
    listing = Listing(
        title=payload.title,
        condition=payload.condition,
        price=payload.price,
        contact=payload.contact,
        description=payload.description,
    )
    db.add(listing)
    db.flush()
    return listing

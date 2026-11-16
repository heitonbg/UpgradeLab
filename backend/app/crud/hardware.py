from sqlalchemy import select, not_
from sqlalchemy.orm import Session
from app.db.models import Hardware


def list_all(db: Session) -> list[Hardware]:
    stmt = (
        select(Hardware)
        .where(not_((Hardware.type == 'CPU') & Hardware.name.ilike('Apple M%')))
        .order_by(Hardware.type.asc(), Hardware.raw_score.desc(), Hardware.name.asc())
    )
    return list(db.scalars(stmt))


def get_by_id(db: Session, hw_id: int) -> Hardware | None:
    row = db.get(Hardware, hw_id)
    if row and row.type == 'CPU' and row.name.casefold().startswith('apple m'):
        return None
    return row

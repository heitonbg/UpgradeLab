from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Hardware


def list_all(db: Session) -> list[Hardware]:
    stmt = (
        select(Hardware)
        .order_by(Hardware.type.asc(), Hardware.normalized_score.desc())
    )
    return list(db.scalars(stmt))


def get_by_id(db: Session, hw_id: int) -> Hardware | None:
    return db.get(Hardware, hw_id)
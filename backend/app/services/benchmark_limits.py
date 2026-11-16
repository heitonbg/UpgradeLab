"""Atomic bounded account quotas, with retention independent of login quotas."""
import math
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import case,delete,or_,select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import OperationalError
from app.core.price_time import db_now
from app.db.models import BenchmarkQuota

def enforce(db,user_id,scope,maximum,seconds):
    now=db_now();key=f'{scope}:{user_id}';table=BenchmarkQuota
    expired=or_(table.started_at<=now-timedelta(seconds=seconds),table.started_at>now)
    statement=insert(table).values(key=key,started_at=now,attempts=1)
    statement=statement.on_conflict_do_update(index_elements=[table.key],
        set_={'started_at':case((expired,now),else_=table.started_at),'attempts':case((expired,1),else_=table.attempts+1)},
        where=or_(expired,table.attempts<maximum)).returning(table.attempts)
    try:
        db.execute(delete(table).where(table.started_at<now-timedelta(days=1)))
        accepted=db.execute(statement).first() is not None
        started=None if accepted else db.scalar(select(table.started_at).where(table.key==key))
        db.commit()
    except OperationalError:
        db.rollback();raise HTTPException(503,'Проверка лимита временно недоступна',headers={'Retry-After':'5'})
    if not accepted:
        retry=max(1,math.ceil((started+timedelta(seconds=seconds)-now).total_seconds()))
        raise HTTPException(429,'Достигнут лимит отправки. Повторите позже.',headers={'Retry-After':str(retry)})

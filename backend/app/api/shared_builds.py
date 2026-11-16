"""Public, immutable user snapshots; never promoted to verified shop prices."""
import hashlib,json,secrets
from fastapi import APIRouter,HTTPException,Response
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.api.deps import DBSession
from app.api.account import AuthUser
from app.core.price_time import db_now,iso_utc
from app.db.models import SharedConfiguration
from app.services import auth_limits
from urllib.parse import urlsplit
router=APIRouter(prefix='/api/shared-builds',tags=['shared builds'])
class Part(BaseModel):
    model_config=ConfigDict(extra='forbid')
    category:str=Field(min_length=1,max_length=80)
    name:str=Field(min_length=2,max_length=200)
    price:int|None=Field(default=None,ge=0,le=10000000)
    url:str=Field(default='',max_length=1000)
    image_url:str=Field(default='',max_length=1000)
    @field_validator('url','image_url')
    @classmethod
    def links(cls,v):
        if v:
            p=urlsplit(v)
            if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('Требуется HTTPS ссылка без пароля')
        return v
class Snapshot(BaseModel):
    model_config=ConfigDict(extra='forbid')
    v:int=Field(default=1,ge=1,le=1)
    parts:list[Part]=Field(min_length=1,max_length=32)
    game:str|None=Field(default=None,max_length=100)
    fps:float|None=Field(default=None,ge=0,le=2000,allow_inf_nan=False)
    current_fps:float|None=Field(default=None,ge=0,le=2000,allow_inf_nan=False)
def public(row):
    return {'id':row.id,'created_at':iso_utc(row.created_at),'snapshot':json.loads(row.payload),'trust':'user_snapshot'}
@router.post('',status_code=201)
def save(payload:Snapshot,db:DBSession,user:AuthUser):
    raw=json.dumps(payload.model_dump(mode='json'),sort_keys=True,ensure_ascii=False,separators=(',',':'))
    digest=hashlib.sha256(raw.encode()).hexdigest()
    previous=db.scalar(select(SharedConfiguration).where(SharedConfiguration.user_id==user.id,SharedConfiguration.fingerprint==digest))
    if previous:return public(previous)
    auth_limits.enforce(db,[(f'share-owner:{user.id}',30,3600)])
    row=SharedConfiguration(id=secrets.token_hex(16),user_id=user.id,fingerprint=digest,created_at=db_now(),payload=raw)
    db.add(row)
    try:db.commit()
    except IntegrityError:
        db.rollback()
        row=db.scalar(select(SharedConfiguration).where(SharedConfiguration.user_id==user.id,SharedConfiguration.fingerprint==digest))
        if row is None:raise
    return public(row)
@router.get('/mine')
def mine(db:DBSession,user:AuthUser):
    return {'items':[public(row) for row in db.scalars(select(SharedConfiguration).where(SharedConfiguration.user_id==user.id).order_by(SharedConfiguration.created_at.desc()).limit(100))]}
@router.get('/{identifier}')
def read(identifier:str,db:DBSession,response:Response):
    row=db.get(SharedConfiguration,identifier) if len(identifier)==32 else None
    if row is None:raise HTTPException(404,'Снимок не найден или ссылка отозвана')
    response.headers['Cache-Control']='no-store'
    return public(row)
@router.delete('/{identifier}',status_code=204)
def revoke(identifier:str,db:DBSession,user:AuthUser):
    row=db.get(SharedConfiguration,identifier)
    if row is None or row.user_id!=user.id:raise HTTPException(404,'Снимок не найден')
    db.delete(row);db.commit()

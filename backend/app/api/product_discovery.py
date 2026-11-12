from fastapi import APIRouter,HTTPException,Response
from app.api.deps import DBSession
from app.api.account import AuthUser
from app.schemas.product_discovery import DiscoveryQuery
from app.db.models import ExternalSearchJob
from app.services.product_discovery import create_job,public_job
router=APIRouter(prefix='/api/product-search',tags=['product-search'])
@router.post('',status_code=202)
def search(payload:DiscoveryQuery,db:DBSession,user:AuthUser,response:Response):
    response.headers['Cache-Control']='no-store'
    return create_job(db,user.id,payload)
@router.get('/{identifier}')
def result(identifier:str,db:DBSession,user:AuthUser,response:Response):
    response.headers['Cache-Control']='no-store'
    row=db.get(ExternalSearchJob,identifier)
    if row is None or row.user_id!=user.id:raise HTTPException(404,'Поиск не найден')
    from datetime import timedelta
    from app.core.price_time import db_now
    if row.status in ('queued','running') and row.created_at<db_now()-timedelta(minutes=5):
        row.status='failed';row.result='{"reason":"interrupted","offers":[]}'
        db.commit()
    return public_job(row)

from fastapi import APIRouter,Query
from typing import Literal
from app.api.deps import DBSession
from app.services.catalog_history import price_history
router=APIRouter(prefix='/api/products',tags=['price-history'])
@router.get('/{product_id}/price-history')
def history(product_id:str,db:DBSession,days:int=Query(default=7,ge=7,le=14)):
    return price_history(db,product_id,days)

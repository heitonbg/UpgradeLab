from fastapi import APIRouter
from app.api.deps import DBSession
from app.crud import hardware as hw_crud
from app.schemas.hardware import HardwareOut

router = APIRouter(prefix="/api", tags=["hardware"])


@router.get("/hardware", response_model=list[HardwareOut])
def get_hardware(db: DBSession):
    return hw_crud.list_all(db)
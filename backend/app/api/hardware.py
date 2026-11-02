from fastapi import APIRouter
from app.api.deps import DBSession
from app.crud import hardware as hw_crud
from app.schemas.hardware import HardwareOut
from app.services.prices import public_price
from app.services.upgrade_prices import upgrade_price_map

router = APIRouter(prefix="/api", tags=["hardware"])


@router.get("/hardware", response_model=list[HardwareOut])
def get_hardware(db: DBSession):
    prices = upgrade_price_map(db)
    return [{**HardwareOut.model_validate(hw).model_dump(), **public_price(prices.get(hw.id))}
            for hw in hw_crud.list_all(db)]


@router.get("/prices/status")
def price_status(db: DBSession):
    prices = upgrade_price_map(db)
    hardware = hw_crud.list_all(db)
    return {"coverage": {kind: {"total": sum(h.type == kind for h in hardware),
                                "priced": sum(h.type == kind and h.id in prices for h in hardware)}
                         for kind in ("CPU", "GPU", "RAM")},
            "updated_at": max((p.observed_at for p in prices.values()), default=None),
            "note": "Цены Ozon, Avito, WB, Яндекс Маркета и DNS используются из полученных предложений не старше 24 часов; при разрешении всех источников также доступны архивные котировки PassMark/Avito."}

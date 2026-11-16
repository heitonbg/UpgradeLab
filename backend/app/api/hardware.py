from fastapi import APIRouter, Response
from sqlalchemy import select, not_
from app.api.deps import DBSession
from app.crud import hardware as hw_crud
from app.schemas.hardware import HardwareOut
from app.services.prices import public_price
from app.services.upgrade_prices import upgrade_price_map
from app.db.models import Hardware

router = APIRouter(prefix="/api", tags=["hardware"])


@router.get('/hardware/selectors')
def hardware_selectors(db: DBSession, response: Response):
    """Small model list for UI pickers; offer prices are calculated only when needed."""
    response.headers['Cache-Control'] = 'no-store'
    rows = db.execute(select(Hardware.id, Hardware.type, Hardware.name, Hardware.raw_score,
                             Hardware.socket, Hardware.vram, Hardware.ram_type,
                             Hardware.ram_capacity_gb, Hardware.ram_channels)
                      .where(Hardware.type.in_(('CPU', 'GPU', 'RAM')),
                             not_((Hardware.type == 'CPU') & Hardware.name.ilike('Apple M%')))
                      .order_by(Hardware.type, Hardware.raw_score.desc(), Hardware.name))
    return [dict(row._mapping) for row in rows]


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

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from app.api.deps import DBSession
from app.crud import hardware as hw_crud
from app.db.models import Hardware
from app.schemas.calculate import CalculateRequest, CalculateResponse
from app.services import calculator
from app.services.prices import price_map, public_price

router = APIRouter(prefix="/api", tags=["calculator"])


@router.post("/calculate", response_model=CalculateResponse)
def post_calculate(payload: CalculateRequest, db: DBSession):
    cpu = hw_crud.get_by_id(db, payload.cpu_id)
    gpu = hw_crud.get_by_id(db, payload.gpu_id)

    if cpu is None or cpu.type != "CPU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CPU не найдена")
    if gpu is None or gpu.type != "GPU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "GPU не найдена")

    # Получаем все CPU и GPU для поиска апгрейда в рамках бюджета
    all_hw = list(db.scalars(select(Hardware)))
    prices = price_map(db)
    all_cpus = [
        {"id": h.id, "name": h.name, "raw_score": h.raw_score, "avg_price": prices[h.id].price_rub if h.id in prices else None, "socket": h.socket}
        for h in all_hw if h.type == "CPU"
    ]
    all_gpus = [
        {"id": h.id, "name": h.name, "raw_score": h.raw_score, "avg_price": prices[h.id].price_rub if h.id in prices else None, "vram": h.vram}
        for h in all_hw if h.type == "GPU"
    ]
    all_rams = [
        {"id": h.id, "name": h.name, "raw_score": h.raw_score, "ram_type": h.ram_type, "ram_capacity_gb": h.ram_capacity_gb, "ram_channels": h.ram_channels}
        for h in all_hw if h.type == "RAM"
    ]

    # Получаем VRAM и сокет текущей GPU/CPU
    gpu_vram = gpu.vram
    cpu_socket = cpu.socket
    
    # Получаем RAM если указана
    ram_type = None
    ram_channels = None
    if payload.ram_id:
        ram = db.get(Hardware, payload.ram_id)
        if not ram or ram.type != "RAM":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "RAM не найдена")
        if ram:
            ram_type = ram.ram_type
            ram_channels = ram.ram_channels
    elif payload.ram_manual:
        # Используем ручные данные RAM
        ram_type = payload.ram_manual.type
        ram_channels = payload.ram_manual.channels

    result = calculator.calculate(
        cpu_raw=cpu.raw_score,
        gpu_raw=gpu.raw_score,
        game=payload.game,
        mode=payload.mode,
        budget=payload.budget,
        cpu_price=prices[cpu.id].price_rub if cpu.id in prices and prices[cpu.id].market == "used_ru" else 0,
        gpu_price=prices[gpu.id].price_rub if gpu.id in prices and prices[gpu.id].market == "used_ru" else 0,
        cpu_socket=cpu_socket,
        cpu_name=cpu.name,
        gpu_name=gpu.name,
        gpu_vram=gpu_vram,
        ram_type=ram_type,
        ram_channels=ram_channels,
        all_cpus=all_cpus,
        all_gpus=all_gpus,
        all_rams=all_rams,
        ai_mode=payload.ai_mode,
        sell_mode=payload.sell_mode,
    )
    
    return CalculateResponse(
        bottleneck=result.bottleneck,
        current_fps=result.current_fps,
        upgraded_fps=result.upgraded_fps,
        recommendation=result.recommendation,
        avg_price=result.avg_price,
        within_budget=result.within_budget,
        upgrade_component=result.upgrade_component,
        ai_warning=result.ai_warning,
        current_component_price=result.current_component_price,
        total_budget=result.total_budget,
        mode=result.mode,
        is_maxed_out=result.is_maxed_out,
        upgrade_price=public_price(prices.get(result.upgrade_id)),
    )

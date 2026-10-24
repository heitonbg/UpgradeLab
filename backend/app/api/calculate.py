from fastapi import APIRouter, HTTPException, status
from app.api.deps import DBSession
from app.crud import hardware as hw_crud
from app.schemas.calculate import CalculateRequest, CalculateResponse
from app.services import calculator

router = APIRouter(prefix="/api", tags=["calculator"])


@router.post("/calculate", response_model=CalculateResponse)
def post_calculate(payload: CalculateRequest, db: DBSession):
    cpu = hw_crud.get_by_id(db, payload.cpu_id)
    gpu = hw_crud.get_by_id(db, payload.gpu_id)

    if cpu is None or cpu.type != "CPU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CPU не найдена")
    if gpu is None or gpu.type != "GPU":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "GPU не найдена")

    result = calculator.calculate(
        cpu_raw=cpu.raw_score,
        gpu_raw=gpu.raw_score,
        game=payload.game,
        mode=payload.mode,
    )
    
    # Берем реальную цену, если она есть. Иначе мок.
    real_price = cpu.avg_price or gpu.avg_price or result.avg_price
    
    return CalculateResponse(
        bottleneck=result.bottleneck,
        current_fps=result.current_fps,
        upgraded_fps=result.upgraded_fps,
        recommendation=result.recommendation,
        avg_price=real_price,
    )
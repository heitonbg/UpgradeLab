import re
from fastapi import APIRouter
from sqlalchemy import select
from pydantic import BaseModel, Field
from app.api.deps import DBSession
from app.db.models import Hardware
from app.services.hardware_matching import match_model, model_key

router = APIRouter(prefix="/api", tags=["autodetect"])


class GpuDetectRequest(BaseModel):
    renderer_string: str = Field(max_length=1000)


class CpuDetectRequest(BaseModel):
    cpu_name: str | None = Field(default=None, max_length=200)
    # Legacy clients may still send timing data. It cannot identify a CPU model.
    benchmark_time_ms: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    cpu_cores: int | None = Field(default=None, ge=1, le=512)
    device_memory: float | None = Field(default=None, ge=0, le=2048)


class GpuDetectResponse(BaseModel):
    gpu_id: int | None
    gpu_name: str | None


class CpuDetectResponse(BaseModel):
    cpu_id: int | None
    cpu_name: str | None
    device_memory_gb: float | None = None
    message: str | None = None


GPU_MODEL = re.compile(r"(?:rtx|gtx|gt)\s*\d{3,4}\s*(?:ti\s*super|ti|super)?|(?:rx|r[579])\s*\d{3,4}\s*(?:xtx|xt)?|arc\s*[ab]\d{3}", re.I)


def _find_gpu_by_renderer(db, raw_string):
    items = list(db.scalars(select(Hardware).where(Hardware.type == "GPU")))
    exact = match_model(items, raw_string)
    if exact:
        return exact
    model = GPU_MODEL.search(raw_string)
    if not model:
        return None
    is_mobile = bool(re.search(r"laptop|mobile", raw_string, re.I))
    matches = []
    for item in items:
        candidate = GPU_MODEL.search(item.name)
        if candidate and model_key(candidate.group()) == model_key(model.group()):
            if bool(re.search(r"laptop|mobile", item.name, re.I)) == is_mobile:
                matches.append(item)
    return matches[0] if len(matches) == 1 else None


@router.post("/detect-gpu", response_model=GpuDetectResponse)
def detect_gpu(payload: GpuDetectRequest, db: DBSession):
    gpu = _find_gpu_by_renderer(db, payload.renderer_string)
    return GpuDetectResponse(gpu_id=gpu.id if gpu else None, gpu_name=gpu.name if gpu else None)


@router.post("/detect-cpu", response_model=CpuDetectResponse)
def detect_cpu(payload: CpuDetectRequest, db: DBSession):
    cpu = match_model(list(db.scalars(select(Hardware).where(Hardware.type == "CPU"))), payload.cpu_name or "")
    return CpuDetectResponse(cpu_id=cpu.id if cpu else None, cpu_name=cpu.name if cpu else None,
                             device_memory_gb=payload.device_memory,
                             message=None if cpu else "Загрузите модель CPU из Windows-отчёта или выберите её через поиск.")

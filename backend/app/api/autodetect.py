from fastapi import APIRouter
from sqlalchemy import select
from app.api.deps import DBSession
from app.db.models import Hardware
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["autodetect"])

class GpuDetectRequest(BaseModel):
    renderer_string: str

class CpuDetectRequest(BaseModel):
    benchmark_time_ms: float = Field(gt=0, allow_inf_nan=False)
    cpu_cores: int = Field(ge=1)
    device_memory: float | None = None

class GpuDetectResponse(BaseModel):
    gpu_id: int | None
    gpu_name: str | None

class CpuDetectResponse(BaseModel):
    cpu_id: int | None
    cpu_name: str | None
    device_memory_gb: float | None = None

def _find_gpu_by_renderer(db, raw_string: str) -> Hardware | None:
    if not raw_string:
        return None
    clean = raw_string.lower()
    for junk in ["angle (", "direct3d11", "vs_5_0", "ps_5_0", "d3d11", "nvidia,", "amd,", "intel,", "opengl", "direct3d9ex"]:
        clean = clean.replace(junk, "")
    
    stmt = select(Hardware).where(Hardware.type == "GPU")
    all_gpus = list(db.scalars(stmt))
    
    # Извлекаем ключевые паттерны из renderer
    # Например: "NVIDIA GeForce RTX 3060/PCIe/SSE2" -> rtx, 3060
    # "NVIDIA GeForce GTX 1050 Ti" -> gtx, 1050, ti
    import re
    model_numbers = re.findall(r'\d{3,4}', clean)  # Извлекаем числа типа 3060, 1050
    model_suffixes = [w for w in clean.split() if w in ['ti', 'super', 'xt', 'se', 'fe', 'non-plus']]
    
    best_match = None
    best_score = 0
    
    for gpu in all_gpus:
        gpu_name_lower = gpu.name.lower()
        score = 0
        
        # 1. Приоритет: точное совпадение модели (3060, 1050 Ti, etc.)
        for num in model_numbers:
            # Ищем число в названии GPU
            gpu_nums = re.findall(r'\d{3,4}', gpu_name_lower)
            for gn in gpu_nums:
                if gn == num:
                    score += 100  # Высокий приоритет за совпадение модели
        
        # 2. Суффиксы (Ti, Super, XT)
        for suffix in model_suffixes:
            if suffix in gpu_name_lower:
                score += 50
        
        # 3. Общее совпадение слов
        words = [w for w in clean.split() if len(w) > 2]
        for word in words:
            if word in gpu_name_lower:
                score += 5
        
        # 4. Приоритет более длинных совпадений
        if clean in gpu_name_lower:
            score += 200
        
        if score > best_score:
            best_score = score
            best_match = gpu
    
    return best_match if best_score >= 50 else None

@router.post("/detect-gpu", response_model=GpuDetectResponse)
def detect_gpu(payload: GpuDetectRequest, db: DBSession):
    gpu = _find_gpu_by_renderer(db, payload.renderer_string)
    return GpuDetectResponse(
        gpu_id=gpu.id if gpu else None,
        gpu_name=gpu.name if gpu else None,
    )

@router.post("/detect-cpu", response_model=CpuDetectResponse)
def detect_cpu(payload: CpuDetectRequest, db: DBSession):
    reference_time_ms = 2600.0
    reference_score = 3700.0

    estimated_score = reference_score * (reference_time_ms / payload.benchmark_time_ms)
    cpus = list(db.scalars(select(Hardware).where(Hardware.type == "CPU")))
    
    candidates = [c for c in cpus if c.raw_score is not None and c.raw_score > 500]
    if not candidates:
        return CpuDetectResponse(cpu_id=None, cpu_name=None, device_memory_gb=payload.device_memory)

    best_cpu = None
    min_diff = float('inf')

    for cpu in candidates:
        cpu_cores = cpu.cores if cpu.cores else 2
        
        diff = abs(cpu.raw_score - estimated_score)
        
        # ЖЕСТКИЙ ШТРАФ ЗА ЯДРА
        # Если у пользователя 6+ ядер, мы сильно штрафуем все процессоры с 4 и менее ядрами.
        # Это заставит алгоритм выбрать 6-ядерный FX-6100 или Ryzen 5, даже если их балл чуть выше.
        if payload.cpu_cores >= 6 and cpu_cores < 6:
            diff += 30000 # Огромный штраф
        elif payload.cpu_cores >= 4 and cpu_cores < 4:
            diff += 30000
            
        if diff < min_diff:
            min_diff = diff
            best_cpu = cpu

    logger.info(
        "CPU Detection: time=%.2f ms, estimated=%.0f, chosen=%s (score=%d, cores=%s)",
        payload.benchmark_time_ms, estimated_score, best_cpu.name, best_cpu.raw_score, best_cpu.cores
    )

    return CpuDetectResponse(
        cpu_id=best_cpu.id,
        cpu_name=best_cpu.name,
        device_memory_gb=payload.device_memory
    )
from fastapi import APIRouter,HTTPException,Query
from pydantic import BaseModel,Field
from typing import Literal
from app.api.deps import DBSession
from app.db.models import Hardware
from app.services.game_catalog import search_games
from app.services.fps_v2 import predict
router=APIRouter(prefix='/api',tags=['games'])
@router.get('/games')
def games(q:str=Query(default='',max_length=100),limit:int=Query(default=50,ge=1,le=100)):
    return search_games(q.strip(),limit)
class FpsQuery(BaseModel):
    cpu_id:int=Field(gt=0)
    gpu_id:int=Field(gt=0)
    game:str=Field(min_length=1,max_length=200)
    resolution:Literal['1080p','1440p','4K']='1080p'
    preset:Literal['low','medium','high','ultra']='high'
    ram_type:Literal['DDR3','DDR4','DDR5']|None=None
    ram_channels:Literal[1,2]|None=None
    ram_capacity_gb:int|None=Field(default=None,ge=2,le=512)
    rt:bool=False
    upscaling:Literal['off','dlss','fsr','xess']='off'
    frame_generation:bool=False
@router.post('/fps/predict')
def fps(payload:FpsQuery,db:DBSession):
    cpu=db.get(Hardware,payload.cpu_id);gpu=db.get(Hardware,payload.gpu_id)
    if cpu is None or cpu.type!='CPU' or gpu is None or gpu.type!='GPU':raise HTTPException(400,'CPU или GPU не найдены')
    return predict(cpu,gpu,**payload.model_dump(exclude={'cpu_id','gpu_id'}))

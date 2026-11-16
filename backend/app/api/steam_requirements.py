from fastapi import APIRouter,HTTPException,Query
from pydantic import BaseModel,Field
from app.api.deps import DBSession
from app.services.steam_storage import local_game,request_requirements,read_status

router=APIRouter(prefix='/api/games',tags=['games'])
class RequirementRequest(BaseModel):
    game:str=Field(min_length=1,max_length=200)

@router.post('/requirements')
def request_game_requirements(payload:RequirementRequest,db:DBSession):
    if not local_game(payload.game):raise HTTPException(404,'Game not in local catalog')
    return request_requirements(db,payload.game)

@router.get('/requirements')
def game_requirements(db:DBSession,game:str=Query(min_length=1,max_length=200)):
    if not local_game(game):raise HTTPException(404,'Game not in local catalog')
    return read_status(db,game)

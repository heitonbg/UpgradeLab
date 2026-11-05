from typing import Literal
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from app.api.deps import DBSession
from app.db.models import SearchJob
from app.schemas.calculate import CalculateRequest
from app.services.builds import BuildRequest
from app.services.search_jobs import create_job, public_job

router = APIRouter(prefix='/api/search-jobs', tags=['search'])


class JobRequest(BaseModel):
    kind: Literal['assemble', 'calculate']
    payload: dict
    client_request_id: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

    @model_validator(mode='after')
    def valid_payload(self):
        model = BuildRequest if self.kind == 'assemble' else CalculateRequest
        self.payload = model.model_validate(self.payload).model_dump(mode='json')
        return self


@router.post('', status_code=202)
def start(payload: JobRequest, db: DBSession, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return create_job(db, payload.kind, payload.payload, payload.client_request_id)


@router.get('/{job_id}')
def get(job_id: str, db: DBSession, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    if len(job_id) != 48 or any(char not in '0123456789abcdef' for char in job_id):
        raise HTTPException(404, 'Поиск не найден или результат уже удалён')
    job = db.get(SearchJob, job_id)
    if job is None:
        raise HTTPException(404, 'Поиск не найден или результат уже удалён')
    return public_job(job)

"""A single bounded search worker, durable results, and short HTTP polling.

No Redis, external worker, paid API, or long-lived HTTP connection is required.
Job IDs are random access capabilities; do not list them through the public API.
"""
import hashlib
import json
import logging
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import datetime, timedelta
from threading import Lock
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, delete, update
from sqlalchemy.exc import IntegrityError
from app.db.base import SessionLocal
from app.db.models import SearchJob

logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='component-search')
submission_lock = Lock()
progress_callback = ContextVar('search_progress', default=None)


def report_progress(message):
    callback = progress_callback.get()
    if callback:
        callback(message[:300])


def public_job(job,db=None):
    if db is not None and job.result:
        from app.services.result_access import current_result
        if not current_result(db,json.loads(job.result)):
            return {'id':job.id,'kind':job.kind,'status':'failed','progress':'Предложения изменились',
                'created_at':job.created_at.isoformat()+'Z','updated_at':job.updated_at.isoformat()+'Z',
                'result':None,'error':'Объявления или права доступа изменились. Повторите поиск.'}
    return {'id': job.id, 'kind': job.kind, 'status': job.status, 'progress': job.progress,
            'created_at': job.created_at.isoformat()+'Z', 'updated_at': job.updated_at.isoformat()+'Z',
            'result': json.loads(job.result) if job.result is not None else None, 'error': job.error}


def run_job(job_id):
    with SessionLocal() as db:
        claimed = db.execute(update(SearchJob).where(SearchJob.id == job_id, SearchJob.status == 'queued').values(
            status='running', progress='Проверяем конфигурацию и доступные цены', updated_at=datetime.utcnow()))
        db.commit()
        if claimed.rowcount != 1:
            return
        job = db.get(SearchJob, job_id)
        kind, payload = job.kind, json.loads(job.payload)
    last_progress = [0.0, None]
    def progress(message):
        now = time.monotonic()
        if message == last_progress[1] or now-last_progress[0] < 2:
            return
        with SessionLocal() as db:
            db.execute(update(SearchJob).where(SearchJob.id == job_id, SearchJob.status == 'running').values(
                progress=message, updated_at=datetime.utcnow()))
            db.commit()
        last_progress[:] = [now, message]
    token = progress_callback.set(progress)
    try:
        with SessionLocal() as db:
            if kind == 'assemble':
                from app.services.builds import BuildRequest, assemble
                result = assemble(BuildRequest.model_validate(payload), db)
            else:
                from app.api.calculate import post_calculate
                from app.schemas.calculate import CalculateRequest
                result = post_calculate(CalculateRequest.model_validate(payload), db)
            encoded = json.dumps(jsonable_encoder(result), ensure_ascii=False)
        with SessionLocal() as db:
            db.execute(update(SearchJob).where(SearchJob.id == job_id).values(status='completed', result=encoded,
                progress='Результат готов', updated_at=datetime.utcnow()))
            db.commit()
    except Exception as error:
        message = str(error.detail) if isinstance(error, HTTPException) else (
            'Поиск не завершился из-за ошибки сервера. Найденные цены сохранены; повторите подбор.')
        logger.exception('Search job %s failed', job_id)
        with SessionLocal() as db:
            db.execute(update(SearchJob).where(SearchJob.id == job_id).values(status='failed', error=message[:1000],
                progress='Поиск завершился с ошибкой', updated_at=datetime.utcnow()))
            db.commit()
    finally:
        progress_callback.reset(token)


def create_job(db, kind, payload, client_request_id):
    from app.services.result_access import listing_revision
    canonical = json.dumps([kind, client_request_id, payload,listing_revision(db)], sort_keys=True, ensure_ascii=False)
    request_key = hashlib.sha256(canonical.encode()).hexdigest()
    with submission_lock:
        previous = db.scalar(select(SearchJob).where(SearchJob.request_key == request_key))
        if previous:
            return public_job(previous,db)
        active = list(db.scalars(select(SearchJob.id).where(SearchJob.status.in_(['queued', 'running']))))
        if len(active) >= 4:
            raise HTTPException(429, 'Сервер уже выполняет несколько поисков. Повторите через минуту.')
        db.execute(delete(SearchJob).where(SearchJob.updated_at < datetime.utcnow()-timedelta(days=1),
                                          SearchJob.status.in_(['completed', 'failed'])))
        job = SearchJob(id=secrets.token_hex(24), request_key=request_key, kind=kind,
            payload=json.dumps(payload, ensure_ascii=False), status='queued', progress='Поиск в очереди',
            created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return public_job(db.scalar(select(SearchJob).where(SearchJob.request_key == request_key)),db)
        response = public_job(job,db)
        executor.submit(run_job, job.id)
        return response


def recover_jobs():
    """Keep completed results; report an interrupted process instead of hanging forever."""
    with SessionLocal() as db:
        db.execute(update(SearchJob).where(SearchJob.status == 'running').values(status='failed',
            error='Backend перезапустился во время поиска. Полученные цены сохранены; повторите подбор.',
            progress='Поиск прерван перезапуском сервера', updated_at=datetime.utcnow()))
        pending = list(db.scalars(select(SearchJob.id).where(SearchJob.status == 'queued').limit(4)))
        db.commit()
    for job_id in pending:
        executor.submit(run_job, job_id)

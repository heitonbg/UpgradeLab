"""Read-only published measured FPS cohorts, separate from model predictions."""
import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator, field_validator
from sqlalchemy import select, func
from app.api.deps import DBSession
from app.api.account import AuthUser
from app.db.models import BenchmarkSubmission, BenchmarkCapture, BenchmarkMeasurement, BenchmarkSource
from app.core.config import settings

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])
DATA = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "aggregates.json"
FPSHQ_MEDIANS = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "fpshq_game_fps_medians_raw.json"
FPSHQ_TOP50 = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "fpshq_model_top50_raw.json"


class BenchmarkSubmissionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    game: str = Field(min_length=2, max_length=100)
    game_version: str | None = Field(default=None, max_length=40)
    cpu: str = Field(min_length=2, max_length=100)
    gpu: str = Field(min_length=2, max_length=100)
    ram_gb: float | None = Field(default=None, gt=0, le=1024)
    resolution: str = Field(pattern=r'^(1280x720|1920x1080|2560x1440|3840x2160|other)$')
    preset: str = Field(min_length=2, max_length=60)
    rt: bool | None = None
    upscaling: str | None = Field(default=None, max_length=60)
    frame_generation: bool | None = None
    average_fps: float = Field(gt=0, le=2000, allow_inf_nan=False)
    one_percent_low: float | None = Field(default=None, gt=0, le=2000, allow_inf_nan=False)
    scene: str = Field(min_length=2, max_length=160)
    os: str = Field(min_length=2, max_length=60)
    driver: str | None = Field(default=None, max_length=80)
    evidence_url: HttpUrl | None = None
    publication_consent: bool

    @field_validator('evidence_url')
    @classmethod
    def https_evidence_only(cls, value):
        if value is not None and (value.scheme != 'https' or value.username or value.password):
            raise ValueError('Ссылка на подтверждение должна быть публичным HTTPS URL')
        return value

    @model_validator(mode='after')
    def validate_submission(self):
        if self.one_percent_low is not None and self.one_percent_low > self.average_fps:
            raise ValueError('1% low не может превышать средний FPS')
        if not self.publication_consent:
            raise ValueError('Для отправки нужно подтвердить право на публикацию результата')
        return self


def _submission_dict(row):
    return {'id': row.id, 'created_at': row.created_at.isoformat() + 'Z',
            'status': row.status, 'result': json.loads(row.payload)}


@router.post('/submissions', status_code=201)
def submit_benchmark(payload: BenchmarkSubmissionIn, db: DBSession, user: AuthUser):
    """Accept community evidence privately for moderation; pending data is not public or calibrated."""
    return _store_submission(payload,db,user)

def _store_submission(payload,db,user,capture=None):
    from app.services import benchmark_limits
    from sqlalchemy.exc import IntegrityError
    from app.core.price_time import db_now
    now = db_now()
    recent = db.scalar(select(func.count()).select_from(BenchmarkSubmission).where(
        BenchmarkSubmission.user_id == user.id,
        BenchmarkSubmission.created_at >= now - timedelta(hours=24))) or 0
    if recent >= 5:
        raise HTTPException(429, 'Достигнут дневной лимит отправки результатов. Попробуйте завтра.')
    benchmark_limits.enforce(db,user.id,'submit',5,86400)
    document=payload.model_dump(mode='json')
    if capture:document['capture']={k:v for k,v in capture.items() if k!='frametimes_ms'}
    row = BenchmarkSubmission(user_id=user.id, created_at=now, status='pending',
                              payload=json.dumps(document,ensure_ascii=False))
    db.add(row)
    db.flush()
    if capture:db.add(BenchmarkCapture(fingerprint=capture['fingerprint'],submission_id=row.id,evidence=json.dumps(capture)))
    try:db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Такой захват уже отправлен. Дубликат не добавлен.')
    db.refresh(row)
    return {'submission': _submission_dict(row),
            'message': 'Результат принят на проверку. До модерации он не появится в публичных бенчмарках.'}


@router.get('/submissions/mine')
def my_benchmark_submissions(db: DBSession, user: AuthUser):
    rows = db.scalars(select(BenchmarkSubmission).where(
        BenchmarkSubmission.user_id == user.id).order_by(BenchmarkSubmission.created_at.desc()).limit(50)).all()
    return {'items': [_submission_dict(row) for row in rows]}


def require_benchmark_reviewer(user):
    allowed = {value.strip().casefold() for value in settings.benchmark_reviewer_emails.split(',') if value.strip()}
    if not allowed or user.email.casefold() not in allowed:
        raise HTTPException(403, 'Нет прав для проверки пользовательских бенчмарков')


class BenchmarkReviewIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(pattern='^(approved|rejected)$')
    note: str | None = Field(default=None, max_length=500)


@router.get('/submissions/review-queue')
def benchmark_review_queue(db: DBSession, user: AuthUser):
    require_benchmark_reviewer(user)
    rows = db.scalars(select(BenchmarkSubmission).where(
        BenchmarkSubmission.status == 'pending').order_by(BenchmarkSubmission.created_at).limit(100)).all()
    return {'items': [_submission_dict(row) for row in rows]}


@router.patch('/submissions/{submission_id}')
def review_benchmark_submission(submission_id: int, payload: BenchmarkReviewIn, db: DBSession, user: AuthUser):
    require_benchmark_reviewer(user)
    row = db.get(BenchmarkSubmission, submission_id)
    if not row:
        raise HTTPException(404, 'Результат не найден')
    if row.status != 'pending':
        raise HTTPException(409, 'Результат уже рассмотрен')
    row.status = payload.status
    row.reviewed_at = datetime.utcnow()
    row.reviewed_by = user.id
    row.review_note = payload.note
    db.commit()
    return {'submission': _submission_dict(row)}


@router.get('/community')
def approved_community_benchmarks(db: DBSession, game: str = Query(default='', max_length=100)):
    """Individually reviewed runs; never mixed into publisher aggregates."""
    rows = db.scalars(select(BenchmarkSubmission).where(
        BenchmarkSubmission.status == 'approved').order_by(BenchmarkSubmission.created_at.desc()).limit(200)).all()
    items = []
    for row in rows:
        result = json.loads(row.payload)
        if not matching(result.get('game'), game):
            continue
        items.append({'id': row.id, 'created_at': row.created_at.isoformat() + 'Z',
                      'measurement_type': 'community_verified', 'publisher': 'UpgradeLab community',
                      'result': {key: value for key, value in result.items() if key != 'publication_consent'},
                      'review_note': row.review_note})
    return {'total': len(items), 'items': items}


@lru_cache(maxsize=1)
def cohorts():
    return json.loads(DATA.read_text(encoding="utf-8"))["rows"]


def matching(value, search):
    return not search or search.casefold() in (value or "").casefold()


_RESOLUTION_KEYS = {
    "1280x720": "720p", "720p": "720p",
    "1920x1080": "1080p", "1080p": "1080p",
    "2560x1440": "1440p", "1440p": "1440p",
    "3840x2160": "4k", "2160p": "4k", "4k": "4k",
}


def resolution_matches(value, search):
    if not search:
        return True
    def key(raw):
        normalized = str(raw or "").strip().casefold().replace("×", "x").replace(" ", "")
        return _RESOLUTION_KEYS.get(normalized)
    requested, actual = key(search), key(value)
    if requested and actual:
        return requested == actual
    return matching(value, search)


@lru_cache(maxsize=1)
def fpshq_game_medians():
    if not FPSHQ_MEDIANS.is_file():
        return {'meta': {'rows': 0}, 'rows': []}
    data = json.loads(FPSHQ_MEDIANS.read_text(encoding='utf-8'))
    meta = data.get('meta', {})
    if meta.get('license') != 'CC BY 4.0' or meta.get('url') != 'https://fpshq.com/en/data/game-fps-medians/':
        raise RuntimeError('Unexpected FPSHQ dataset license or provenance')
    return data


@lru_cache(maxsize=1)
def fpshq_top50_data():
    data = json.loads(FPSHQ_TOP50.read_text(encoding='utf-8'))
    meta = data.get('meta', {})
    if meta.get('license') != 'CC BY 4.0' or meta.get('url') != 'https://fpshq.com/en/data/fps-model-top50/':
        raise RuntimeError('Unexpected FPSHQ top-50 license or provenance')
    return data


@router.get('/game-reference')
def game_reference(
    game: str = Query(default='', max_length=100),
    resolution: str = Query(default='', max_length=20),
    preset: str = Query(default='', max_length=60),
    limit: int = Query(default=100, ge=1, le=200),
):
    """FPSHQ review/community medians; broad GPU-class references, not exact PC tests."""
    data = fpshq_game_medians()
    rows = [row for row in data['rows']
            if matching(row.get('game'), game)
            and resolution_matches(row.get('resolution'), resolution)
            and matching(row.get('preset'), preset)]
    return {'total': len(rows), 'items': rows[:limit], 'measurement_type': 'publisher_aggregate',
            'source': 'FPSHQ', 'source_url': data['meta'].get('url'),
            'license': data['meta'].get('license'), 'version': data['meta'].get('version'),
            'note': 'Сводная медиана по разным видеокартам из обзоров и измерений. Это не FPS конкретной связки CPU/GPU; используйте только как общий ориентир.',
            'exact_pair_supported': False}


@router.get('/gpu-reference')
def gpu_reference(
    game: str = Query(default='', max_length=100),
    gpu: str = Query(default='', max_length=100),
    resolution: str = Query(default='', max_length=20),
    preset: str = Query(default='', max_length=60),
    source: str = 'aggregate',
    sort: str = 'game',
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = 0,
):
    """FPSHQ GPU reference rows; model, review aggregates and measurements remain distinct."""
    data = fpshq_top50_data()
    rows = [row for row in data['rows']
            if (source == 'any' or row.get('source') == source)
            and matching(row.get('game'), game)
            and matching(row.get('gpu'), gpu)
            and resolution_matches(row.get('resolution'), resolution)
            and matching(row.get('preset'), preset)]
    if sort == 'fps_desc':
        rows.sort(key=lambda row: (-float(row.get('fps') or 0), row.get('game', '').casefold(), row.get('gpu', '').casefold()))
    elif sort == 'fps_asc':
        rows.sort(key=lambda row: (float(row.get('fps') or 0), row.get('game', '').casefold(), row.get('gpu', '').casefold()))
    else:
        rows.sort(key=lambda row: (row.get('game', '').casefold(), row.get('gpu', '').casefold(),
                                   row.get('resolution', ''), row.get('preset', '')))
    items = [{'game': row['game'], 'gpu': row['gpu'], 'resolution': row['resolution'],
              'preset': row['preset'], 'average_fps': row['fps'], 'one_percent_low': row.get('low1'),
              'data_type': row['source'], 'basis': 'review_aggregate' if row['source'] == 'aggregate' else row['source'], 'url': row['url']}
             for row in rows[offset:offset + limit]]
    return {'total': len(rows), 'limit': limit, 'offset': offset, 'items': items,
            'measurement_type': 'review_aggregate' if source == 'aggregate' else 'mixed_gpu_reference', 'source': 'FPSHQ',
            'source_url': data['meta'].get('url'), 'license': data['meta'].get('license'),
            'version': data['meta'].get('version'),
            'note': 'FPSHQ GPU references are shown by provenance. These are not tests of a particular CPU/GPU pair.',
            'exact_pair_supported': False}


@router.get("")
def list_benchmarks(
    game: str = Query(default="", max_length=100),
    cpu: str = Query(default="", max_length=100),
    gpu: str = Query(default="", max_length=100),
    resolution: str = Query(default="", max_length=20),
    sort: str = Query(default="fps_desc", pattern="^(fps_desc|fps_asc|game)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows = [row for row in cohorts() if matching(row["settings"]["game"], game)
            and matching(row["settings"]["cpu"], cpu)
            and matching(row["settings"]["gpu"], gpu)
            and resolution_matches(row["settings"].get("resolution"), resolution)]
    if sort == "game":
        rows.sort(key=lambda row: (row["settings"].get("game") or "").casefold())
    else:
        rows.sort(key=lambda row: row.get("mean_fps") or 0, reverse=sort == "fps_desc")
    return {"total": len(rows), "limit": limit, "offset": offset,
            "items": rows[offset:offset + limit], "measurement_type": "measured",
            "note": "Среднее опубликованных измерений для одинаковых условий. Числа не являются прогнозом для иной конфигурации."}


@router.get('/dataset-info')
def benchmark_dataset_info(db: DBSession):
    """Provenance and import status for the curated source-backed dataset."""
    document = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'benchmarks' / 'measurements.json').read_text(encoding='utf-8'))
    count = db.scalar(select(func.count()).select_from(BenchmarkMeasurement)) or 0
    source_count = db.scalar(select(func.count()).select_from(BenchmarkSource)) or 0
    return {'schema_version': document.get('schema_version'),
            'curated_measurements': len(document.get('rows', [])),
            'stored_measurements': count, 'stored_sources': source_count,
            'quality': document.get('quality', {}), 'snapshot_manifest': document.get('sources', []),
            'imported': count > 0,
            'note': 'Только source-backed данные из сохранённого snapshot. Модельные оценки и пользовательские результаты не входят в измеренные записи.'}


@router.get('/measurements')
def list_stored_measurements(
    db: DBSession,
    game: str = Query(default='', max_length=100),
    cpu: str = Query(default='', max_length=120),
    gpu: str = Query(default='', max_length=120),
    resolution: str = Query(default='', max_length=20),
    data_type: str = Query(default='measured', pattern='^(measured|estimated|all)$'),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    query = select(BenchmarkMeasurement)
    if data_type != 'all':
        query = query.where(BenchmarkMeasurement.data_type == data_type)
    for column, value in ((BenchmarkMeasurement.game, game), (BenchmarkMeasurement.cpu, cpu),
                          (BenchmarkMeasurement.gpu, gpu), (BenchmarkMeasurement.resolution, resolution)):
        if value:
            query = query.where(column.ilike(f'%{value}%'))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(BenchmarkMeasurement.game, BenchmarkMeasurement.gpu,
                                     BenchmarkMeasurement.resolution, BenchmarkMeasurement.id)
                      .offset(offset).limit(limit)).all()
    return {'total': total, 'limit': limit, 'offset': offset,
            'items': [json.loads(row.payload) for row in rows],
            'measurement_type': 'source_record',
            'note': 'Это исходные опубликованные наблюдения с происхождением и лицензией; не расчётный прогноз.'}


class CaptureEnvelope(BaseModel):
    model_config=ConfigDict(extra='forbid')
    filename:str=Field(min_length=1,max_length=160)
    content:str=Field(min_length=1,max_length=4*1024*1024)
    metadata:dict=Field(default_factory=dict)

async def read_capture_request(request):
    from pydantic import ValidationError
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>8*1024*1024:raise HTTPException(413,'Запрос превышает 8 МиБ')
    try:return CaptureEnvelope.model_validate_json(body)
    except ValidationError:raise HTTPException(422,'Ожидается CSV/JSON до 4 МиБ с допустимыми метаданными')

def decode_capture(envelope):
    from app.services.benchmark_capture import parse_capture,CaptureError
    try:return parse_capture(envelope.content,envelope.filename)
    except CaptureError as exc:raise HTTPException(422,str(exc))
    except RecursionError:raise HTTPException(422,'Слишком сложная структура файла')

@router.post('/capture/preview')
async def preview_capture(request:Request,db:DBSession,user:AuthUser):
    from app.services import benchmark_limits
    benchmark_limits.enforce(db,user.id,'preview',20,3600)
    envelope=await read_capture_request(request)
    from starlette.concurrency import run_in_threadpool
    capture=await run_in_threadpool(decode_capture,envelope)
    duplicate=db.get(BenchmarkCapture,capture['fingerprint']) is not None
    return {**{k:v for k,v in capture.items() if k!='frametimes_ms'},'duplicate':duplicate,'note':'Файл можно подделать. Распознавание не подтверждает подлинность; требуется модерация.'}

@router.post('/capture/submit',status_code=201)
async def submit_capture(request:Request,db:DBSession,user:AuthUser):
    from pydantic import ValidationError
    from starlette.concurrency import run_in_threadpool
    from app.services import benchmark_limits
    benchmark_limits.enforce(db,user.id,'parse-submit',10,3600)
    envelope=await read_capture_request(request)
    capture=await run_in_threadpool(decode_capture,envelope)
    if db.get(BenchmarkCapture,capture['fingerprint']):raise HTTPException(409,'Такой захват уже отправлен')
    document={**capture['metadata'],**envelope.metadata,'average_fps':capture['average_fps'],'one_percent_low':capture['one_percent_low']}
    for key in ('cpu','gpu','game','resolution'):
        if capture['metadata'].get(key) and document.get(key)!=capture['metadata'][key]:capture['warnings'].append(f'Пользователь уточнил распознанное поле {key}; проверить вручную')
    try:payload=BenchmarkSubmissionIn.model_validate(document)
    except ValidationError as exc:raise HTTPException(422,exc.errors(include_input=False,include_context=False))
    return _store_submission(payload,db,user,capture)

@router.get('/submissions/{submission_id}/capture')
def capture_evidence(submission_id:int,db:DBSession,user:AuthUser):
    row=db.get(BenchmarkSubmission,submission_id)
    if row is None:raise HTTPException(404,'Прогон не найден')
    if row.user_id!=user.id:require_benchmark_reviewer(user)
    capture=db.scalar(select(BenchmarkCapture).where(BenchmarkCapture.submission_id==row.id))
    if capture is None:raise HTTPException(404,'Исходных frametime нет')
    return json.loads(capture.evidence)

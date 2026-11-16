"""Local cache and bounded durable SQLite queue. No HTTP inside user requests."""
from __future__ import annotations
import hashlib,json,sqlite3
from contextlib import closing,contextmanager
from contextvars import ContextVar
from datetime import timedelta
from functools import wraps,lru_cache
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select,update,func,or_,and_,inspect
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from app.db.models import SteamRequirements,SteamEnrichmentTask as Task,SteamSourceState as Source,Hardware
from app.core.config import settings
from app.core.price_time import db_now,as_utc,iso_utc
from app.services.game_catalog import catalog,key as game_key
from app.services.steam_parser import VERSION,parse_requirements,GPU_RE
from app.services.cpu_requirements import parse_cpu_requirement

_state=ContextVar('steam_requirement_context',default=None)
TABLES=(SteamRequirements.__table__,Task.__table__,Source.__table__)

@lru_cache(maxsize=16)
def _queue_engine(engine):
    # API sessions may already hold every pooled connection under concurrency.
    # A short-lived independent SQLite connection avoids nested pool starvation
    # without committing the caller's transaction or increasing the API pool.
    if engine.url.get_backend_name()!='sqlite' or not engine.url.database or engine.url.database==':memory:':
        return engine
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    return create_engine(engine.url,poolclass=NullPool,connect_args={'check_same_thread':False,'timeout':2})


def ensure_schema(engine):
    existing=set(inspect(engine).get_table_names())
    if all(table.name in existing for table in TABLES):return None
    saved=None
    filename=engine.url.database
    if engine.url.get_backend_name()=='sqlite' and filename and filename!=':memory:':
        source=Path(filename).resolve()
        if source.is_file() and source.stat().st_size:
            directory=source.parent/'backups';directory.mkdir(parents=True,exist_ok=True)
            saved=directory/('before-steam-'+uuid4().hex+'.db')
            try:
                with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(saved)) as dst:
                    src.backup(dst)
                    if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('backup_integrity_failed')
            except Exception:
                saved.unlink(missing_ok=True);raise
    for table in TABLES:table.create(engine,checkfirst=True)
    return saved

@lru_cache(maxsize=1)
def _local_index():
    index_path=Path(__file__).resolve().parents[1]/'data/steam_game_index.json'
    if index_path.is_file():
        document=json.loads(index_path.read_text(encoding='utf-8'))
        games=document['games'] if document.get('version')==1 else catalog()
    else:games=catalog()
    ids={str(g['id']):g for g in games};names={}
    for g in ids.values():
        for name in [g['name'],*g.get('aliases',[])]:
            names.setdefault(game_key(name),[]).append(g)
    return ids,{k:v[0] for k,v in names.items() if len({str(g['id']) for g in v})==1}

def local_game(value):
    value=str(getattr(value,'value',value)).strip();ids,names=_local_index()
    return ids.get(value) or names.get(game_key(value))

@lru_cache(maxsize=2)
def _hardware_for_ready(engine,epoch):
    with Session(_queue_engine(engine)) as session:
        rows=list(session.scalars(select(Hardware).where(Hardware.type.in_(('CPU','GPU')),Hardware.raw_score>0)))
        from types import SimpleNamespace
        return tuple(SimpleNamespace(id=r.id,type=r.type,name=r.name,raw_score=r.raw_score) for r in rows)

@lru_cache(maxsize=2000)
def _ready_indexed(engine,epoch,game_id):
    game=local_game(game_id);rec=game.get('recommended_requirements') or {}
    if not isinstance(rec,dict) or not rec.get('cpu') or not rec.get('gpu'):return False
    rows=_hardware_for_ready(engine,epoch)
    from app.services.cpu_requirements import CpuRequirementResolver
    from app.services.requirements_anchored_fps import resolve_gpu_requirement
    cpu=CpuRequirementResolver([r for r in rows if r.type=='CPU']).resolve(rec['cpu'])
    gpu=resolve_gpu_requirement(rec['gpu'],[r for r in rows if r.type=='GPU'])
    return cpu.get('status')==gpu.get('status')=='resolved_exact_models'

def _local_ready(game,db=None):
    if db is None:return False
    import time
    return _ready_indexed(db.get_bind().engine,int(time.monotonic()//300),str(game['id']))

def _parsed(row):
    try:return json.loads(row.parsed_json) if row else None
    except (ValueError,TypeError):return None

def read_status(db,game):
    game=local_game(game)
    if game is None:return {'status':'unknown_game','game_id':None,'version':None}
    gid=str(game['id']);row=db.get(SteamRequirements,gid)
    task=db.scalar(select(Task).where(Task.game_id==gid,Task.task_type=='requirements'))
    parsed=_parsed(row)
    if row and parsed:
        status='available' if parsed.get('recommended',{}).get('cpu') and parsed.get('recommended',{}).get('gpu') else 'no_recommended'
    elif task and task.status in ('queued','running'):status=task.status
    elif task and task.status=='failed':status='failed'
    elif _local_ready(game,db):status='local_ready'
    else:status='not_requested'
    # Existing requirements stay usable while a refresh is pending or unavailable.
    return {'status':status,'game_id':gid,'game':game['name'],
        'steam_app_id':row.app_id if row else game.get('steam_app_id'),
        'source_url':row.source_url if row else game.get('source_url'),
        'source_type':'steam_developer_requirements' if row else 'local_catalog',
        'retrieved_at':iso_utc(row.retrieved_at) if row else None,
        'last_checked_at':iso_utc(row.last_checked_at) if row else None,
        'expires_at':iso_utc(row.expires_at) if row else None,
        'version':row.content_sha256 if row else None,'requirements':parsed,
        'task_status':task.status if task else None,'attempts':task.attempts if task else 0,
        'last_error':task.last_error if task else None,'poll_after_seconds':5,
        'refresh_pending':bool(task and task.status in ('queued','running'))}

def request_requirements(db,game,now=None):
    now=now or db_now();game=local_game(game)
    if game is None:raise ValueError('unknown_catalog_game')
    if not settings.steam_requirements_enabled:return {**read_status(db,game['id']),'status':'disabled'}
    row=db.get(SteamRequirements,str(game['id']))
    if row and row.expires_at>now:return read_status(db,game['id'])
    if not row and _local_ready(game,db):return read_status(db,game['id'])
    active=db.scalar(select(Task).where(Task.game_id==str(game['id']),Task.task_type=='requirements'))
    if active and (active.status in ('queued','running') or active.next_attempt_at>now):
        return read_status(db,game['id'])

    engine=_queue_engine(db.get_bind().engine);gid=str(game['id'])
    # A separate short transaction never commits the caller's account/build work.
    with engine.connect() as conn:
        conn.exec_driver_sql('BEGIN IMMEDIATE')
        old=conn.execute(select(Task).where(Task.game_id==gid,Task.task_type=='requirements')).mappings().first()
        if old and (old['status'] in ('queued','running') or old['next_attempt_at']>now):
            conn.commit()
        else:
            pending=conn.scalar(select(func.count()).select_from(Task).where(Task.status.in_(('queued','running'))))
            if pending>=settings.steam_max_pending:
                conn.commit();return {**read_status(db,gid),'status':'queue_full'}
            values={'status':'queued','attempts':0,'next_attempt_at':now,'updated_at':now,'lease_owner':None,'lease_expires_at':None,'last_error':None}
            if old:conn.execute(update(Task).where(Task.id==old['id']).values(**values))
            else:conn.execute(insert(Task).values(game_id=gid,task_type='requirements',priority=0,created_at=now,**values))
            conn.commit()
    db.expire_all()
    return read_status(db,gid)

def claim(engine,owner,now=None):
    now=now or db_now()
    ready=or_(and_(Task.status=='queued',Task.next_attempt_at<=now),and_(Task.status=='running',Task.lease_expires_at<=now))
    with engine.connect() as conn:
        conn.exec_driver_sql('BEGIN IMMEDIATE')
        conn.execute(update(Task).where(Task.status=='running',Task.lease_expires_at<=now,Task.attempts>=settings.steam_max_attempts).values(status='failed',lease_owner=None,lease_expires_at=None,last_error='lease_attempts_exhausted',next_attempt_at=now+timedelta(days=1)))
        task_id=conn.scalar(select(Task.id).where(ready,Task.attempts<settings.steam_max_attempts).order_by(Task.priority.desc(),Task.created_at).limit(1))
        if task_id is None:conn.commit();return None
        row=conn.execute(update(Task).where(Task.id==task_id,ready).values(status='running',lease_owner=owner,
            lease_expires_at=now+timedelta(seconds=120),attempts=Task.attempts+1,updated_at=now).returning(*Task.__table__.c)).mappings().first()
        conn.commit();return dict(row) if row else None

def reserve_request(engine,now=None):
    now=now or db_now()
    with engine.connect() as conn:
        conn.exec_driver_sql('BEGIN IMMEDIATE')
        row=conn.execute(select(Source).where(Source.source=='steam_store')).mappings().first()
        dates=[row[k] for k in ('next_request_at','cooldown_until') if row and row[k] and row[k]>now]
        if dates:conn.commit();return max((d-now).total_seconds() for d in dates)
        conn.execute(insert(Source).values(source='steam_store',next_request_at=now+timedelta(seconds=settings.steam_request_interval_seconds)).on_conflict_do_update(
            index_elements=['source'],set_={'next_request_at':now+timedelta(seconds=settings.steam_request_interval_seconds)}))
        conn.commit();return 0

def fail_task(engine,task,owner,error,now=None):
    now=now or db_now();code=error.code;attempts=task['attempts']
    delay=max(error.retry_after,30*2**max(0,attempts-1))
    if code=='http_403':delay=max(delay,86400)
    if code in ('app_not_found','appid_not_uniquely_resolved','not_base_game','game_title_mismatch'):delay=max(delay,settings.steam_negative_cache_days*86400)
    terminal=not error.transient or attempts>=settings.steam_max_attempts
    if terminal:delay=max(delay,86400)
    with engine.begin() as conn:
        conn.execute(update(Task).where(Task.id==task['id'],Task.lease_owner==owner).values(
            status='failed' if terminal else 'queued',lease_owner=None,lease_expires_at=None,
            next_attempt_at=now+timedelta(seconds=delay),updated_at=now,last_error=code))
        if code in ('http_403','http_429'):
            conn.execute(insert(Source).values(source='steam_store',cooldown_until=now+timedelta(seconds=delay),last_error=code).on_conflict_do_update(
                index_elements=['source'],set_={'cooldown_until':now+timedelta(seconds=delay),'last_error':code}))

def finish_task(engine,task,owner,data,appid,now=None):
    now=now or db_now()
    with Session(engine) as db:
        current=db.get(Task,task['id'])
        if not current or current.lease_owner!=owner or current.status!='running' or current.lease_expires_at<=now:return None
        cpus=list(db.scalars(select(Hardware).where(Hardware.type=='CPU',Hardware.raw_score>0)))
        gpus=list(db.scalars(select(Hardware).where(Hardware.type=='GPU',Hardware.raw_score>0)))
        parsed=parse_requirements(data,cpus,gpus)
        rec=parsed['recommended'];has_recommended=bool(rec.get('cpu') and rec.get('gpu'))
        row=db.get(SteamRequirements,task['game_id']) or SteamRequirements(game_id=task['game_id'])
        old=_parsed(row) or {}
        # A temporarily empty or less-complete payload cannot erase good stored requirements.
        quality=lambda p:(sum(bool(p.get(level,{}).get('fully_resolved')) for level in ('minimum','recommended')),sum(bool(p.get(level,{}).get(field)) for level in ('minimum','recommended') for field in ('cpu','gpu')))
        if not old or quality(parsed)>=quality(old):
            raw=data.get('pc_requirements');raw=raw if isinstance(raw,dict) else {}
            stored={**parsed,**{kind:{k:v for k,v in parsed[kind].items() if k!='raw_html'} for kind in ('minimum','recommended')}}
            canonical=json.dumps(stored,sort_keys=True,ensure_ascii=False)
            row.app_id=appid;row.title=data.get('name','');row.minimum_html=parsed['minimum']['raw_html'];row.recommended_html=parsed['recommended']['raw_html']
            row.parsed_json=canonical;row.parsing_status=parsed['parsing_status'];row.match_confidence=parsed['match_confidence']
            row.parser_version=VERSION;row.content_sha256=hashlib.sha256(canonical.encode()).hexdigest()
            row.source_url='https://store.steampowered.com/app/'+str(appid)+'/';row.retrieved_at=now
        row.last_checked_at=now
        row.expires_at=now+timedelta(days=settings.steam_cache_days if has_recommended else settings.steam_negative_cache_days)
        db.add(row);current.status='completed';current.lease_owner=None;current.lease_expires_at=None;current.updated_at=now;current.last_error=None
        db.commit();return parsed

def enriched_profile(base):
    current=_state.get()
    if not current or not current.get('requirements'):return base
    parsed=current['requirements'];result=dict(base or {})
    for level in ('minimum','recommended'):
        fields=parsed.get(level,{})
        if fields.get('fully_resolved'):
            result[level+'_requirements']={'cpu':fields['cpu'],'gpu':' or '.join(m['name'] for m in fields['gpu_match']['resolved_models'])}
    result['developer_target']=parsed.get('official_target')
    result['source_url']=current['source_url']
    result['requirements_provenance']={'license':None,'snapshot_date':current['last_checked_at'],'source':'Steam developer-published requirements'}
    result['steam_requirements']=current
    return result

def current_status():return _state.get()

def with_requirements(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        payload=args[0] if args else kwargs.get('payload');db=args[1] if len(args)>1 else kwargs.get('db')
        token=None
        if _state.get() is None and isinstance(db,Session) and payload is not None and settings.steam_requirements_enabled:
            try:
                game=local_game(payload.game)
                if game:token=_state.set(request_requirements(db,game['id']))
            except SQLAlchemyError:
                # Old isolated test schemas and a temporarily unavailable queue must not break FPS.
                pass
        try:return function(*args,**kwargs)
        finally:
            if token is not None:_state.reset(token)
    return wrapped

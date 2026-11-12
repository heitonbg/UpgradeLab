"""One privileged executor; local import works independently of network rights."""
import json,os,time,uuid,tempfile
from contextlib import contextmanager
from pathlib import Path
from zipfile import ZipFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core import price_time
from app.core.config import settings
from app.db.models import CatalogSyncRun,CatalogAccess
from app.services.catalog_files import CatalogError
from app.services.catalog_import import prepare_import,apply_import,load_schema
from app.services.catalog_access import validated_rights
from app.services.safe_http import SafeSession
from app.services.network_policy import Policy

@contextmanager
def sync_lock(engine):
    filename=engine.url.database
    if engine.url.get_backend_name()!='sqlite' or not filename or filename==':memory:':raise CatalogError('file_sqlite_required')
    lock=open(str(Path(filename).resolve())+'.regard.lock','a+b')
    try:
        lock.seek(0)
        if os.name=='nt':
            import msvcrt
            if Path(lock.name).stat().st_size==0:lock.write(b'0');lock.flush();lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise CatalogError('sync_already_running') from None
        else:
            import fcntl
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise CatalogError('sync_already_running') from None
        yield
    finally:lock.close()  # OS releases the lock, including on process termination.

def download(engine,directory,transport=None):
    from app.services.source_permissions import network_allowed
    with Session(engine) as db:
        access=db.get(CatalogAccess,'regard');rights=validated_rights(access) if access else None
    if not settings.regard_download_enabled or not rights or not rights.automatic_download or not network_allowed('regard'):
        raise CatalogError('automatic_download_not_authorized')
    if settings.regard_price_url!='https://www.regard.ru/api/site/pricelist':raise CatalogError('unconfirmed_price_endpoint')
    return fetch_official(directory,transport)


def fetch_official(directory,transport=None):
    """Fixed public endpoint only. Caller must authorize diagnostics or pass sync gates."""
    import hashlib,logging,re
    from app.services.regard_feed import RegardFeedAdapter
    endpoint='https://www.regard.ru/api/site/pricelist'
    media='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    headers={'User-Agent':'UpgradeLab/1.0','Accept':media+', application/octet-stream;q=0.9, */*;q=0.8',
             'Accept-Language':'ru-RU,ru;q=0.9','Referer':'https://www.regard.ru/'}
    session=transport or SafeSession(Policy(hosts=('www.regard.ru','regard.ru')),extra_media_types=(media,))
    target=Path(directory)/'price.xlsx';started=time.perf_counter();attempts=0
    handle=tempfile.NamedTemporaryFile(dir=directory,suffix='.part',delete=False);partial=Path(handle.name);handle.close()
    try:
        for attempt in range(2):
            attempts+=1
            try:
                digest=hashlib.sha256();size=0
                class Sink:
                    def write(self,chunk):
                        nonlocal size
                        size+=len(chunk)
                        if size>8*1024*1024:raise CatalogError('file_too_large')
                        digest.update(chunk);return stream.write(chunk)
                with partial.open('wb') as stream:
                    response=session.get_to(endpoint,Sink(),headers=headers,timeout=25,max_bytes=8*1024*1024)
                status=response.status_code
                if status in (401,402,403,404,429):raise CatalogError('download_access_rejected_'+str(status))
                if status>=500:
                    if attempt==0:time.sleep(.25);continue
                    raise CatalogError('download_unavailable')
                if status!=200:raise CatalogError('unexpected_download_status')
                break
            except TimeoutError:
                if attempt:raise CatalogError('download_timeout') from None
                time.sleep(.25)
        download_seconds=time.perf_counter()-started
        if response.headers.get('Content-Type','').split(';',1)[0].strip().lower()!=media:raise CatalogError('invalid_xlsx_content_type')
        with partial.open('rb') as check:
            if check.read(4)!=b'PK\x03\x04':raise CatalogError('not_xlsx')
        native=RegardFeedAdapter(settings.regard_source_utc_offset_minutes).read(partial.read_bytes())
        with ZipFile(partial) as archive:
            if archive.testzip() is not None:raise CatalogError('corrupt_xlsx')
        filename=re.search(r'regard_price_\d{6}_\d{2}\.xlsx',response.headers.get('Content-Disposition',''))
        metadata={'status':status,'filename':filename.group(0) if filename else None,'content_type':media,'bytes':size,
                  'sha256':digest.hexdigest(),'download_seconds':download_seconds,'validation_seconds':time.perf_counter()-started-download_seconds,'seconds':time.perf_counter()-started,'attempts':attempts,'native':native.metadata}
        os.replace(partial,target)
        target.with_suffix('.json').write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf-8')
        logging.getLogger(__name__).info('regard_download %s',json.dumps(metadata,ensure_ascii=False))
        return target
    except Exception as error:
        logging.getLogger(__name__).warning('regard_download %s',json.dumps({'status':'failed','attempts':attempts,'code':str(error) if isinstance(error,CatalogError) else type(error).__name__}))
        raise
    finally:partial.unlink(missing_ok=True)


def synchronize(engine,schema_path,rights,*,file=None,audience='development',analysis=False,min_products=1000,transport=None):
    from app.services.regard_feed import RegardFeedAdapter
    from scripts.regard_feed import peak_memory
    identifier=uuid.uuid4().hex
    with sync_lock(engine):
        with Session(engine) as db:
            # Owning the process lock proves an earlier local executor stopped.
            for row in db.scalars(select(CatalogSyncRun).where(CatalogSyncRun.source=='regard',CatalogSyncRun.status=='running')):
                row.status='interrupted';row.finished_at=price_time.db_now()
            db.add(CatalogSyncRun(id=identifier,source='regard',started_at=price_time.db_now(),status='running',report='{}'));db.commit()
        started=time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix='upgradelab-regard-') as directory:
                if file:
                    from app.services.catalog_import import read_local
                    source=Path(directory)/'price.xlsx';source.write_bytes(read_local(file,8*1024*1024))
                else:source=download(engine,directory,transport)
                schema=load_schema(schema_path)
                if schema.input_adapter!='regard-native-v1' or schema.source!='regard':raise CatalogError('native_regard_schema_required')
                # Source compressed bytes are bounded; XML is parsed as a stream.
                size=source.stat().st_size
                if size>8*1024*1024:raise CatalogError('file_too_large')
                from app.services.catalog_import import digest,hardware_snapshot,source_snapshot
                with Session(engine) as db:
                    signature=digest([digest(source.read_bytes()),schema.model_dump(),rights,audience,analysis,min_products,digest(hardware_snapshot(db))])
                    state=digest(source_snapshot(db,'regard'))
                    previous=db.scalar(select(CatalogSyncRun).where(CatalogSyncRun.source=='regard',CatalogSyncRun.status.in_(['succeeded','unchanged'])).order_by(CatalogSyncRun.finished_at.desc()))
                    cached=json.loads(previous.report) if previous else {}
                if cached.get('input_signature')==signature and cached.get('catalog_state')==state:
                    receipt={**cached['receipt'],'idempotent':True}
                    result={**cached,'receipt':receipt,'metrics':{'xlsx_parse_skipped':True}}
                else:
                    native=RegardFeedAdapter(schema.source_utc_offset_minutes).read(source.read_bytes())
                    if len(native.rows)<min_products:raise CatalogError('suspicious_small_feed')
                    with ZipFile(source) as archive:
                        if archive.testzip() is not None:raise CatalogError('corrupt_xlsx')
                    metrics={};plan=prepare_import(engine,source,schema_path,metrics=metrics)
                    receipt=apply_import(engine,source,schema_path,plan,rights,audience=audience,analysis=analysis)
                    result={'receipt':receipt,'source_metadata':native.metadata,'metrics':metrics,
                        'elapsed_seconds':time.perf_counter()-started,'peak_working_set_mib':peak_memory(),
                        'sqlite_bytes':Path(engine.url.database).stat().st_size}
                with Session(engine) as db:result['catalog_state']=digest(source_snapshot(db,'regard'))
                if not file:result['download']=json.loads(source.with_suffix('.json').read_text(encoding='utf-8'))
                result.update(input_signature=signature,elapsed_seconds=time.perf_counter()-started,peak_working_set_mib=peak_memory(),sqlite_bytes=Path(engine.url.database).stat().st_size)
            with Session(engine) as db:
                run=db.get(CatalogSyncRun,identifier);run.status='unchanged' if receipt.get('idempotent') else 'succeeded';run.finished_at=price_time.db_now();run.report=json.dumps(result,default=str,ensure_ascii=False);db.commit()
            return {'sync_id':identifier,**result}
        except Exception as error:
            with Session(engine) as db:
                run=db.get(CatalogSyncRun,identifier);run.status='failed';run.finished_at=price_time.db_now();run.report=json.dumps({'error':str(error) if isinstance(error,CatalogError) else type(error).__name__});db.commit()
            raise

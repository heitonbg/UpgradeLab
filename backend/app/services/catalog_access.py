"""Local import permissions. No access to any store is enabled by these helpers."""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from app.db.models import CatalogAccess,CatalogProduct
from app.schemas.catalog import CatalogRights
from app.core.price_time import as_utc
from app.core import price_time
_analysis=ContextVar('closed_catalog_analysis',default=None)

def analysis_database(engine):
    from pathlib import Path
    name=engine.url.database
    if engine.url.get_backend_name()!='sqlite' or not name or not name.endswith('.analysis.db'):
        raise ValueError('Closed analysis requires a separate .analysis.db SQLite')
    return str(Path(name).resolve())

@contextmanager
def closed_catalog_analysis(engine):
    token=_analysis.set(analysis_database(engine))
    try:yield
    finally:_analysis.reset(token)

def analysis_enabled(db):
    from pathlib import Path
    name=db.get_bind().url.database
    return bool(name and _analysis.get()==str(Path(name).resolve()))

_fixture=ContextVar('catalog_fixture_visibility',default=False)

@contextmanager
def fixture_catalog():
    token=_fixture.set(True)
    try:yield
    finally:_fixture.reset(token)

def validated_rights(access):
    try:
        rights=CatalogRights.model_validate_json(access.rights)
        stamp=as_utc(rights.confirmed_at)
        return rights if rights.development and stamp and stamp<=price_time.utc_now() else None
    except (ValueError,TypeError):
        return None

def visible_catalog_ids(db):
    from sqlalchemy import select
    accesses={a.source:a for a in db.scalars(select(CatalogAccess))}
    states={}
    rights_by_source={source:validated_rights(access) for source,access in accesses.items()}
    private_analysis=analysis_enabled(db)
    for item in db.scalars(select(CatalogProduct).where(CatalogProduct.offer_id.is_not(None))):
        access=accesses.get(item.source)
        rights=rights_by_source.get(item.source)
        payload=json.loads(item.payload)
        allowed=rights is not None and rights.source==item.source and item.source!='avito' and (
            bool(access.public_enabled) and rights.public_display and not access.fixture or
            bool(access.fixture) and _fixture.get())
        closed=bool(rights and rights.source==item.source and not access.fixture and item.source=='regard' and private_analysis)
        states[item.offer_id]=bool(not payload.get('missing_from_feed') and (
            allowed and (payload.get('eligible') or payload.get('preliminary_eligible')) and payload.get('availability')!='out_of_stock' or
            closed and payload.get('analysis_eligible') and payload.get('availability')!='out_of_stock'))
    return states

def filter_catalog(db,rows):
    states=visible_catalog_ids(db)
    from app.services.internal_offers import live_internal
    return [row for row in rows if states.get(row.id,row.origin!='catalog_import') and live_internal(db,row)]

def restricted_catalog_sources(db):
    from sqlalchemy import select
    result=set()
    for access in db.scalars(select(CatalogAccess)):
        rights=validated_rights(access)
        if not rights or not access.public_enabled or not rights.automatic_download or access.fixture:
            result.add(access.source)
    return result

def recheck_blocked_ids(db):
    from sqlalchemy import select
    sources=restricted_catalog_sources(db)
    return {item.offer_id for item in db.scalars(select(CatalogProduct))
            if item.source in sources and item.offer_id is not None}

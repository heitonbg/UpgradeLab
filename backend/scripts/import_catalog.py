"""Privileged local CLI only. Never imports app.main or fetches files from URLs."""
import argparse,json,sys
from pathlib import Path
from sqlalchemy import create_engine,inspect
from app.db.models import Base,CatalogAccess,CatalogProduct,CatalogImport,CatalogObservation,CatalogDailyPrice,CatalogPriceCorrection
from app.services.catalog_import import prepare_import,apply_import,canonical
from app.services.catalog_files import CatalogError
from app.services.catalog_access import fixture_catalog
from app.schemas.offers import SearchOffers
from app.services.offers import search_offers
from sqlalchemy.orm import Session

def engine_for(path):
    path=Path(path).resolve()
    if not path.is_file():raise CatalogError('explicit_existing_database_required')
    return create_engine('sqlite:///'+path.as_posix(),connect_args={'timeout':15})

def fixture_check(args):
    if args.fixture and not Path(args.database).name.endswith('.fixture.db'):
        raise CatalogError('fixture_database_suffix_required')

def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='Local CSV/XLSX catalogue preview/apply; no network downloads')
    parser.add_argument('--database',required=True,help='Explicit existing SQLite file; no production default')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init',help='Add import tables to an existing application database')
    for name in ('preview','apply'):
        cmd=sub.add_parser(name);cmd.add_argument('--file',required=True);cmd.add_argument('--schema',required=True)
        cmd.add_argument('--plan',required=True)
        if name=='preview':cmd.add_argument('--received-at')
        else:
            cmd.add_argument('--rights',required=True)
            cmd.add_argument('--confirm-owner-rights',action='store_true')
            cmd.add_argument('--audience',choices=['development','public-noncommercial','public-commercial'],default='development')
            cmd.add_argument('--fixture',action='store_true');cmd.add_argument('--allow-rejected',action='store_true');cmd.add_argument('--closed-analysis',action='store_true');cmd.add_argument('--allow-shrink',action='store_true')
    query=sub.add_parser('search',help='Search existing offers; imported sources remain offline unless explicitly authorized')
    query.add_argument('--query',required=True);query.add_argument('--category',required=True)
    query.add_argument('--source',required=True);query.add_argument('--fixture',action='store_true');query.add_argument('--closed-analysis',action='store_true')
    args=parser.parse_args();engine=None
    try:
        engine=engine_for(args.database)
        if args.command=='init':
            if not inspect(engine).has_table('hardware'):raise CatalogError('hardware_catalogue_required')
            for table in (CatalogAccess.__table__,CatalogProduct.__table__,CatalogImport.__table__,CatalogObservation.__table__,CatalogDailyPrice.__table__,CatalogPriceCorrection.__table__):
                table.create(engine,checkfirst=True)
            result={'status':'import_tables_ready'}
        elif args.command=='preview':
            target=Path(args.plan).resolve()
            if target in {Path(args.file).resolve(),Path(args.schema).resolve(),Path(args.database).resolve()}:
                raise CatalogError('unsafe_plan_output')
            plan=prepare_import(engine,args.file,args.schema,received_at=args.received_at)
            with target.open('x',encoding='utf-8') as output:output.write(canonical(plan)+'\n')
            result={**plan['report'],'source':plan['source'],'plan_sha256':plan['plan_sha256']}
        elif args.command=='apply':
            fixture_check(args)
            if not args.confirm_owner_rights:raise CatalogError('explicit_owner_confirmation_required')
            from app.services.catalog_import import read_local
            plan=json.loads(read_local(args.plan,32*1024*1024))
            rights=json.loads(read_local(args.rights,65536))
            result=apply_import(engine,args.file,args.schema,plan,rights,audience=args.audience,
                fixture=args.fixture,allow_rejected=args.allow_rejected,analysis=args.closed_analysis,allow_shrink=args.allow_shrink)
        else:
            fixture_check(args)
            with Session(engine) as db:
                payload=SearchOffers(query=args.query,category=args.category,sources=[args.source])
                payload._catalog_only=True
                if args.closed_analysis:
                    from app.services.catalog_access import closed_catalog_analysis
                    with closed_catalog_analysis(engine):result=search_offers(db,payload)
                elif args.fixture:
                    with fixture_catalog():result=search_offers(db,payload)
                else:result=search_offers(db,payload)
        print(canonical(result))
        return 0
    except CatalogError as error:
        print(canonical({'error':str(error)}),file=sys.stderr);return 2
    except Exception:
        print(canonical({'error':'catalog_operation_failed'}),file=sys.stderr);return 2
    finally:
        if engine is not None:engine.dispose()

if __name__=='__main__':raise SystemExit(main())

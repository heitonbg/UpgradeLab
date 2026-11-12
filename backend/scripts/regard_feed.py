"""Privileged offline workflow for the real owner-provided Regard workbook."""
import argparse,json,time,sys,os
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from app.db.models import Base,Hardware,CatalogProduct,StoreOffer
from app.services.regard_feed import RegardFeedAdapter,compare_feeds
from app.services.catalog_import import prepare_import,apply_import
from app.services.catalog_access import closed_catalog_analysis
from app.schemas.offers import SearchOffers
from app.services.offers import search_offers
from app.services.builds import BuildRequest,assemble
from app.core.price_time import iso_utc,utc_now

def schema():
 fields=('external_product_id','vendor_code','brand','title','price','category','source_updated_at','product_url','availability','description')
 return {'source':'regard','version':'regard-native-xlsx-v1','format':'xlsx','input_adapter':'regard-native-v1','source_utc_offset_minutes':180,'columns':{k:k for k in fields},'categories':{k:k for k in ('CPU','GPU','motherboard','memory','storage','psu','case','cooler')},'availability':{},'currency':'RUB','decimal_separator':'.','thousands_separator':'none','complete':True}

def seed_hardware(db):
 data=json.loads((Path(__file__).resolve().parents[1]/'seed_data.json').read_text(encoding='utf-8'))
 for kind,key in (('CPU','cpus'),('GPU','gpus'),('RAM','ram')):
  items=data.get(key,[])
  if not items:continue
  lo=min(int(r['score']) for r in items);hi=max(int(r['score']) for r in items)
  for row in items:
   score=int(row['score']);normal=55 if hi==lo else max(10,min(100,round(10+(score-lo)*90/(hi-lo))))
   db.add(Hardware(type=kind,name=row['name'],raw_score=score,normalized_score=normal,cores=row.get('cores'),vram=row.get('vram'),socket=row.get('socket'),ram_type=row.get('type') if kind=='RAM' else None,ram_capacity_gb=row.get('capacity_gb'),ram_channels=row.get('channels')))
 db.commit()

def peak_memory():
 if os.name=='nt':
  import ctypes
  from ctypes import wintypes
  class Info(ctypes.Structure):
   _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('peak','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
  info=Info();info.cb=ctypes.sizeof(info)
  kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
  psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Info),wintypes.DWORD]
  if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(info),info.cb):return round(info.peak/1048576,2)
 return None

def run(file,output):
 root=Path(output).resolve();root.mkdir(parents=True,exist_ok=True);dbfile=root/'regard.analysis.db'
 if dbfile.exists():raise ValueError('Refusing to overwrite existing analysis database')
 file=Path(file).resolve();raw=file.read_bytes();start=time.perf_counter();read=RegardFeedAdapter().read(raw);reader_time=time.perf_counter()-start
 mapping=root/'schema.json';mapping.write_text(json.dumps(schema(),ensure_ascii=False,indent=2),encoding='utf-8')
 engine=create_engine('sqlite:///'+dbfile.as_posix());Base.metadata.create_all(engine)
 try:
  with Session(engine) as db:seed_hardware(db)
  metrics={};start=time.perf_counter();plan=prepare_import(engine,file,mapping,metrics=metrics);preview_time=time.perf_counter()-start
  (root/'preview.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
  rights={'source':'regard','development':True,'public_display':False,'commercial':False,'automatic_download':False,'basis':'Owner supplied workbook for isolated local analysis in iteration 12; no shop publication or download permission','owner_confirmed_by':'UpgradeLab owner task iteration 12','confirmed_at':iso_utc(utc_now())}
  (root/'rights.json').write_text(json.dumps(rights,ensure_ascii=False,indent=2),encoding='utf-8')
  start=time.perf_counter();receipt=apply_import(engine,file,mapping,plan,rights,analysis=True,allow_rejected=True);apply_time=time.perf_counter()-start
  second=apply_import(engine,file,mapping,plan,rights,analysis=True,allow_rejected=True)
  result={'real_workbook':True,'fixture':False,'native':read.metadata,'preview':plan['report'],'receipt':receipt,'repeat_idempotent':second['idempotent'],'metrics':{**metrics,'native_reader_seconds':reader_time,'preview_seconds':preview_time,'apply_seconds':apply_time},'public_display':False,'automatic_download':False,'network_requests':0,'scenarios':{}}
  with Session(engine) as db,patch('socket.socket',side_effect=AssertionError('Offline real feed analysis forbids sockets')):
   query=SearchOffers(query='RTX 5060',category='GPU',sources=['regard']);query._catalog_only=True
   result['public_search_count']=len(search_offers(db,query)['offers'])
   with closed_catalog_analysis(engine):
    result['closed_search']=search_offers(db,query)
    gpu=next((h for h in db.scalars(select(Hardware).where(Hardware.type=='GPU')) if h.name=='GeForce RTX 5060' and h.vram==8),None)
    for name,gpu_id in (('optimal',None),('rtx5060',gpu.id if gpu else -1)):
     if gpu_id==-1:result['scenarios'][name]={'status':'partial','reason':'RTX 5060 8GB absent from existing Hardware'};continue
     request=BuildRequest(scenario='build',auto_parts=True,budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['regard'],allow_store_fallback=False,allow_platform_change=True)
     if gpu_id is None:r=assemble(request,db)
     else:
      from app.services.adaptive_builds import solve_profiles
      from app.services.offers import available_offers
      from app.services.offer_geography import offer_scope,financial_evidence
      from fastapi import HTTPException
      with offer_scope(request):
       eligible=available_offers(db,['regard'],include_unavailable=True)
       allowed={v.id for v in eligible if v.category!='GPU' or v.hardware_id==gpu_id}
       try:r=financial_evidence(solve_profiles(request,db,allowed,observed=True),db,request)
       except HTTPException as error:
        gpu_rows=[v for v in eligible if v.category=='GPU' and v.hardware_id==gpu_id]
        chosen=min(gpu_rows,key=lambda v:v.price_rub) if gpu_rows else None
        r={'status':'partial','parts':[{'type':'GPU','name':chosen.name,'price':chosen.price_rub,'offer_id':chosen.id}] if chosen else [],'missing_parts':[{'type':'configuration','reason':error.detail}],'purchase_ready':False}

     from app.services.offers import available_offers
     candidates={}
     for offer in available_offers(db,['regard'],include_unavailable=True):
      if offer.category=='GPU' and gpu_id is not None and offer.hardware_id!=gpu_id:continue
      candidates.setdefault(offer.category,[])
      if len(candidates[offer.category])<3:candidates[offer.category].append({'name':offer.name,'price_rub':offer.price_rub,'external_product_id':json.loads(offer.attributes)['catalog_import'].get('external_product_id')})
     details=[]
     for part in r.get('parts',[]):
      offer=db.get(StoreOffer,part.get('offer_id')) if part.get('offer_id') else None
      metadata=json.loads(offer.attributes).get('catalog_import',{}) if offer else {}
      details.append({'category':part['type'],'name':offer.name if offer else part['name'],'hardware_name':part['name'],'external_product_id':metadata.get('external_product_id'),'price_rub':part['price'],'origin':offer.origin if offer else None,'compatibility':part.get('compatibility'),'product_url':None,'availability':'unknown','delivery':'unknown'})
     complete_technical=r.get('technical_compatibility_confirmed',False)
     result['scenarios'][name]={'status':'draft' if len(details)==8 and complete_technical else 'partial','raw_solver_status':r.get('status'),'purchase_ready':False,'candidate_examples':candidates,'found_parts':details,'found_subtotal_rub':sum(v['price_rub'] for v in details),'compatibility_status':r.get('compatibility_status'),'physical_compatibility':r.get('physical_compatibility'),'missing_parts':r.get('missing_parts',[]),'missing_evidence':[{'category':v['category'],**v['compatibility']} for v in details if v.get('compatibility') and v['compatibility'].get('status')!='compatible']+[{'category':'physical',**r['physical_compatibility']}] if r.get('physical_compatibility') else [],'unknowns':['Stock, city, shipping, payment conditions and product URLs are not supplied by workbook','Physical dimensions and connector evidence must be checked independently'],'result':r}
  result['metrics']['peak_working_set_mib']=peak_memory()
  (root/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8');return result
 finally:engine.dispose()

def main():
 sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--file',required=True);p.add_argument('--output');p.add_argument('--compare-with');a=p.parse_args()
 if a.compare_with:
  reader=RegardFeedAdapter();old=reader.read(Path(a.compare_with).read_bytes());new=reader.read(Path(a.file).read_bytes());print(json.dumps(compare_feeds([r for _,r in old.rows],[r for _,r in new.rows]),ensure_ascii=False));return
 if not a.output:p.error('--output required for isolated import')
 r=run(a.file,a.output);print(json.dumps({'native':r['native'],'matching':r['preview']['matching'],'accepted':r['preview']['accepted'],'rejected':r['preview']['rejected'],'materialized':r['receipt']['materialized_offers'],'public_search_count':r['public_search_count'],'closed_search_count':len(r['closed_search']['offers']),'scenarios':{k:{'status':v['status'],'parts':len(v.get('found_parts',[])),'subtotal':v.get('found_subtotal_rub')} for k,v in r['scenarios'].items()},'metrics':r['metrics']},ensure_ascii=False))
if __name__=='__main__':main()

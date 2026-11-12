"""Actual local HTTP matrix, saves raw responses and source dates."""
import json,time,requests
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/product-readiness-20261111';BASE='http://127.0.0.1:8006'
payload=dict(scenario='build',auto_parts=True,budget=80000,game='Red Dead Redemption 2',mode='1080p_high',socket='AM4',ram_type='DDR4',ram_capacity_gb=16,price_sources=['regard'],allow_store_fallback=False,allow_platform_change=True,pricing_mode='offers')
session=requests.Session();session.trust_env=False
results=[]
for sources in [['regard'],['upgradelab'],['regard','upgradelab']]:
 for budget in [50000,80000,120000,150000]:
  start=time.monotonic();r=session.post(BASE+'/api/assemble',json={**payload,'budget':budget,'price_sources':sources},timeout=180);body=r.json();item={'budget':budget,'sources':sources,'http_status':r.status_code,'seconds':round(time.monotonic()-start,2),'result':body};results.append(item)
  (OUT/'matrix-real.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(budget,sources,r.status_code,body.get('status'),body.get('total_price'),len(body.get('parts',[])),flush=True)

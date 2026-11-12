"""Explicit operator diagnostic. No DB, no cookies/headers in report."""
import argparse,json
from pathlib import Path
from app.services.regard_sync import fetch_official
from app.services.safe_http import SafeSession
from app.services.network_policy import Policy
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);p.add_argument('--confirm-official-download',action='store_true');p.add_argument('--warm-session',action='store_true');a=p.parse_args()
 if not a.confirm_official_download:p.error('explicit --confirm-official-download required; review source conditions')
 root=Path(a.output);root.mkdir(parents=True,exist_ok=False)
 client=None;home=None
 if a.warm_session:
  client=SafeSession(Policy(hosts=('www.regard.ru','regard.ru')),extra_media_types=('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',))
  r=client.get('https://www.regard.ru/',timeout=20,max_bytes=8*1024*1024)
  home={'status':r.status_code,'session_cookie_count':len(client.cookies)}
  if r.status_code!=200:raise RuntimeError('public_homepage_unavailable')
 file=fetch_official(root,client);report=json.loads(file.with_suffix('.json').read_text(encoding='utf-8'))
 if home:report['homepage']=home
 report['warm_session']=a.warm_session
 (root/'diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k!='native'},ensure_ascii=False))

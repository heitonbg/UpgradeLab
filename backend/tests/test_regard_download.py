"""Official download protocol fixtures. Never connects to Regard."""
import sys,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from test_regard_feed import xlsx,BASE
from app.services import regard_sync
from app.services.catalog_files import CatalogError
MEDIA='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
class FakeTransport:
 def __init__(self,status=200,media=MEDIA,body=None,error=None):self.status=status;self.media=media;self.body=body if body is not None else xlsx(BASE);self.error=error;self.calls=0
 def get_to(self,url,sink,**kwargs):
  self.calls+=1;self.url=url;self.kwargs=kwargs
  if self.error:raise self.error
  if self.status==200:sink.write(self.body)
  return SimpleNamespace(status_code=self.status,headers={'Content-Type':self.media,'Content-Disposition':'attachment; filename="regard_price_091126_17.xlsx"'})
class RegardDownloadTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
 def test_success_requires_native_structure_and_records_hash(self):
  import hashlib,json
  transport=FakeTransport();path=regard_sync.fetch_official(self.root,transport)
  self.assertEqual(path.read_bytes(),transport.body)
  metadata=json.loads(path.with_suffix('.json').read_text())
  self.assertEqual(metadata['sha256'],hashlib.sha256(transport.body).hexdigest());self.assertEqual(metadata['native']['selected_rows'],1)
  self.assertEqual(transport.kwargs['headers']['Referer'],'https://www.regard.ru/')
  self.assertEqual(transport.kwargs['headers']['User-Agent'],'UpgradeLab/1.0')
 def test_403_and_429_stop_without_retry(self):
  for status in (403,429):
   t=FakeTransport(status=status)
   with self.assertRaises(CatalogError):regard_sync.fetch_official(self.root,t)
   self.assertEqual(t.calls,1)
 def test_timeout_has_two_attempts_and_cleans_partial_file(self):
  t=FakeTransport(error=TimeoutError())
  with patch('app.services.regard_sync.time.sleep'):
   with self.assertRaises(CatalogError):regard_sync.fetch_official(self.root,t)
  self.assertEqual(t.calls,2);self.assertEqual(list(self.root.glob('*.part')),[])
 def test_html_and_wrong_media_rejected(self):
  for t in (FakeTransport(media='text/html'),FakeTransport(body=b'<html>error</html>'),FakeTransport(body=b'PK\x03\x04broken')):
   with self.assertRaises(CatalogError):regard_sync.fetch_official(self.root,t)
   self.assertFalse((self.root/'price.xlsx').exists());self.assertEqual(list(self.root.glob('*.part')),[])
 def test_503_retries_only_twice(self):
  t=FakeTransport(status=503)
  with patch('app.services.regard_sync.time.sleep'):
   with self.assertRaises(CatalogError):regard_sync.fetch_official(self.root,t)
  self.assertEqual(t.calls,2)
 def test_oversized_response_is_rejected_and_cleaned(self):
  t=FakeTransport(body=b'x'*(8*1024*1024+1))
  with self.assertRaisesRegex(CatalogError,'file_too_large'):regard_sync.fetch_official(self.root,t)
  self.assertEqual(list(self.root.glob('*.part')),[])

 def test_failure_keeps_previous_file(self):
  target=self.root/'price.xlsx';target.write_bytes(b'last validated snapshot')
  with self.assertRaises(CatalogError):regard_sync.fetch_official(self.root,FakeTransport(status=403))
  self.assertEqual(target.read_bytes(),b'last validated snapshot')
if __name__=='__main__':unittest.main()

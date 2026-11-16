"""Local fixtures only: no store requests, production database or raw file execution."""
import json,math,unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from app.db.base import Base,get_db
from app.db.models import User,BenchmarkSubmission,BenchmarkCapture,SharedConfiguration
from app.api.account import current_user
from app.api.benchmarks import router as benchmarks
from app.api.shared_builds import router as shares
from app.services.benchmark_capture import parse_capture,CaptureError

def csv(values=None):
    values=values or [10+(i%5) for i in range(1200)]
    return 'Application,ProcessID,SwapChainAddress,MsBetweenPresents\n'+'\n'.join('game.exe,1,abc,'+str(v) for v in values)
class ParsingTests(unittest.TestCase):
    def test_mean_is_inverse_mean_frametime_and_low_uses_slowest_frames(self):
        x=parse_capture(csv([10]*990+[30]*10),'x.csv')
        self.assertAlmostEqual(x['average_fps'],1000/10.2,places=3)
        self.assertAlmostEqual(x['one_percent_low'],1000/30,places=3)
        self.assertEqual(x['frames'],1000)
        self.assertEqual(x['authenticity'],'unverified')
    def test_capframex_bom_metadata_and_unknown_fields_not_invented(self):
        data={'SessionInfo':{'CPU':'Fixture CPU','GPU':'Fixture GPU','ProcessName':'private.exe'},'Runs':[{'CaptureData':{'MsBetweenPresents':[10]*1000}}]}
        x=parse_capture('\ufeff'+json.dumps(data),'capture.json')
        self.assertEqual(x['metadata'],{'cpu':'Fixture CPU','gpu':'Fixture GPU'})
        self.assertNotIn('game',x['metadata'])
        self.assertTrue(any('постоянный' in w for w in x['warnings']))
    def test_semicolon_decimal_comma_and_duplicate_normalization(self):
        content='MsBetweenPresents;Application\n'+'\n'.join('10,5;game.exe' for _ in range(100))
        x=parse_capture(content,'x.csv');self.assertAlmostEqual(x['average_fps'],95.238,places=3)
        self.assertEqual(x['fingerprint'],parse_capture(content+'\n','x.csv')['fingerprint'])
    def test_invalid_numeric_and_summary_only_rejected(self):
        for value in (-1,0,'nan','inf',True,'=1+1'):
            with self.subTest(value=value),self.assertRaises(CaptureError):parse_capture(csv([10]*100+[value]),'x.csv')
        with self.assertRaises(CaptureError):parse_capture('AverageFPS,GPUTime\n100,5','x.csv')
    def test_short_multiple_streams_and_oversize_rejected(self):
        with self.assertRaises(CaptureError):parse_capture(csv([10]*50),'x.csv')
        with self.assertRaises(CaptureError):parse_capture(csv().replace('game.exe,1','other.exe,2',1),'x.csv')
        with self.assertRaises(CaptureError):parse_capture('x'*(4*1024*1024+1),'x.csv')
        with self.assertRaises(CaptureError):parse_capture(json.dumps({'Runs':[{},{}]}),'x.json')
    def test_stutters_retained_and_first_boundary_zero_excluded(self):
        x=parse_capture(csv([0]+[10]*100+[300]),'x.csv')
        self.assertEqual(x['frames'],101);self.assertEqual(x['maximum_ms'],300)
        self.assertGreater(len(x['warnings']),1)
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.engine=create_engine('sqlite:///'+str(Path(self.tmp.name)/'test.db'),connect_args={'check_same_thread':False})
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([User(id=1,email='one@example.test',name='One',password_hash='unused'),User(id=2,email='two@example.test',name='Two',password_hash='unused')]);db.commit()
        self.user=SimpleNamespace(id=1,email='one@example.test')
        app=FastAPI();app.include_router(benchmarks);app.include_router(shares)
        def dbs():
            with Session(self.engine) as db:yield db
        app.dependency_overrides[get_db]=dbs;app.dependency_overrides[current_user]=lambda:self.user
        self.app=app;self.client=TestClient(app)
        self.envelope={'filename':'capture.csv','content':csv(),'metadata':{'game':'Fixture Game','cpu':'Fixture CPU','gpu':'Fixture GPU','resolution':'1920x1080','preset':'High','scene':'Fixture scene','os':'Windows','publication_consent':True}}
        self.snapshot={'v':1,'parts':[{'category':'CPU','name':'Fixture CPU','price':1000,'url':'https://example.test/product','image_url':''}],'game':'Fixture Game','fps':100}
    def tearDown(self):self.client.close();self.engine.dispose();self.tmp.cleanup()
    def test_preview_submission_recomputation_pending_and_duplicate(self):
        preview=self.client.post('/api/benchmarks/capture/preview',json={k:v for k,v in self.envelope.items() if k!='metadata'})
        self.assertEqual(preview.status_code,200,preview.text);self.assertFalse(preview.json()['duplicate']);self.assertNotIn('frametimes_ms',preview.json())
        self.envelope['metadata']['average_fps']=999
        first=self.client.post('/api/benchmarks/capture/submit',json=self.envelope)
        self.assertEqual(first.status_code,201,first.text);data=first.json()['submission'];self.assertEqual(data['status'],'pending');self.assertNotEqual(data['result']['average_fps'],999)
        self.assertEqual(self.client.get('/api/benchmarks/community').json()['total'],0)
        self.assertEqual(self.client.post('/api/benchmarks/capture/submit',json=self.envelope).status_code,409)
        proof=self.client.get('/api/benchmarks/submissions/'+str(data['id'])+'/capture');self.assertEqual(len(proof.json()['frametimes_ms']),1200)
        self.user=SimpleNamespace(id=2,email='two@example.test');self.assertEqual(self.client.get('/api/benchmarks/submissions/'+str(data['id'])+'/capture').status_code,403)
    def test_consent_and_authentication_required(self):
        self.envelope['metadata']['publication_consent']=False
        self.assertEqual(self.client.post('/api/benchmarks/capture/submit',json=self.envelope).status_code,422)
        del self.app.dependency_overrides[current_user]
        self.assertEqual(self.client.post('/api/benchmarks/capture/preview',json=self.envelope).status_code,401)
        self.assertEqual(self.client.post('/api/shared-builds',json=self.snapshot).status_code,401)
    def test_daily_quota_survives_auth_cleanup_and_expires(self):
        from datetime import timedelta
        from unittest.mock import patch
        from app.services import benchmark_limits,auth_limits
        from app.core.price_time import db_now
        from fastapi import HTTPException
        now=db_now()
        with Session(self.engine) as db,patch.object(benchmark_limits,'db_now',return_value=now):
            for _ in range(5):benchmark_limits.enforce(db,1,'submit',5,86400)
        with Session(self.engine) as db,patch.object(benchmark_limits,'db_now',return_value=now+timedelta(hours=6)):
            auth_limits._cleanup(db,now+timedelta(hours=6));db.commit()
            with self.assertRaises(HTTPException) as error:benchmark_limits.enforce(db,1,'submit',5,86400)
            self.assertEqual(error.exception.status_code,429);self.assertIn('Retry-After',error.exception.headers)
        with Session(self.engine) as db,patch.object(benchmark_limits,'db_now',return_value=now+timedelta(days=1,seconds=1)):
            benchmark_limits.enforce(db,1,'submit',5,86400)

    def test_file_size_and_malformed_payload(self):
        self.assertEqual(self.client.post('/api/benchmarks/capture/preview',content='x'*(8*1024*1024+1)).status_code,413)
        self.assertEqual(self.client.post('/api/benchmarks/capture/preview',json={'filename':'x.exe','content':'bad'}).status_code,422)
    def test_shared_snapshot_is_saved_immutable_public_and_revocable_by_owner(self):
        first=self.client.post('/api/shared-builds',json=self.snapshot);self.assertEqual(first.status_code,201,first.text);token=first.json()['id']
        self.assertEqual(self.client.post('/api/shared-builds',json=self.snapshot).json()['id'],token)
        self.assertEqual(len(self.client.get('/api/shared-builds/mine').json()['items']),1)
        self.snapshot['fps']=200
        public=self.client.get('/api/shared-builds/'+token).json();self.assertEqual(public['snapshot']['fps'],100);self.assertNotIn('user_id',public)
        self.user=SimpleNamespace(id=2,email='two@example.test');self.assertEqual(self.client.delete('/api/shared-builds/'+token).status_code,404)
        self.user=SimpleNamespace(id=1,email='one@example.test');self.assertEqual(self.client.delete('/api/shared-builds/'+token).status_code,204);self.assertEqual(self.client.get('/api/shared-builds/'+token).status_code,404)
    def test_unsafe_links_and_huge_snapshot_rejected(self):
        self.snapshot['parts'][0]['url']='javascript:alert(1)';self.assertEqual(self.client.post('/api/shared-builds',json=self.snapshot).status_code,422)
        self.snapshot['parts']*=33;self.assertEqual(self.client.post('/api/shared-builds',json=self.snapshot).status_code,422)
if __name__=='__main__':unittest.main()

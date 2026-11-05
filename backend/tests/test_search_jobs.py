import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db.base import Base
from app.db.models import SearchJob
from app.services.search_jobs import create_job, run_job, public_job, recover_jobs
from app.api.search_jobs import JobRequest
from fastapi import HTTPException
from pydantic import ValidationError


class SearchJobsTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.engine=create_engine('sqlite:///'+(Path(self.directory.name)/'jobs.db').as_posix())
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine)
        self.db=self.sessions()
        self.worker=patch('app.services.search_jobs.executor.submit').start()
        self.factory=patch('app.services.search_jobs.SessionLocal',self.sessions).start()

    def tearDown(self):
        patch.stopall();self.db.close();self.engine.dispose();self.directory.cleanup()

    def create(self, nonce='x'*20):
        return create_job(self.db,'calculate',{'cpu_id':1,'gpu_id':2,'game':'CS2','mode':'1080p_low'},nonce)

    def test_retry_after_lost_post_response_reuses_same_job(self):
        first=self.create();again=self.create()
        self.assertEqual(first['id'],again['id'])
        self.assertEqual(self.worker.call_count,1)
        self.assertEqual(len(list(self.db.scalars(select(SearchJob)))),1)

    def test_completed_result_survives_new_database_session(self):
        job=self.create()
        with patch('app.api.calculate.post_calculate',return_value={'budget':50000,'status':'partial','parts':[]}):
            run_job(job['id'])
        self.db.close()
        with self.sessions() as db:
            saved=public_job(db.get(SearchJob,job['id']))
        self.assertEqual(saved['status'],'completed')
        self.assertEqual(saved['result']['budget'],50000)
        self.assertEqual(saved['result']['parts'],[])

    def test_failure_is_saved_as_a_result_instead_of_closing_http_connection(self):
        job=self.create()
        with patch('app.api.calculate.post_calculate',side_effect=HTTPException(400,'Неподходящий CPU')),patch(
                'app.services.search_jobs.logger.exception'):
            run_job(job['id'])
        self.db.expire_all();saved=public_job(self.db.get(SearchJob,job['id']))
        self.assertEqual(saved['status'],'failed')
        self.assertEqual(saved['error'],'Неподходящий CPU')

    def test_queue_is_bounded_on_small_hosting(self):
        for index in range(4):self.create(str(index)*20)
        with self.assertRaises(HTTPException) as error:self.create('z'*20)
        self.assertEqual(error.exception.status_code,429)

    def test_restart_reports_interrupted_search_and_keeps_completed_results(self):
        first=self.create('a'*20);second=self.create('b'*20)
        self.db.get(SearchJob,first['id']).status='running'
        done=self.db.get(SearchJob,second['id']);done.status='completed';done.result='{"ok":true}'
        self.db.commit();recover_jobs();self.db.expire_all()
        self.assertEqual(self.db.get(SearchJob,first['id']).status,'failed')
        self.assertEqual(json.loads(self.db.get(SearchJob,second['id']).result),{'ok':True})

    def test_bad_payload_is_rejected_before_job_is_queued(self):
        with self.assertRaises(ValidationError):
            JobRequest(kind='assemble',payload={'budget':50000},client_request_id='x'*20)

    def test_http_returns_job_before_worker_finishes_and_polling_gets_result(self):
        import time
        from threading import Event
        from concurrent.futures import ThreadPoolExecutor
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.search_jobs import router
        from app.db.base import get_db
        started, release = Event(), Event()
        def calculate(*args):
            started.set()
            release.wait(3)
            return {'status':'partial','budget':50000,'parts':[]}
        def database():
            with self.sessions() as db:yield db
        app=FastAPI();app.include_router(router);app.dependency_overrides[get_db]=database
        with ThreadPoolExecutor(max_workers=1) as worker,patch('app.api.calculate.post_calculate',side_effect=calculate):
            self.worker.side_effect=lambda fn,job_id:worker.submit(fn,job_id)
            try:
                with TestClient(app) as client:
                    when=time.monotonic()
                    response=client.post('/api/search-jobs',json={'kind':'calculate','client_request_id':'http'*8,
                        'payload':{'cpu_id':1,'gpu_id':2,'game':'CS2','mode':'1080p_low','budget':50000}})
                    self.assertEqual(response.status_code,202,response.text)
                    self.assertLess(time.monotonic()-when,1)
                    self.assertTrue(started.wait(1))
                    path='/api/search-jobs/'+response.json()['id']
                    self.assertEqual(client.get(path).json()['status'],'running')
                    release.set()
                    for _ in range(30):
                        data=client.get(path).json()
                        if data['status']=='completed':break
                        time.sleep(.02)
                    self.assertEqual(data['status'],'completed',data)
                    self.assertEqual(data['result']['budget'],50000)
            finally:release.set()

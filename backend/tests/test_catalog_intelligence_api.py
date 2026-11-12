"""Public history and private discovery ownership; in-process, no working DB."""
import unittest,tempfile,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from datetime import datetime,timezone
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.db.models import Base,User,CatalogProduct,ExternalSearchJob
from app.api.account import current_user
from app.api.product_discovery import router as discovery_router
from app.api.catalog_history import router as history_router

class DiscoveryApiTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.engine=create_engine('sqlite:///'+str(Path(self.temp.name)/'test.db'));Base.metadata.create_all(self.engine);self.addCleanup(self.engine.dispose)
  self.app=FastAPI();self.app.include_router(discovery_router);self.app.include_router(history_router)
  def database():
   with Session(self.engine) as db:yield db
  self.app.dependency_overrides[get_db]=database
  self.client=TestClient(self.app);self.addCleanup(self.client.close)
  with Session(self.engine) as db:
   db.add(User(id=1,email='one@test.invalid',name='One',password_hash='unused'))
   db.add(ExternalSearchJob(id='secret-job-id',user_id=1,request_key='key',created_at=datetime.now(),status='completed',result='{"offers":[]}'))
   db.add(CatalogProduct(key='private-product',source='regard',external_key='123',payload='{}'));db.commit()
 def test_anonymous_search_requires_session(self):
  with patch('app.api.product_discovery.create_job',side_effect=AssertionError('must authenticate first')):
   self.assertEqual(self.client.post('/api/product-search',json={'model':'Ryzen 5600','category':'CPU','sources':['dns']}).status_code,401)
 def test_other_owner_cannot_read_job(self):
  from types import SimpleNamespace
  self.app.dependency_overrides[current_user]=lambda:SimpleNamespace(id=2)
  self.assertEqual(self.client.get('/api/product-search/secret-job-id').status_code,404)
 def test_owner_can_read_without_caching(self):
  from types import SimpleNamespace
  self.app.dependency_overrides[current_user]=lambda:SimpleNamespace(id=1)
  response=self.client.get('/api/product-search/secret-job-id')
  self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store')
 def test_history_without_source_rights_is_hidden(self):
  self.assertEqual(self.client.get('/api/products/private-product/price-history?days=14').status_code,404)
 def test_bad_history_range_rejected(self):
  self.assertEqual(self.client.get('/api/products/private-product/price-history?days=9').status_code,422)

if __name__=='__main__':unittest.main()

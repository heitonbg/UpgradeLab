"""The owner view stays loopback-only, token-gated and isolated from public catalogue APIs."""
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pydantic import SecretStr

from app.api.catalog_admin import router as admin_router
from app.api.catalog_history import router as public_history_router
from app.db.models import Base, CatalogAccess, CatalogDailyPrice, CatalogProduct, StoreOffer
from app.core.price_time import utc_now
from app.db import models  # noqa: F401


class CatalogAdminApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'regard.analysis.db'
        self.engine = create_engine('sqlite:///' + self.database.as_posix())
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.app = FastAPI()
        self.app.include_router(admin_router)
        self.app.include_router(public_history_router)
        self.peer = ('127.0.0.1', 54321)

        @self.app.middleware('http')
        async def use_loopback_peer_for_test(request, call_next):
            request.scope['client'] = self.peer
            return await call_next(request)

        def database():
            with Session(self.engine) as db:
                yield db

        from app.db.base import get_db
        self.app.dependency_overrides[get_db] = database
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.token = 'local-development-test-token-never-used-in-production'
        rights = {'source': 'regard', 'development': True, 'public_display': False,
                  'commercial': False, 'automatic_download': False,
                  'basis': 'Owner supplied workbook for local private analysis',
                  'owner_confirmed_by': 'test owner', 'confirmed_at': utc_now().isoformat()}
        with Session(self.engine) as db:
            db.add(CatalogAccess(source='regard', rights=json.dumps(rights), public_enabled=0, fixture=0))
            offer = StoreOffer(source='regard', name='Ryzen 5 test', category='CPU', price_rub=12000,
                               condition='new', url='https://www.regard.ru/product/123/test',
                               observed_at=utc_now().replace(tzinfo=None), origin='catalog_import', attributes='{}')
            db.add(offer)
            db.flush()
            db.add(CatalogProduct(key='regard-cpu-test', source='regard', external_key='sku:123', offer_id=offer.id,
                                  payload=json.dumps({'title': 'Ryzen 5 test', 'brand': 'AMD', 'price': '12000.00',
                                      'category': 'CPU', 'source_updated_at': utc_now().isoformat(),
                                      'availability': 'unknown', 'analysis_eligible': True,
                                      'product_url': 'https://www.regard.ru/product/123/test',
                                      'image_url': None, 'reasons': []})))
            db.add(CatalogDailyPrice(product_key='regard-cpu-test', source_day=utc_now().date().isoformat(),
                                     source='regard', price_kopecks=1200000, import_key='import-test'))
            db.commit()

    def headers(self):
        return {'X-UpgradeLab-Catalog-Admin': self.token}

    def test_disabled_without_local_admin_token(self):
        with patch('app.api.catalog_admin.settings.regard_catalog_admin_token', SecretStr('')):
            self.assertEqual(self.client.get('/api/admin/catalog/regard').status_code, 404)

    def test_wrong_admin_token_is_denied(self):
        with patch('app.api.catalog_admin.settings.regard_catalog_admin_token', SecretStr(self.token)):
            self.assertEqual(self.client.get('/api/admin/catalog/regard', headers={'X-UpgradeLab-Catalog-Admin': 'wrong'}).status_code, 403)

    def test_forwarded_loopback_header_does_not_make_remote_peer_local(self):
        self.peer = ('192.0.2.10', 54321)
        with patch('app.api.catalog_admin.settings.regard_catalog_admin_token', SecretStr(self.token)):
            response = self.client.get('/api/admin/catalog/regard', headers={
                **self.headers(), 'X-Forwarded-For': '127.0.0.1', 'X-Real-IP': '::1'})
            self.assertEqual(response.status_code, 404)

    def test_local_admin_sees_real_record_without_public_grant(self):
        with patch('app.api.catalog_admin.settings.regard_catalog_admin_token', SecretStr(self.token)):
            response = self.client.get('/api/admin/catalog/regard?q=ryzen', headers=self.headers())
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data['public_display'])
            self.assertEqual(data['catalog_product_count'], 1)
            self.assertEqual(data['linked_store_offer_count'], 1)
            self.assertEqual(data['total'], 1)
            card = data['items'][0]
            self.assertEqual(card['manufacturer'], 'AMD')
            self.assertEqual(card['price_rub'], 12000)
            self.assertEqual(card['availability'], 'unknown')
            self.assertIsNone(card['image_url'])
            self.assertEqual(card['product_url'], 'https://www.regard.ru/product/123/test')
            self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_private_history_works_only_in_admin_route(self):
        with patch('app.api.catalog_admin.settings.regard_catalog_admin_token', SecretStr(self.token)):
            response = self.client.get('/api/admin/catalog/regard/regard-cpu-test/price-history?days=14', headers=self.headers())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()['observations']), 1)
            self.assertEqual(self.client.get('/api/products/regard-cpu-test/price-history?days=14').status_code, 404)

    def test_non_analysis_database_is_rejected(self):
        ordinary = create_engine('sqlite:///' + (Path(self.temp.name) / 'ordinary.db').as_posix())
        Base.metadata.create_all(ordinary)
        from app.db.base import get_db
        def ordinary_database():
            with Session(ordinary) as db:
                yield db
        self.app.dependency_overrides[get_db] = ordinary_database
        try:
            with patch('app.api.catalog_admin.settings.regard_catalog_admin_token', SecretStr(self.token)):
                self.assertEqual(self.client.get('/api/admin/catalog/regard', headers=self.headers()).status_code, 404)
        finally:
            ordinary.dispose()

    def test_invalid_history_range_is_rejected(self):
        with patch('app.api.catalog_admin.settings.regard_catalog_admin_token', SecretStr(self.token)):
            response = self.client.get('/api/admin/catalog/regard/regard-cpu-test/price-history?days=9', headers=self.headers())
            self.assertEqual(response.status_code, 422)


if __name__ == '__main__':
    unittest.main()

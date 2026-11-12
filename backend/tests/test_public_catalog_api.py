import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.catalog_public import router
from app.api.deps import get_db
from app.db.models import Base, CatalogAccess, CatalogProduct, StoreOffer


class PublicCatalogApiTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch('app.core.price_time.utc_now', return_value=datetime(2026, 11, 10, 12, tzinfo=timezone.utc))
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine('sqlite:///' + str(Path(self.temp.name) / 'catalog.db'))
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        app = FastAPI()
        app.include_router(router)

        def database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        rights = {'source': 'regard', 'development': True, 'public_display': True,
                  'commercial': False, 'automatic_download': False,
                  'basis': 'Owner-authorized public display for the demo',
                  'owner_confirmed_by': 'Project owner', 'confirmed_at': '2026-01-01T00:00:00Z'}
        with Session(self.engine) as db:
            db.add(CatalogAccess(source='regard', rights=json.dumps(rights), public_enabled=1, fixture=0))
            for index, (name, category, availability) in enumerate([
                    ('Ryzen 5 5600', 'CPU', 'unknown'), ('RTX 5060', 'GPU', 'out_of_stock'),
                    ('Old product', 'GPU', 'unknown')]):
                payload = {'title': name, 'category': category, 'brand': 'Vendor', 'price': '12000',
                           'source_updated_at': '2026-11-10T00:00:00Z' if index == 0 else '2026-11-08T00:00:00Z', 'availability': availability,
                           'product_url': f'https://www.regard.ru/product/{1000+index}',
                           'missing_from_feed': index == 2, 'preliminary_eligible': index == 0}
                offer = StoreOffer(source='regard', url=payload['product_url'], name=name,
                                   category=category, price_rub=12000, condition='new',
                                   observed_at=datetime(2026, 11, 10 if index == 0 else 8, tzinfo=timezone.utc).replace(tzinfo=None),
                                   origin='catalog_import', attributes='{}') if index < 2 else None
                if offer:
                    db.add(offer)
                    db.flush()
                db.add(CatalogProduct(key=f'product-{index}', source='regard', external_key=str(index),
                                      payload=json.dumps(payload), offer_id=offer.id if offer else None))
            db.commit()

    def test_public_endpoint_paginates_and_keeps_unknown_availability_explicit(self):
        response = self.client.get('/api/catalog/products?page=1&page_size=1')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['total'], 2)
        self.assertEqual(len(body['items']), 1)
        self.assertEqual(body['items'][0]['availability'], 'unknown')
        self.assertEqual(body['items'][0]['product_url'], 'https://www.regard.ru/product/1000')
        self.assertTrue(body['items'][0]['preliminary_candidate'])
        unavailable = self.client.get('/api/catalog/products?page=2&page_size=1').json()['items'][0]
        self.assertEqual(unavailable['availability'], 'out_of_stock')
        self.assertFalse(unavailable['preliminary_candidate'])
        self.assertFalse(unavailable['price_fresh'])

    def test_search_and_category_filters_apply_before_pagination(self):
        body = self.client.get('/api/catalog/products?q=ryzen&category=CPU').json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['items'][0]['name'], 'Ryzen 5 5600')

    def test_public_display_permission_gate_is_default_deny(self):
        with Session(self.engine) as db:
            access = db.get(CatalogAccess, 'regard')
            access.public_enabled = 0
            db.commit()
        body = self.client.get('/api/catalog/products').json()
        self.assertEqual(body['total'], 0)
        self.assertEqual(body['items'], [])


if __name__ == '__main__':
    unittest.main()

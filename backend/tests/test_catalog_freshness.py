import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from types import SimpleNamespace
from app.services.catalog_freshness import catalog_price_state, observation_usable

class CatalogFreshnessTests(unittest.TestCase):
    def test_boundaries_and_live_isolation(self):
        now=datetime(2026,11,11,12,tzinfo=timezone.utc)
        with patch('app.core.price_time.utc_now',return_value=now):
            for hours,state,usable in [(0,'fresh',True),(24,'fresh',True),(25,'stale',True),(72,'stale',True),(73,'historical',False)]:
                with self.subTest(hours=hours):
                    row=SimpleNamespace(origin='catalog_import',source='regard',observed_at=now-timedelta(hours=hours))
                    result=catalog_price_state(row.observed_at)
                    self.assertEqual(result['price_freshness'],state)
                    self.assertEqual(observation_usable(row),usable)
                    self.assertFalse(result['purchase_ready'])
                    row.origin='product_page'
                    self.assertEqual(observation_usable(row),hours<=24)
            for value in [None,'bad',now+timedelta(minutes=6)]:
                self.assertFalse(catalog_price_state(value)['optimizer_eligibility'])

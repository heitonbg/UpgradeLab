"""Catalog observations may support estimates, never purchase verification."""
from datetime import timedelta
from app.core.config import settings
from app.core.price_time import is_fresh, OFFER_TTL, OBSERVATION_SKEW, iso_utc

def catalog_price_state(value):
    fresh = is_fresh(value, OFFER_TTL, inclusive=True, future_tolerance=OBSERVATION_SKEW)
    usable = is_fresh(value, timedelta(hours=settings.catalog_preliminary_hours), inclusive=True, future_tolerance=OBSERVATION_SKEW)
    return {'source_price_at': iso_utc(value), 'price_freshness': 'fresh' if fresh else 'stale' if usable else 'historical',
            'optimizer_eligibility': usable, 'purchase_ready': False}

def observation_usable(row):
    if row.origin == 'catalog_import' and row.source == 'regard':
        return catalog_price_state(row.observed_at)['optimizer_eligibility']
    return is_fresh(row.observed_at, OFFER_TTL, inclusive=True, future_tolerance=OBSERVATION_SKEW)

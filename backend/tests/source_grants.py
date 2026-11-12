"""Explicit synthetic permission records for mocked transports, never production grants."""
import json
from unittest.mock import patch
from app.core.config import settings
from app.core.stores import STORES

def grant_network(case):
    live=patch.object(settings,'offers_live_search',True);live.start();case.addCleanup(live.stop)
    grants={s:{'automatic_network':True,'public_display':True,'basis':'Synthetic offline transport fixture only',
        'confirmed_by':'Test fixture','confirmed_at':'2020-01-01T00:00:00Z'} for s in STORES if s!='avito'}
    context=patch.object(settings,'source_permissions',json.dumps(grants));context.start();case.addCleanup(context.stop)

"""Operator-owned attestation; default deny. Public input cannot grant network access."""
import json
from pydantic import BaseModel,Field
from app.core.config import settings
from app.core.price_time import past_utc
class NetworkGrant(BaseModel):
    automatic_network:bool=False
    public_display:bool=False
    basis:str=Field(min_length=8,max_length=1000)
    confirmed_by:str=Field(min_length=2,max_length=200)
    confirmed_at:str
    model_config={'extra':'forbid'}

def network_allowed(source):
    if source in ('avito','upgradelab'):return False
    try:
        grant=NetworkGrant.model_validate(json.loads(settings.source_permissions).get(source,{}))
        return bool(grant.automatic_network and grant.public_display and past_utc(grant.confirmed_at))
    except (ValueError,TypeError):return False

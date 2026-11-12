"""Tri-state, provenance-bearing hardware evidence; no lookalike PSU revisions."""
import json,re
from pydantic import BaseModel,Field
from typing import Literal
class Slot(BaseModel):
    kind:Literal['M.2','SATA']
    interfaces:list[Literal['NVMe','SATA']]
    sizes:list[int]=Field(default_factory=list)
    available:int=Field(ge=0,le=16)
    sockets:list[str]=Field(default_factory=list)
    model_config={'extra':'forbid'}
class StorageSlots(BaseModel):
    applies_to:str=Field(min_length=2,max_length=300)
    slots:list[Slot]=Field(max_length=16)
    basis:str=Field(min_length=3,max_length=500)
    source_url:str=Field(min_length=3,max_length=1000)
    model_config={'extra':'forbid'}
class Connectors(BaseModel):
    applies_to:str=Field(min_length=2,max_length=300)
    atx24:bool
    eps_4plus4:int=Field(ge=0,le=8)
    pcie_6plus2:int=Field(ge=0,le=8)
    basis:str=Field(min_length=3,max_length=500)
    source_url:str=Field(min_length=3,max_length=1000)
    model_config={'extra':'forbid'}

def slots(board):
    try:
        evidence=StorageSlots.model_validate(json.loads(board.attributes).get('storage_slots'))
        return evidence if ' '.join(evidence.applies_to.casefold().split())==' '.join(board.name.casefold().split()) else None
    except (ValueError,TypeError):return None

def storage_status(board,drive):
    from app.services.component_quality import quality_check
    from app.services.storage_compatibility import nvme_board_evidence
    quality=quality_check(drive)[0]
    if not quality:return {'status':'unknown','reason':'storage_model_unknown'}
    data=slots(board);interface=quality['interface'];size=2280 if interface=='NVMe' else None
    if data is None and 'storage_slots' in json.loads(board.attributes):return {'status':'unknown','reason':'invalid_storage_slot_evidence'}
    if data:
        candidates=[s for s in data.slots if interface in s.interfaces and (size is None or s.kind=='M.2' and size in s.sizes)]
        if not candidates:return {'status':'incompatible','reason':'storage_interface_or_size_mismatch'}
        if not any(s.available>0 for s in candidates):return {'status':'incompatible','reason':'no_free_storage_slot'}
        from app.services.builds import board_socket
        if not any(not s.sockets or board_socket(board.name) in s.sockets for s in candidates):return {'status':'incompatible','reason':'storage_platform_restriction'}
        return {'status':'compatible','reason':'documented_slot','evidence':data.model_dump()}
    raw=json.loads(board.attributes)
    if interface=='NVMe' and raw.get('nvme_2280') is False:return {'status':'incompatible','reason':'nvme_explicitly_unsupported'}
    if interface=='NVMe' and nvme_board_evidence(board):return {'status':'compatible','reason':'existing_reviewed_nvme_evidence'}
    return {'status':'unknown','reason':'storage_slot_evidence_missing'}

def psu_status(offer,cpu=None,gpu=None):
    from app.services.component_quality import quality_check
    from app.services.assembly_policy import psu_requirement
    quality,reason=quality_check(offer)
    if not quality:
        revision=bool(re.search(r'\b(?:V[2-9]|REV[. ]*[2-9])\b',offer.name,re.I))
        return {'status':'unknown','reason':'psu_revision_unknown' if revision else 'psu_model_unknown','detail':reason}
    if cpu and gpu and quality['watts']<psu_requirement(cpu,gpu):return {'status':'incompatible','reason':'psu_insufficient_power'}
    try:c=Connectors.model_validate(json.loads(offer.attributes).get('power_connectors'))
    except (ValueError,TypeError):return {'status':'unknown','reason':'psu_connectors_unknown','watts':quality['watts']}
    if ' '.join(c.applies_to.casefold().split())!=' '.join(offer.name.casefold().split()):return {'status':'unknown','reason':'psu_connector_profile_model_mismatch'}
    if not c.atx24 or c.eps_4plus4<1 or c.pcie_6plus2<1:return {'status':'incompatible','reason':'psu_connectors_insufficient'}
    # GPU-specific connector requirements are not derivable from a model name.
    requirements=json.loads(offer.attributes).get('system_connector_requirements')
    if requirements is None:return {'status':'unknown','reason':'gpu_connector_requirements_unknown','watts':quality['watts']}
    if not isinstance(requirements,dict) or not isinstance(requirements.get('pcie_6plus2'),int) or not requirements.get('basis'):
        return {'status':'unknown','reason':'gpu_connector_requirements_unknown'}
    if gpu is not None and (requirements.get('gpu_model')!=gpu.name or requirements.get('gpu_vram')!=getattr(gpu,'vram',None)):return {'status':'unknown','reason':'gpu_connector_requirements_unknown'}
    if c.pcie_6plus2<requirements['pcie_6plus2']:return {'status':'incompatible','reason':'psu_connectors_insufficient'}
    return {'status':'compatible','reason':'documented_power_and_connectors','evidence':c.model_dump()}

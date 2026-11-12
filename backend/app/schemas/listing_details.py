"""Optional, category-specific seller declarations; never trusted profile input."""
from typing import Literal
from pydantic import BaseModel,Field,create_model,field_validator,model_validator
from app.services.cities import BY_ID
class Specs(BaseModel):
    model_config={'extra':'forbid','str_max_length':120}
    @field_validator('*',mode='before')
    @classmethod
    def plain(cls,v):
        if isinstance(v,str) and any(c in v for c in ('<','>','\x00')):raise ValueError('Нужен обычный текст')
        return v
def number(maximum):return (int|None,Field(default=None,ge=1,le=maximum,strict=True))
text=(str|None,None)
FIELDS={
 'CPU':dict(manufacturer=text,model=text,socket=text,generation=text,integrated_graphics=(bool|None,None)),
 'GPU':dict(gpu_manufacturer=text,model=text,board_manufacturer=text,vram=number(128),length_mm=number(700),power_connectors=text),
 'motherboard':dict(manufacturer=text,model=text,revision=text,socket=text,chipset=text,ram_type=(Literal['DDR3','DDR4','DDR5']|None,None),form_factor=(Literal['ATX','mATX','Mini-ITX','EATX']|None,None),storage_interfaces=(list[Literal['SATA','NVMe']],Field(default_factory=list,max_length=2)),m2_sizes=(list[Literal[2230,2242,2260,2280,22110]],Field(default_factory=list,max_length=5)),m2_free_slots=(int|None,Field(default=None,ge=0,le=8,strict=True))),
 'memory':dict(model=text,ram_type=(Literal['DDR3','DDR4','DDR5']|None,None),capacity_gb=number(4096),modules=number(8),frequency_mhz=number(16000),module_type=(Literal['DIMM','SO-DIMM','RDIMM','ECC']|None,None)),
 'storage':dict(manufacturer=text,model=text,revision=text,capacity_gb=number(100000),interface=(Literal['SATA','NVMe']|None,None),form_factor=(Literal['M.2','2.5','mSATA','external']|None,None),m2_size=(Literal[2230,2242,2260,2280,22110]|None,None)),
 'psu':dict(manufacturer=text,model=text,revision=text,watts=number(3000),form_factor=(Literal['ATX','SFX','SFX-L']|None,None),power_connectors=text),
 'case':dict(manufacturer=text,model=text,form_factor=text,board_formats=(list[Literal['ATX','mATX','Mini-ITX','EATX']],Field(default_factory=list,max_length=4)),psu_formats=(list[Literal['ATX','SFX','SFX-L']],Field(default_factory=list,max_length=3)),max_gpu_length_mm=number(900),max_cooler_height_mm=number(400)),
 'cooler':dict(model=text,sockets=(list[Literal['AM4','AM5','LGA1151','LGA1200','LGA1700','LGA1851']],Field(default_factory=list,max_length=6)),height_mm=number(400),cooling_type=(Literal['air','liquid']|None,None))
}
MODELS={category:create_model(category.title()+'SellerSpecs',__base__=Specs,**fields) for category,fields in FIELDS.items()}
def validate_characteristics(category,value):
    if not value:return {}
    if category not in MODELS:raise ValueError('Сначала выберите категорию')
    return MODELS[category].model_validate(value).model_dump(exclude_none=True,exclude_defaults=True)

class SellerDelivery(BaseModel):
    mode:Literal['unknown','meetup','pickup','cities','russia']='cities'
    city_ids:list[str]=Field(default_factory=list,max_length=100)
    cost_rub:int|None=Field(default=None,ge=0,le=1000000,strict=True)
    terms:str=Field(default='',max_length=500)
    model_config={'extra':'forbid'}
    @field_validator('city_ids')
    @classmethod
    def known(cls,value):
        if any(c not in BY_ID for c in value):raise ValueError('Неизвестный город доставки')
        return list(dict.fromkeys(value))
    @model_validator(mode='after')
    def rules(self):
        if self.mode=='cities' and not self.city_ids:raise ValueError('Выберите город доставки')
        if self.mode not in ('cities','russia') and (self.city_ids or self.cost_rub is not None):raise ValueError('Стоимость отправки указывается только для доставки')
        return self

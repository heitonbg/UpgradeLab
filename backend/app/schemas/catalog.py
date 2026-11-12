"""Explicit, versioned column mappings. Schema files are operator-owned JSON."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator,field_validator
from app.core.stores import STORES
from app.schemas.geography import GeoEvidence

FIELDS={'source_id','external_product_id','sku','vendor_code','brand','title','category','model','description',
        'price','currency','availability','quantity','product_url','image_url','source_updated_at'}
ATTRS={'socket','ram_type','capacity_gb','modules','watts','form_factor','interface','sockets','board_formats','psu_formats'}

class CatalogSchema(BaseModel):
    source: str
    version: str = Field(min_length=1,max_length=50)
    input_adapter: Literal['tabular','regard-native-v1'] = 'tabular'
    source_utc_offset_minutes: int = Field(default=180,ge=-720,le=840)
    format: Literal['csv','xlsx']
    columns: dict[str,str]
    attributes: dict[str,str] = Field(default_factory=dict)
    geography:GeoEvidence|None=None
    technical:dict=Field(default_factory=dict)
    header_row: int = Field(default=1,ge=1,le=100)
    sheet: str | None = Field(default=None,max_length=100)
    encoding: Literal['utf-8','utf-8-sig','cp1251'] = 'utf-8-sig'
    delimiter: Literal[',',';','\t'] = ';'
    decimal_separator: Literal['.',','] = ','
    thousands_separator: Literal[' ','.',',','none'] = ' '
    currency: str | None = None
    categories: dict[str,str]
    availability: dict[str,Literal['in_stock','out_of_stock','unknown']]
    date_format: str | None = Field(default=None,max_length=80)
    complete: bool = False
    fixture: bool = False
    price_basis: Literal['ordinary'] = 'ordinary'
    model_config={'extra':'forbid'}
    @field_validator('technical')
    @classmethod
    def technical_contract(cls,value):
        from app.services.technical_evidence import StorageSlots,Connectors
        if not set(value).issubset({'storage_slots','power_connectors','system_connector_requirements'}):
            raise ValueError('Недопустимые технические поля')
        if 'storage_slots' in value:StorageSlots.model_validate(value['storage_slots'])
        if 'power_connectors' in value:Connectors.model_validate(value['power_connectors'])
        if 'system_connector_requirements' in value:
            req=value['system_connector_requirements']
            if not isinstance(req,dict) or set(req)-{'pcie_6plus2','basis','source_url','gpu_model','gpu_vram'} or type(req.get('pcie_6plus2')) is not int or not 0<=req['pcie_6plus2']<=8 or not req.get('basis') or not req.get('gpu_model') or type(req.get('gpu_vram')) is not int or req['gpu_vram']<=0:
                raise ValueError('Требования разъёмов требуют точной модели GPU и основания')
        return value

    @model_validator(mode='after')
    def valid_schema(self):
        if self.input_adapter=='regard-native-v1' and (self.source!='regard' or self.format!='xlsx' or self.fixture):raise ValueError('invalid_regard_adapter')
        if self.source not in STORES:raise ValueError('unknown_source')
        if not {'title','price'}.issubset(self.columns) or not set(self.columns).issubset(FIELDS):
            raise ValueError('invalid_columns')
        if not set(self.attributes).issubset(ATTRS):raise ValueError('invalid_attributes')
        if not set(self.categories.values()).issubset({'CPU','GPU','memory','motherboard','storage','psu','case','cooler'}):
            raise ValueError('invalid_categories')
        if self.decimal_separator==self.thousands_separator:raise ValueError('ambiguous_separators')
        return self

class CatalogRights(BaseModel):
    source: str
    development: bool = False
    public_display: bool = False
    commercial: bool = False
    automatic_download: bool = False
    basis: str = Field(min_length=8,max_length=1000)
    owner_confirmed_by: str = Field(min_length=2,max_length=200)
    confirmed_at: str
    model_config={'extra':'forbid'}

"""Shared geographic query and explicitly sourced location evidence."""
from typing import Literal
from datetime import datetime
from pydantic import BaseModel,Field,field_validator,model_validator
from app.services.cities import BY_ID

class GeoQuery(BaseModel):
    city_id:str|None=None
    geo_mode:Literal['all','local','delivery']='all'
    max_price:int|None=Field(default=None,gt=0,le=100000000)
    limit:int=Field(default=100,ge=1,le=200)
    @field_validator('city_id')
    @classmethod
    def city(cls,value):
        if value is not None and value not in BY_ID:raise ValueError('Неизвестный город')
        return value
    @model_validator(mode='after')
    def city_required(self):
        if self.geo_mode!='all' and not self.city_id:raise ValueError('Выберите город для локального поиска или доставки')
        return self

class DeliveryEvidence(BaseModel):
    mode:Literal["unknown","meetup","pickup","cities","russia"]="cities"
    terms:str=Field(default="",max_length=500)
    city_ids:list[str]=Field(default_factory=list,max_length=100)
    cost_rub:int|None=Field(default=None,ge=0,le=1000000)
    checked_at:datetime
    kind:Literal['store_confirmed','seller_declared']
    basis:str=Field(min_length=3,max_length=500)
    @field_validator('city_ids')
    @classmethod
    def known_cities(cls,value):
        if any(v not in BY_ID for v in value):raise ValueError('Неизвестный город доставки')
        return list(dict.fromkeys(value))
    model_config={'extra':'forbid'}

class GeoEvidence(BaseModel):
    city_id:str|None=None
    location_kind:Literal['store_stock','seller_declared','unknown']='unknown'
    availability:Literal['in_stock','seller_declared','unknown','unavailable']='unknown'
    checked_at:datetime|None=None
    basis:str|None=Field(default=None,max_length=500)
    delivery:DeliveryEvidence|None=None
    @field_validator('city_id')
    @classmethod
    def known_city(cls,value):return GeoQuery.city(value)
    model_config={'extra':'forbid'}

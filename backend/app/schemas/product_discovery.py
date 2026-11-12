"""Only product-search parameters may leave the backend; no seller contacts."""
import re
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict,field_validator
from app.schemas.offers import Category
class DiscoveryQuery(BaseModel):
    model_config=ConfigDict(extra='forbid')
    model:str=Field(min_length=2,max_length=100)
    category:Category
    max_price:int|None=Field(default=None,ge=1,le=10000000)
    city_id:str|None=Field(default=None,max_length=100)
    sources:list[Literal['avito','dns','citilink','ozon','wb']]=Field(min_length=1,max_length=5)
    condition:Literal['new','used','any']='any'
    @field_validator('model')
    @classmethod
    def product_only(cls,value):
        if re.search(r'https?://|@|(?:\+?\d[\s()-]*){10,}|[<>\r\n]',value,re.I):raise ValueError('Введите модель без контактов, адресов и ссылок')
        value=' '.join(value.split())
        if len(value)<2:raise ValueError('Укажите модель')
        return value
    @field_validator('city_id')
    @classmethod
    def known_city(cls,value):
        if value:
            from app.services.cities import BY_ID
            if value not in BY_ID:raise ValueError('Неизвестный город')
        return value
class DiscoveryUrls(BaseModel):
    model_config=ConfigDict(extra='forbid')
    urls:list[str]=Field(default_factory=list,max_length=10)

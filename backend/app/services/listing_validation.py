import re
from fastapi import HTTPException
from app.db.models import Hardware
from app.services.offers import signature, consistent_hardware_title, component_listing

def validate_model(db, payload):
    if not payload.hardware_id:
        return
    hardware=db.get(Hardware,payload.hardware_id)
    category={'RAM':'memory'}.get(hardware.type,hardware.type) if hardware else None
    if hardware is None or category!=payload.category:
        raise HTTPException(422,'Модель не соответствует категории объявления')
    if category == 'memory' and re.sub(r'\W','',payload.title.casefold()) != re.sub(r'\W','',hardware.name.casefold()):
        raise HTTPException(422,'Название RAM должно соответствовать выбранной модели каталога')
    if category == 'GPU' and re.search(r'laptop|mobile|max-q|ноутбук',payload.title,re.I):
        raise HTTPException(422,'Мобильная GPU не соответствует настольной модели каталога')
    if category in ('CPU','GPU') and (
        not component_listing(payload.title) or
        not signature(payload.title,category) or
        signature(payload.title,category)!=signature(hardware.name,category) or
        not consistent_hardware_title(payload.title,hardware,category)):
        raise HTTPException(422,'Название объявления не соответствует выбранной модели')


def seller_availability(listing):
    from datetime import timedelta
    from app.core.price_time import is_fresh
    # Independent marketplace policy, not a store page confirmation.
    if listing.publication_status != 'active' or listing.condition == 'Неисправное':
        return 'not_available'
    if listing.availability_confirmed_at is None:
        return 'not_confirmed'
    return 'seller_declared' if is_fresh(listing.availability_confirmed_at,timedelta(hours=24)) else 'expired'

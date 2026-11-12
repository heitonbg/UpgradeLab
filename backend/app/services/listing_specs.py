"""Normalize seller declarations against existing catalogues, without granting trust."""
import json,re,hashlib
from types import SimpleNamespace
from sqlalchemy import select
from fastapi import HTTPException
from app.db.models import Hardware,StoreOffer,CatalogProduct
from app.services.listing_validation import validate_model
from app.services.component_quality import quality_check
from app.services.offers import title_category,model_signatures
from app.services.storage_compatibility import nvme_board_evidence

def canonical(value):return ' '.join(str(value).casefold().split())
def reference_fields(db,listing):
    from app.services.catalog_access import filter_catalog
    refs=list(db.scalars(select(StoreOffer).join(CatalogProduct,CatalogProduct.offer_id==StoreOffer.id).where(StoreOffer.category==listing.category,StoreOffer.name==listing.title)))
    refs=filter_catalog(db,refs)
    allowed={'socket','ram_type','form_factor','storage_slots','power_connectors','system_connector_requirements','nvme_2280','sockets','board_formats','psu_formats','length_mm','height_mm','max_gpu_length_mm','max_cooler_height_mm'}
    variants=[]
    for ref in refs:
        try:data={k:v for k,v in json.loads(ref.attributes).items() if k in allowed}
        except (ValueError,TypeError):continue
        relevant={'CPU':{'socket'},'GPU':{'length_mm'},'motherboard':{'socket','ram_type','form_factor','storage_slots','nvme_2280'},'memory':{'ram_type'},'storage':{'form_factor'},'psu':{'form_factor','power_connectors','system_connector_requirements'},'case':{'board_formats','psu_formats','max_gpu_length_mm','max_cooler_height_mm'},'cooler':{'sockets','height_mm'}}
        data={k:v for k,v in data.items() if k in relevant.get(listing.category,set())}
        if data:variants.append(data)
    if not variants:return {},False
    if any(v!=variants[0] for v in variants[1:]):return {},True
    return variants[0],False

def assess_listing(db,listing):
    declared=listing.characteristics or {};missing=[];conflicts=[];catalog={};attrs={}
    category=listing.category
    inferred=title_category(listing.title)
    if inferred and inferred!=category:conflicts.append('Название не соответствует категории')
    for field in ('socket','ram_type','capacity_gb','modules','watts','form_factor','sockets','board_formats','psu_formats','length_mm','height_mm','max_gpu_length_mm','max_cooler_height_mm'):
        if field in declared:attrs[field]=declared[field]
    if declared.get('module_type') in ('SO-DIMM','RDIMM','ECC'):conflicts.append('Тип памяти не подходит для действующего настольного подбора')
    if category in ('memory','motherboard'):
        stated=set(re.findall(r'DDR[345]',listing.title.upper()))
        if len(stated)>1 or stated and declared.get('ram_type') and declared['ram_type'] not in stated:conflicts.append('Тип RAM противоречит названию')
    h=db.get(Hardware,listing.hardware_id) if listing.hardware_id else None
    if h:
        try:validate_model(db,listing)
        except HTTPException:conflicts.append('Модель Hardware не соответствует объявлению')
        if category in ('CPU','GPU'):
            if declared.get('model'):
                try:validate_model(db,SimpleNamespace(hardware_id=listing.hardware_id,category=category,title=declared['model']))
                except HTTPException:conflicts.append('Полная модель в характеристиках противоречит Hardware')
            other='GPU' if category=='CPU' else 'CPU'
            if model_signatures(listing.title,other):conflicts.append('Название содержит несколько разных комплектующих')
        if category=='CPU':
            catalog={'model':h.name,'socket':h.socket}
            if declared.get('socket') and h.socket and declared['socket']!=h.socket:conflicts.append('Сокет противоречит Hardware')
            if declared.get('manufacturer') in ('AMD','Intel') and declared['manufacturer'].casefold() not in h.name.casefold():conflicts.append('Производитель CPU противоречит Hardware')
        elif category=='GPU':
            catalog={'model':h.name,'vram':h.vram}
            sizes={int(n) for n in re.findall(r'\b(\d+)\s*(?:gb|гб)\b',listing.title,re.I)}
            if declared.get('vram') is not None:sizes.add(declared['vram'])
            if not sizes:missing.append('Укажите VRAM для однозначного варианта GPU')
            elif sizes!={h.vram}:conflicts.append('VRAM противоречит Hardware')
        elif category=='memory':
            catalog={'model':h.name,'ram_type':h.ram_type,'capacity_gb':h.ram_capacity_gb}
            for key in ('ram_type','capacity_gb'):
                if declared.get(key) and catalog.get(key) and declared[key]!=catalog[key]:conflicts.append('Характеристики RAM противоречат каталогу')
                if catalog.get(key):attrs.setdefault(key,catalog[key])
    elif category in ('CPU','GPU'):missing.append('Не выбрана однозначная модель Hardware')
    trusted,ambiguous=reference_fields(db,listing)
    if ambiguous:conflicts.append('Доверенные технические профили противоречат друг другу')
    for key in ('socket','ram_type','form_factor'):
        if declared.get(key) and trusted.get(key) and declared[key]!=trusted[key]:conflicts.append('Характеристики противоречат доверенному профилю: '+key)
    attrs.update(trusted)
    if category=='memory':
        if not all(attrs.get(k) for k in ('ram_type','capacity_gb','modules')):missing.append('Не хватает типа, объёма или числа физических модулей RAM')
        if attrs.get('modules') not in (None,1,2):missing.append('Текущий подбор поддерживает один или два модуля')
    candidate=SimpleNamespace(name=listing.title,category=category,condition='new' if listing.condition=='Новое' else 'used',source='upgradelab',attributes=json.dumps(attrs,ensure_ascii=False),url='/?tab=marketplace')
    if category=='memory':
        from app.services.automatic_builds import memory_configuration
        if all(attrs.get(k) for k in ('ram_type','capacity_gb','modules')) and memory_configuration(candidate) is None:conflicts.append('Конфигурация RAM противоречит названию или типу модуля')
    if category=='motherboard':
        from app.services.builds import board_socket
        reviewed=nvme_board_evidence(SimpleNamespace(name=listing.title,attributes=json.dumps(trusted)))
        if not trusted and not reviewed:missing.append('Нет доверенного технического профиля платы')
        if reviewed:
            socket=board_socket(listing.title);ram='DDR5' if socket=='AM5' else 'DDR4'
            catalog.update(socket=socket,ram_type=ram)
            if declared.get('socket') and declared['socket']!=socket:conflicts.append('Сокет противоречит проверенной модели платы')
            if declared.get('ram_type') and declared['ram_type']!=ram:conflicts.append('Тип RAM противоречит проверенной модели платы')
            attrs.setdefault('socket',socket);attrs.setdefault('ram_type',ram)
        if not attrs.get('socket') or not attrs.get('ram_type'):missing.append('Неизвестен сокет или тип RAM платы')
        if declared.get('m2_free_slots')==0:attrs['nvme_2280']=False;attrs.pop('storage_slots',None)
    elif category in ('storage','psu','cooler'):
        if category=='psu' and declared.get('revision') and canonical(declared['revision']) not in canonical(listing.title):missing.append('Ревизия PSU не подтверждена полным названием')
        if category=='storage' and declared.get('m2_size') not in (None,2280):
            missing.append('Размер M.2 не подтверждён существующим профилем 2280')
        quality,reason=quality_check(candidate,(declared.get('sockets') or ['AM4'])[0] if category=='cooler' else None)
        if quality:
            catalog.update({k:v for k,v in quality.items() if k in ('model','watts','capacity_gb','interface','form_factor','sockets','cooling_class')})
            for key in ('watts','capacity_gb','interface'):
                if declared.get(key) is not None and quality.get(key) is not None and declared[key]!=quality[key]:conflicts.append('Заявленные характеристики противоречат профилю: '+key)
            if category=='psu' and not trusted.get('power_connectors'):missing.append('Разъёмы PSU не подтверждены доверенным профилем')
        else:missing.append(reason or 'Модель не подтверждена')
    elif category=='case':
        from app.services.gaming_selection import is_case_offer
        if not is_case_offer(candidate):missing.append('Не распознана модель корпуса')
        if not attrs.get('board_formats'):missing.append('Не указаны форм-факторы плат для корпуса')
    elif category not in ('CPU','GPU','memory'):missing.append('Не выбрана поддерживаемая категория')
    eligible=not missing and not conflicts
    status='contradictory' if conflicts else 'insufficient_data' if missing else 'trusted_profile' if trusted else 'catalog_matched' if catalog else 'seller_declared'
    assessment={'state':status,'optimizer_eligible':eligible,'declared_fields':declared,'catalog_fields':catalog,'trusted_fields':trusted,
        'missing':missing,'contradictions':conflicts,'reason':'Противоречивые характеристики' if conflicts else 'Недостаточно данных для проверки совместимости' if missing else 'Данные подходят для предварительного подбора; цена заявлена продавцом'}
    return {'assessment':assessment,'attributes':attrs,'fingerprint':hashlib.sha256(json.dumps([listing.title,listing.category,listing.hardware_id,declared,trusted],sort_keys=True,ensure_ascii=False).encode()).hexdigest()}

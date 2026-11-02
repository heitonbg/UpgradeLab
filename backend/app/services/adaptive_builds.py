"""Try complete compatible platforms and redistribute budget before giving up."""
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models import Hardware
from app.services.automatic_builds import assemble_auto, board_matches, memory_matches
from app.services.offers import available_offers


def platform_candidates(payload):
    configurations = [(payload.socket, payload.ram_type)]
    if payload.allow_platform_change and payload.selected_cpu_id is None:
        configurations += [('AM4','DDR4'),('LGA1700','DDR4'),('LGA1200','DDR4'),('AM5','DDR5')]
        if payload.budget <= 40000:
            configurations += [('LGA1151','DDR4')]
    return [payload.model_copy(update={'socket':socket,'ram_type':ram})
            for socket,ram in dict.fromkeys(configurations)]


def solve_profiles(payload, db, allowed_offer_ids, preferred_source=None, observed=False):
    hardware = {item.id:item for item in db.scalars(select(Hardware))}
    rows = [row for row in available_offers(db,payload.price_sources,include_unavailable=observed) if row.id in allowed_offer_ids]
    profiles = []
    for profile in platform_candidates(payload):
        if (any(row.category=='CPU' and row.hardware_id in hardware and hardware[row.hardware_id].socket==profile.socket for row in rows)
                and any(row.category=='motherboard' and board_matches(row,profile) for row in rows)
                and any(row.category=='memory' and memory_matches(row,profile) for row in rows)):
            profiles.append(profile)
    last_error = HTTPException(400,'Нужно найти совместимый комплект CPU, платы и памяти либо более доступные детали для полной сборки.')
    all_candidates=[]
    def rank(result):
        return (result.get('preferred_parts_count',0) if preferred_source else 0,
                result['fps'],-result['total_price'],result['actual_config']['socket']==payload.socket)
    for flexible in (False,True):
        candidates = []
        for profile in profiles:
            try:
                result = assemble_auto(profile,db,allowed_offer_ids=allowed_offer_ids,
                                       preferred_source=preferred_source,flexible=flexible,observed=observed)
            except HTTPException as error:
                if error.status_code != 400:raise
                last_error=error
                continue
            changes=[]
            if profile.socket!=payload.socket or profile.ram_type!=payload.ram_type:
                changes.append(f'Платформа изменена с {payload.socket}/{payload.ram_type} на {profile.socket}/{profile.ram_type}: подобраны совместимые CPU, плата и память.')
            if flexible:
                changes.append('Бюджет перераспределён между деталями. CPU и GPU подбираются после учёта стоимости всего остального ПК.')
            for variant in [result,*result.get('alternatives',[])]:
                variant['selection_changes']=changes
                variant['preferred_source']=preferred_source
                if changes:
                    variant['compatibility_notes']=[*changes,*variant['compatibility_notes']]
            candidates.append(result)
        if candidates:
            all_candidates.extend(candidates)
            if not preferred_source or max(result.get('preferred_parts_count',0) for result in candidates)==8:
                return max(all_candidates,key=rank)
    if all_candidates:
        return max(all_candidates,key=rank)
    # A preferred quote can cost more than a non-preferred quote for the same
    # CPU/GPU. If that blocks every PC, retry the full budget with cheaper quotes.
    if preferred_source:
        result=solve_profiles(payload,db,allowed_offer_ids,preferred_source=None,observed=observed)
        for variant in [result,*result.get('alternatives',[])]:
            variant['preferred_source']=preferred_source
            variant['preferred_parts_count']=sum(part.get('price_source')=='Avito' for part in variant['parts'])
        return result
    raise last_error

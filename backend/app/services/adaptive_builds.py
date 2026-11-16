"""Try complete compatible platforms and redistribute budget before giving up."""
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models import Hardware
from app.services.automatic_builds import assemble_auto, board_matches, memory_matches, memory_candidates
from app.services.offers import available_offers


def platform_candidates(payload):
    automatic_socket = payload.socket == "AUTO"
    if automatic_socket:
        configurations = [("AM4", "DDR4"), ("LGA1700", "DDR4"),
                          ("LGA1700", "DDR5"), ("LGA1200", "DDR4"),
                          ("AM5", "DDR5")]
        if payload.budget <= 40000:
            configurations.append(("LGA1151", "DDR4"))
        if payload.ram_type != "AUTO":
            configurations = [pair for pair in configurations if pair[1] == payload.ram_type]
    elif payload.ram_type == "AUTO":
        configurations = [(payload.socket, "DDR4"), (payload.socket, "DDR5")]
    else:
        configurations = [(payload.socket, payload.ram_type)]
        if payload.allow_platform_change and payload.selected_cpu_id is None:
            configurations += [("AM4", "DDR4"), ("LGA1700", "DDR4"),
                               ("LGA1200", "DDR4"), ("AM5", "DDR5")]
            if payload.budget <= 40000:
                configurations.append(("LGA1151", "DDR4"))
        if payload.selection_policy == "target_fps":
            if payload.allow_platform_change and payload.selected_cpu_id is None and payload.ram_type == "DDR5":
                configurations += [("AM5", "DDR5"), ("LGA1700", "DDR5")]
            configurations = [pair for pair in configurations if pair[1] == payload.ram_type]
    return [payload.model_copy(update={"socket": socket, "ram_type": ram})
            for socket, ram in dict.fromkeys(configurations)]


def solve_profiles(payload, db, allowed_offer_ids, preferred_source=None, observed=False):
    hardware = {item.id:item for item in db.scalars(select(Hardware))}
    rows = [row for row in available_offers(db,payload.price_sources,include_unavailable=observed) if row.id in allowed_offer_ids]
    profiles = []
    for profile in platform_candidates(payload):
        if (any(row.category=='CPU' and row.hardware_id in hardware and hardware[row.hardware_id].socket==profile.socket for row in rows)
                and any(row.category=='motherboard' and board_matches(row,profile) for row in rows)
                and any(row.category=='memory' and memory_matches(candidate,profile)
                        for row in rows for candidate in memory_candidates([row]))):
            profiles.append(profile)
    last_error = HTTPException(400,'Нужно найти совместимый комплект CPU, платы и памяти либо более доступные детали для полной сборки.')
    all_candidates=[]
    def rank(result):
        if payload.workload=='gaming' and payload.selection_policy=='target_fps':
            from app.services.target_selection import target_result_rank
            return target_result_rank(result,payload.target_fps)
        return (result.get('preferred_parts_count',0) if preferred_source else 0,
                (-result['total_price'] if payload.objective=='economy' else result.get('selection_score',result['fps'])),-result['total_price'],result['actual_config']['socket']==payload.socket)
    if payload.workload == "gaming" and payload.selection_policy == "target_fps":
        platform_variants = []
        for profile in profiles:
            try:
                result = assemble_auto(profile, db, allowed_offer_ids=allowed_offer_ids,
                                       preferred_source=None, flexible=True, observed=observed)
            except HTTPException as error:
                if error.status_code != 400:
                    raise
                last_error = error
                continue
            changes = []
            if profile.socket != payload.socket or profile.ram_type != payload.ram_type:
                changes.append(
                    f"Подобрана совместимая платформа {profile.socket} / {profile.ram_type}; "
                    "CPU, материнская плата и комплект памяти показаны вместе.")
            changes.append("Бюджет распределён между всеми деталями; целевой FPS остаётся прогнозом модели.")
            for variant in [result, *result.get("alternatives", [])]:
                item = dict(variant)
                item.pop("alternatives", None)
                item["selection_changes"] = list(dict.fromkeys([*item.get("selection_changes", []), *changes]))
                item["compatibility_notes"] = list(dict.fromkeys([*item.get("compatibility_notes", []), *changes]))
                item["preferred_source"] = None
                item["selection_policy"] = "target_fps"
                parts = item.get("parts", [])
                cpu = next((part for part in parts if part.get("type") == "CPU"), {})
                gpu = next((part for part in parts if part.get("type") == "GPU"), {})
                board = next((part for part in parts if part.get("type") == "motherboard"), {})
                memory = next((part for part in parts if part.get("type") == "memory"), {})
                item["_profile_identity"] = (item.get("actual_config", {}).get("socket"), cpu.get("id"),
                    gpu.get("id"), board.get("offer_id"), memory.get("offer_id"))
                item["_profile_socket"] = profile.socket
                platform_variants.append(item)
        if platform_variants:
            from app.services.target_selection import target_result_rank
            platform_variants.sort(
                key=lambda item: target_result_rank(item, payload.target_fps), reverse=True)
            primary = platform_variants[0]
            if payload.objective == 'performance':
                def cpu_gpu(item):
                    parts=item.get('parts',[])
                    return (next((p.get('id') for p in parts if p.get('type')=='CPU'),None),
                            next((p.get('id') for p in parts if p.get('type')=='GPU'),None))
                old_cpu,old_gpu=cpu_gpu(primary)
                upgrades=[item for item in platform_variants
                    if cpu_gpu(item)[1]==old_gpu and item['_profile_socket']==primary['_profile_socket']
                    and item.get('fps',0)>=primary.get('fps',0)
                    and item['total_price']<=payload.budget
                    and cpu_gpu(item)[0] in hardware]
                if old_cpu in hardware and upgrades:
                    primary=max([primary,*upgrades],key=lambda item:(hardware[cpu_gpu(item)[0]].raw_score,item.get('fps',0),-item['total_price']))
            primary_identity, primary_socket = primary["_profile_identity"], primary["_profile_socket"]
            remaining = [item for item in platform_variants if item["_profile_identity"] != primary_identity]
            selected = [primary]
            other_platform = next((item for item in remaining
                                   if item["_profile_socket"] != primary_socket), None)
            if other_platform:
                selected.append(other_platform)
            best_fps = max((item for item in remaining if item not in selected),
                           key=lambda item: (item.get("fps", 0), -item.get("total_price", 0)),
                           default=None)
            if best_fps:
                selected.append(best_fps)
            for item in remaining:
                if len(selected) >= 3:
                    break
                if item not in selected:
                    selected.append(item)
            primary["alternatives"] = []
            for item in selected[1:]:
                item["title"] = (f"Альтернативная платформа {item['_profile_socket']}"
                                 if item["_profile_socket"] != primary_socket else "Другой вариант сборки")
                item["summary"] = "Полная сборка с совместимыми CPU, платой, памятью и остальными деталями."
                primary["alternatives"].append(item)
            for item in selected:
                item.pop("_profile_identity", None)
                item.pop("_profile_socket", None)
            return primary

    for flexible in ((True,) if payload.workload=='gaming' and payload.selection_policy=='target_fps' else (False,True)):
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

"""Conservative ad screening; thresholds are sanity rules, not market valuations."""
import re
import json
from collections import defaultdict
from statistics import median


UNSUITABLE = re.compile(
    r"\b(?:обмен|обменяю|меняю|куплю|выкуп|скупка|ищу|trade|wanted)\b|"
    r"неисправ|нерабоч|на запчасти|под ремонт|не включается|артефакт|"
    r"под восстанов|требует восстанов|требует ремонт|на восстанов|на разбор|\bдонор\b|"
    r"из\s+ремонта|после\s+ремонта|восстановленн|\brefurbished\b|"
    r"не проверен|непроверен|без проверки|не тестирован|не тестировал|прогрев|нет изображения|"
    r"цена (?:условная|договорная|за креплен)|только коробка|коробка без", re.I)


def safe_offers(rows, hardware):
    """Recheck persisted offers too. References ignore the selected store filter.

    A price below 20% of >=2 same-model new offers, or below 35% of
    >=3 same-model used offers, needs manual review and is not used automatically.
    Cheap old cards remain valid; the minimal performance-tier floor is deliberately
    low and never substitutes for an actual fetched price.
    """
    candidates = []
    for row in rows:
        from app.services.offers import title_category
        category = title_category(row.name)
        if category and category != row.category:
            continue
        if row.category == 'case':
            from app.services.gaming_selection import is_case_offer
            if not is_case_offer(row):
                continue
        if getattr(row, 'source', None) != 'avito' and getattr(row, 'condition', None) == 'new' and re.search(
                r'\bб\s*/\s*у\b|бывш\w*\s+в\s+употреб|\brefurbished\b', row.name, re.I):
            continue  # A discounted used retail item must not masquerade as new.
        description = json.loads(getattr(row, 'attributes', '{}')).get('description', '')
        title = re.sub(r'без обмена|обмен не (?:интересует|нужен)|обмена нет', '', row.name + ' ' + str(description), flags=re.I)
        if UNSUITABLE.search(title):
            continue
        model = hardware.get(row.hardware_id)
        if row.category in ('CPU', 'GPU'):
            from app.services.offers import component_listing, offer_model_signatures, consistent_hardware_title
            if (not component_listing(row.name) or len(offer_model_signatures(row)) > 1
                    or model and not consistent_hardware_title(row.name, model, row.category)):
                continue
        if row.category == 'GPU':
            score = model.raw_score if model else 0
            floor = 5000 if score >= 20000 else 2500 if score >= 10000 else 1
            placeholder = row.price_rub <= 2000 and (row.price_rub in (1, 10, 100, 123, 1234)
                          or len(set(str(row.price_rub))) == 1)
            if placeholder or row.price_rub < floor:
                continue
        candidates.append(row)
    groups = defaultdict(list)
    for row in candidates:
        if row.hardware_id:
            groups[row.hardware_id].append(row)
    result = []
    for row in candidates:
        peers = groups.get(row.hardware_id, [])
        retail = [p.price_rub for p in peers if p.condition == 'new' and p.source != 'avito' and p.id != row.id]
        used = [p.price_rub for p in peers if p.condition == 'used' and p.id != row.id]
        if row.category in ('CPU', 'GPU') and (
                (len(retail) >= 2 and row.price_rub < median(retail) * .2) or
                (len(used) >= 3 and row.price_rub < median(used) * .35)):
            continue
        result.append(row)
    return result

"""Gaming build search and preference policy; prices still come from stores."""
import json
import re


CPU_SEARCHES = {
    "AM4": ["Ryzen 5 5600", "Ryzen 5 5600X", "Ryzen 7 5700X"],
    "AM5": ["Ryzen 5 7500F", "Ryzen 5 7600", "Ryzen 7 7700"],
    "LGA1700": ["Core i5-12400F", "Core i5-13400F", "Core i5-14400F"],
    "LGA1200": ["Core i5-10400F", "Core i5-11400F", "Core i7-10700F"],
    "LGA1151": ["Core i5-8400", "Core i5-9400F", "Core i7-9700"],
}


def cpu_preference(cpu):
    """Preference tier for a new gaming build, not an invented FPS benchmark."""
    ryzen = re.search(r"Ryzen\s+[3579]\s+(\d{4,5})([A-Z0-9]*)", cpu.name, re.I)
    if ryzen:
        number = int(ryzen[1])
        if number in (3200, 3400):
            return 0
        return 3 if number >= 5600 else 2 if number >= 5000 else 1 if number >= 3000 else 0
    intel = re.search(r"\bi[3579][ -]*(\d{4,5})", cpu.name, re.I)
    if intel:
        number = int(intel[1])
        return 3 if number >= 12000 else 2 if number >= 10000 else 1 if number >= 8000 else 0
    return 1  # Unknown catalog models are not assigned a fabricated generation.


def gaming_options(options):
    # Prefer newer complete configurations if they fit the user's budget.
    # Older parts remain an explicit fallback when no newer configuration fits.
    preferred = [o for o in options if cpu_preference(o[0]) >= 2]
    if preferred and max(o[3] for o in preferred) < .9 * max(o[3] for o in options):
        return options
    if preferred:
        stronger = [o for o in preferred if cpu_preference(o[0]) >= 3]
        # Allow a stronger CPU when it does not require a large GPU downgrade.
        if stronger and max(o[3] for o in stronger) >= .9 * max(o[3] for o in preferred):
            return stronger
        return preferred
    newer = [o for o in options if cpu_preference(o[0]) >= 1]
    return newer or options


def case_features(offer):
    attrs = json.loads(offer.attributes)
    title = offer.name.upper()
    score = 0
    if re.search(r"CC560|CH370|CH510|MONTECH.*(?:X3|AIR|SKY)|ZALMAN\s+I[34]", title):
        score += 4
    if attrs.get('mesh_front') is True or re.search(r"MESH|AIRFLOW|СЕТЧАТ", title):
        score += 2
    if attrs.get('tempered_glass') is True or re.search(r"GLASS|СТЕКЛ|ПАНОРАМ", title):
        score += 2
    if re.search(r"ARGB|RGB|ПОДСВЕТ", title):
        score += 1
    return score


def gaming_cases(offers, budget, style='gaming', flexible=False):
    if style == 'budget':
        return sorted(offers, key=lambda o: (o.condition != 'new', o.price_rub))
    limit = max(3500, min(15000, round(budget * (.15 if flexible else .09))))
    candidates = [o for o in offers if o.condition == 'new' and 1500 <= o.price_rub <= limit
                  and not re.search(r"SLIM|\bSFF\b|LOW PROFILE|НА ЗАПЧАСТИ|ДЕФЕКТ|БЕЗ КРЫШ", o.name, re.I)]
    styled = [o for o in candidates if case_features(o) > 0]
    candidates = styled or candidates
    if style == 'minimal':
        return sorted(candidates, key=lambda o: (bool(re.search(r"ARGB|RGB|\bLED\b|ПОДСВЕТ|CC560|MONTECH.*X3", o.name, re.I)), -case_features(o), o.price_rub))
    return sorted(candidates, key=lambda o: (-case_features(o), o.price_rub))


def distinct_cases(offers):
    result, seen = [], set()
    for offer in offers:
        title = offer.name.upper()
        model = re.search(r"CC560(?:\s*(?:ARGB|V2))*|CH370|CH510|X3\s*(?:MESH|GLASS)|AIR\s*\d+\w*|SKY\s*TWO", title)
        key = re.sub(r"\W", "", model.group() if model else title)
        key += 'white' if re.search(r"WHITE|БЕЛЫЙ", title) else ''
        if key not in seen:
            result.append(offer)
            seen.add(key)
    return result

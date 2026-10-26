import re


def model_key(name: str) -> str:
    value = name.lower()
    value = re.sub(r"\((r|tm)\)|[™®]", "", value)
    value = re.sub(r"@.*$|\b\d+(?:\.\d+)?\s*(?:ghz|mhz)\b", "", value)
    value = re.sub(r"\b(?:processor|cpu|six-core|quad-core|eight-core|dual-core|\d+[- ]core)\b", "", value)
    value = re.sub(r"[^a-z0-9]", "", value)
    value = re.sub(r"^(amd|intel|nvidia|ati)", "", value)
    return re.sub(r"^(geforce|radeon)", "", value)


def match_model(items, name):
    key = model_key(name)
    if not key:
        return None
    matches = [item for item in items if model_key(item.name) == key]
    return matches[0] if len(matches) == 1 else None

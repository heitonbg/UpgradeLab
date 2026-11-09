"""Small offline directory. IDs are UpgradeLab-owned, not vendor/FIAS codes."""
import json
import unicodedata
from pathlib import Path

def key(value):
    return unicodedata.normalize('NFKC', value).casefold().replace('ё','е').strip()

CITIES = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'cities.json').read_text(encoding='utf-8'))
BY_ID = {city['city_id']: city for city in CITIES}
if len(BY_ID) != len(CITIES):
    raise RuntimeError('Duplicate city ID')

def search_cities(query='', limit=30):
    text=key(query)
    if query in BY_ID:
        return [BY_ID[query]]
    return [city for city in CITIES if not text or any(
        text in key(value) for value in [city['name'], city['region'], *city.get('aliases',[])])][:limit]

def city_name(city_id):
    city=BY_ID.get(city_id)
    return city['name']+' · '+city['region'] if city else None

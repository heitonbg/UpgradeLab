"""Cached local game names, never a remote per-keystroke request."""
import json, unicodedata, re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from app.schemas.calculate import GameName
from app.core.constants import GAME_PROFILES
from app.services.benchmark_model_v2 import dataset as benchmark_dataset
from app.services.benchmark_data import native_cohort
from app.services.external_fps_model import profiles_by_id, package as external_fps_package

ALIASES={'CS2':['Counter-Strike 2','Counter Strike 2','кс2'], 'GTA V':['Grand Theft Auto V','GTA 5'], 'Мир танков':['танки','tanki','миртанков'], 'PUBG: Battlegrounds':['PUBG'], 'The Witcher 3 Next-Gen':['The Witcher 3: Wild Hunt']}
def key(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())

@lru_cache(maxsize=1)
def catalog():
    document=json.loads((Path(__file__).resolve().parents[1]/'data/game_catalog.json').read_text(encoding='utf-8'))
    imported=json.loads((Path(__file__).resolve().parents[1]/'data/game_aliases.json').read_text(encoding='utf-8'))['aliases']
    result=[];seen=set()
    external_by_id = profiles_by_id()
    external_source = external_fps_package()["source"]
    def attach_external(item):
        external = external_by_id.get(str(item.get("id", "")))
        item["external_gpu_estimate_available"] = bool(external)
        if not external:
            return item
        item["external_model_source"] = "PCGameBenchmarks"
        item["external_model_snapshot_date"] = external_source.get("snapshot_date")
        item["external_model_license"] = external_source.get("license")
        item["steam_app_id"] = item.get("steam_app_id") or external.get("steam_app_id")
        item["minimum_requirements"] = external.get("minimum_requirements")
        item["recommended_requirements"] = external.get("recommended_requirements")
        item["engine_fps_cap"] = external.get("engine_fps_cap")
        if item.get("release_year") is None:
            item["release_year"] = external.get("release_year")
        return item
    measured_rows, _ = benchmark_dataset()
    native_counts = {}
    for row in measured_rows:
        if not native_cohort(row):
            continue
        game_key = key(row.get('game', ''))
        native_counts[game_key] = native_counts.get(game_key, 0) + 1
    for game in GameName:
        aliases=list(dict.fromkeys([*ALIASES.get(game.value,[]),*imported.get(game.value,[])]))
        native_count = native_counts.get(key(game.value), 0)
        has_legacy_profile = game in GAME_PROFILES
        result.append({'id':game.value,'name':game.value,'aliases':aliases,
            'selectable':True,
            'fps_capability':('measured_pair_data_and_legacy_profile' if native_count and has_legacy_profile
                              else 'published_measurements_available' if native_count
                              else 'legacy_profile' if has_legacy_profile
                              else 'external_model_estimate' if game.value in external_by_id
                              else 'insufficient_data'),
            'legacy_profile_available':has_legacy_profile,
            'native_pair_observation_count':native_count,
            'source_url':None})
        result[-1] = attach_external(result[-1])
        seen.update(key(x) for x in [game.value,*aliases])
    for row in document['games']:
        if key(row['name']) in seen:continue
        seen.add(key(row['name']))
        native_count = native_counts.get(key(row['name']), 0)
        external_available = row.get('id') in external_by_id
        result.append(attach_external({**row,'selectable':True,
            'fps_capability':'published_measurements_available' if native_count else
                              'external_model_estimate' if external_available else 'insufficient_data',
            'legacy_profile_available':False,
            'native_pair_observation_count':native_count}))
    return tuple(result)

@lru_cache(maxsize=1)
def _search_rows():
    return tuple((g,tuple((key(title),tuple(re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',title).casefold())))
                         for title in [g['name'],*g.get('aliases',[])])) for g in catalog())

@lru_cache(maxsize=256)
def search_games(query='',limit=50):
    needle=key(query)
    words=re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',query).casefold())
    def token_match(tokens):
        return bool(words) and all(any(word==token if word.isdigit() else token.startswith(word) for token in tokens) for word in words)
    matches=[g for g,variants in _search_rows() if not needle or any(needle in normalized or token_match(tokens) for normalized,tokens in variants)]
    if not matches and len(query.strip())>=5:
        digits=set(re.findall(r'\d+',query))
        wanted=' '.join(sorted(words))
        scored=[]
        for g in catalog():
            title=g['name']
            if digits!=set(re.findall(r'\d+',title)):continue
            score=SequenceMatcher(None,wanted,' '.join(sorted(re.findall(r'[^\W_]+',title.casefold())))).ratio()
            if score>=0.88:scored.append((score,g))
        matches=[g for _,g in sorted(scored,key=lambda row:-row[0])[:10]]
    counts={}
    for game in catalog():counts[game['fps_capability']]=counts.get(game['fps_capability'],0)+1
    legacy_count = sum(bool(game.get('legacy_profile_available')) for game in catalog())
    native_count = sum(int(game.get('native_pair_observation_count') or 0) for game in catalog())
    return {'total':len(catalog()),'matched':len(matches),'items':matches[:limit],
            'attribution':'PCGameBenchmarks','source_url':'https://github.com/emilioagustin83/pc-game-fps-dataset',
            'license':'CC-BY-4.0','selectable_count':len(catalog()),
            'legacy_profile_count':legacy_count,'native_pair_observation_count':native_count,
            'capability_counts':counts}

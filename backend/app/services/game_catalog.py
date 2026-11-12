"""Cached local game names, never a remote per-keystroke request."""
import json, unicodedata
from functools import lru_cache
from pathlib import Path
from app.schemas.calculate import GameName

ALIASES={'CS2':['Counter-Strike 2','Counter Strike 2','кс2'], 'GTA V':['Grand Theft Auto V','GTA 5'], 'Мир танков':['танки','tanki','миртанков'], 'PUBG: Battlegrounds':['PUBG'], 'The Witcher 3 Next-Gen':['The Witcher 3: Wild Hunt']}
def key(text):
    return ''.join(c for c in unicodedata.normalize('NFKC',text).casefold() if c.isalnum())

@lru_cache(maxsize=1)
def catalog():
    document=json.loads((Path(__file__).resolve().parents[1]/'data/game_catalog.json').read_text(encoding='utf-8'))
    imported=json.loads((Path(__file__).resolve().parents[1]/'data/game_aliases.json').read_text(encoding='utf-8'))['aliases']
    result=[];seen=set()
    for game in GameName:
        aliases=list(dict.fromkeys([*ALIASES.get(game.value,[]),*imported.get(game.value,[])]))
        result.append({'id':game.value,'name':game.value,'aliases':aliases,'fps_supported':True,'source_url':None})
        seen.update(key(x) for x in [game.value,*aliases])
    for row in document['games']:
        if key(row['name']) in seen:continue
        seen.add(key(row['name']))
        result.append({**row,'fps_supported':False})
    return tuple(result)

@lru_cache(maxsize=256)
def search_games(query='',limit=50):
    needle=key(query)
    matches=[g for g in catalog() if not needle or any(needle in key(x) for x in [g['name'],*g['aliases']])]
    return {'total':len(catalog()),'matched':len(matches),'items':matches[:limit],
            'attribution':'PCGameBenchmarks','source_url':'https://github.com/emilioagustin83/pc-game-fps-dataset',
            'license':'CC-BY-4.0','supported_count':len(GameName)}

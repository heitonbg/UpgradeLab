"""Rebuild the small Steam metadata index from existing licensed local data."""
import json
from pathlib import Path
from app.services.game_catalog import catalog

def build(target=None):
    target=Path(target or Path(__file__).resolve().parents[1]/'app/data/steam_game_index.json')
    rows=[]
    for game in catalog():
        rec=game.get('recommended_requirements') or {}
        rows.append({'id':str(game['id']),'name':game['name'],'aliases':game.get('aliases',[]),
                     'steam_app_id':game.get('steam_app_id'),'source_url':game.get('source_url'),
                     'recommended_requirements':{k:rec.get(k) for k in ('cpu','gpu')} if isinstance(rec,dict) else {}})
    target.write_text(json.dumps({'version':1,'attribution':'PCGameBenchmarks','license':'CC-BY-4.0',
        'source_url':'https://github.com/emilioagustin83/pc-game-fps-dataset','games':rows},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'games':len(rows),'bytes':target.stat().st_size}))
if __name__=='__main__':build()

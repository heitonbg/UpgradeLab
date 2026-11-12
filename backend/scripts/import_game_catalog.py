"""Offline CC-BY-4.0 name-only importer; never import estimated FPS as tests.

python -m scripts.import_game_catalog downloaded-games.csv [--output path]
The operator downloads from the documented source after reviewing its license.
"""
import argparse,csv,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
SOURCE='https://github.com/emilioagustin83/pc-game-fps-dataset'
def convert(path):
    path=Path(path);rows=[]
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if not {'name','page_url','release_year'}.issubset(reader.fieldnames or []):raise ValueError('Unsupported catalogue schema')
        for r in reader:
            if not r['name'] or not r['page_url'].startswith('https://pcgamebenchmarks.com/'):continue
            rows.append({'id':'pcgb:'+r['page_url'].rstrip('/').rsplit('/',1)[-1], 'name':r['name'],
                'aliases':[],'source_url':r['page_url'], 'release_year':int(r['release_year']) if r['release_year'].isdigit() else None})
    return {'source':SOURCE,'attribution':'PCGameBenchmarks — https://pcgamebenchmarks.com','license':'CC-BY-4.0',
        'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'note':'Names only; estimated FPS and requirement text were not imported.','games':rows}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('csv');parser.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'app/data/game_catalog.json'));args=parser.parse_args()
    data=convert(args.csv);Path(args.output).write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print(len(data['games']))

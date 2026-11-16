"""Fetch FPSHQ's public CC BY 4.0 snapshots and replace only validated files.

Run from backend: python -m scripts.update_fpshq_benchmarks
The endpoints are published bulk data under /data/, not the restricted /api/.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from app.services.benchmark_data import DIRECTORY

DATASETS = {
    'fpshq_game_fps_medians_raw.json': (
        'https://fpshq.com/data/game-fps-medians.json',
        'https://fpshq.com/en/data/game-fps-medians/',
        1,
    ),
    'fpshq_model_top50_raw.json': (
        'https://fpshq.com/data/fps-model-top50.json',
        'https://fpshq.com/en/data/fps-model-top50/',
        1,
    ),
}


def fetch(url):
    request = Request(url, headers={'User-Agent': 'UpgradeLab-Benchmark-Import/1.0'})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f'FPSHQ returned HTTP {response.status}')
        return response.read()


def main():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    reports = []
    staged = []
    try:
        for filename, (download_url, dataset_url, _minimum) in DATASETS.items():
            raw = fetch(download_url)
            data = json.loads(raw)
            meta = data.get('meta') or {}
            if meta.get('license') != 'CC BY 4.0' or meta.get('url') != dataset_url:
                raise ValueError(f'License/provenance mismatch in {filename}')
            rows = data.get('rows')
            if not isinstance(rows, list) or len(rows) != meta.get('rows') or not rows:
                raise ValueError(f'Row count mismatch in {filename}')
            if filename == 'fpshq_model_top50_raw.json' and any(
                row.get('source') not in {'measured', 'aggregate', 'model'} for row in rows
            ):
                raise ValueError('Unexpected FPSHQ measurement class')
            fd, temp_name = tempfile.mkstemp(prefix=filename + '.', suffix='.tmp', dir=DIRECTORY)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
            staged.append((Path(temp_name), DIRECTORY / filename))
            reports.append({'file': filename, 'version': meta.get('version'), 'rows': len(rows),
                            'sha256': hashlib.sha256(raw).hexdigest(),
                            'license': meta['license'], 'source': dataset_url})
        for temporary, destination in staged:
            os.replace(temporary, destination)
        print(json.dumps({'updated': reports}, ensure_ascii=False, indent=2))
    finally:
        for temporary, _destination in staged:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()

"""Offline FPS cohort report; never called during a user request."""
import json
from pathlib import Path
from app.services.benchmark_aggregation import aggregate
from app.services.benchmark_data import DIRECTORY

if __name__ == '__main__':
    source = DIRECTORY / 'measurements.json'
    data = json.loads(source.read_text(encoding='utf-8'))
    rows = aggregate(data['rows'])
    output = DIRECTORY / 'aggregates.json'
    output.write_text(json.dumps({'schema_version': 1, 'rows': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'observations':len(data['rows']), 'cohorts':len(rows),
                      'multi_source_cohorts':sum(row['independent_publishers'] >= 2 for row in rows),
                      'output':str(output)},ensure_ascii=False))

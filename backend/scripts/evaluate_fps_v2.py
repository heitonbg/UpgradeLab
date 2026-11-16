"""Generate a reproducible diagnostic comparing the retained baseline and FPS v2."""
import argparse
import json
from pathlib import Path

from app.services.fps_v2_evaluation import evaluate_v2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='app/data/benchmarks/fps_v2_evaluation.json')
    args = parser.parse_args()
    result = evaluate_v2()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'candidate': result['candidate_leave_one_resolution_out']['metrics'],
                      'legacy': result['legacy_same_holdout_diagnostic']['metrics'],
                      'promoted_to_production': result['promoted_to_production']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

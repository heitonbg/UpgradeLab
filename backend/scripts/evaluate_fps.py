"""Offline legacy diagnostic or curated benchmark comparison; no SQLite writes.

python -m scripts.evaluate_fps --curated
"""
import argparse,json
from app.services.fps_validation import validation_report

def report(curated=False):
    if not curated:return validation_report()
    from app.services.benchmark_data import build_dataset
    from app.services.benchmark_calibration import compare_models
    data=build_dataset()
    return {'quality':data['quality'],'evaluation':compare_models(data['rows'])}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--curated',action='store_true');args=parser.parse_args()
    print(json.dumps(report(args.curated),ensure_ascii=False,indent=2,allow_nan=False))

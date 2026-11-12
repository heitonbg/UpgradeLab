"""Offline curated dataset and evaluation. Never opens or modifies SQLite.

python -m scripts.prepare_fps_benchmarks --output ../.artifacts/benchmark-data/reproduced
"""
import argparse,json
from pathlib import Path
from app.services.benchmark_data import build_dataset,DIRECTORY
from app.services.benchmark_calibration import compare_models

def prepare(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    dataset=build_dataset();evaluation=compare_models(dataset['rows'])
    for name,value in [('measurements.json',dataset),('quality_report.json',dataset['quality']),('evaluation_report.json',evaluation)]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return dataset['quality'],evaluation
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',default=str(DIRECTORY));args=parser.parse_args()
    quality,evaluation=prepare(args.output)
    print(json.dumps({k:v for k,v in quality.items() if k not in ('excluded','duplicates_merged')},ensure_ascii=False,indent=2))
    print(json.dumps({'model_metrics':{k:{n:v for n,v in m.items() if n!='by_group'} for k,m in evaluation['models'].items()},'promotion':evaluation['promotion']},indent=2))

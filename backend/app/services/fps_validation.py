"""Strict measured-data admission and leakage-safe evaluation utilities.

Experimental only. No model is activated by importing this module.
"""
import hashlib,json,math
from pathlib import Path

def measured_native(row):
    return (row.get('benchmark_type')=='game' and row.get('game_type')=='game' and row.get('synthetic') is False
        and row.get('frame_generation') is False and row.get('upscaling') in ('','Native','Off','None')
        and row.get('os')=='windows' and row.get('form_factor')=='Desktop'
        and row.get('graphics_preset') in ('Low','Medium','High','Ultra')
        and row.get('resolution') in ('1080p','1440p','4K')
        and bool(row.get('cpu') and row.get('gpu_id') and row.get('source_file') and row.get('date') and row.get('game_version'))
        and isinstance(row.get('avg_fps'),(int,float)) and math.isfinite(row['avg_fps']) and row['avg_fps']>0)

def series_key(row):
    # All resolutions/presets/reruns on the same publisher/bench/GPU/game/version
    # stay together. A split by individual FPS row would leak the test series.
    return (row['source'],row['testbench_source_id'],row['gpu_id'],row['game_id'],row['game_version'])

def grouped_split(rows):
    groups=sorted({series_key(r) for r in rows},key=lambda g:hashlib.sha256(repr(g).encode()).hexdigest())
    if len(groups)<2:return list(rows),[]
    test=set(groups[-max(1,len(groups)//4):])
    return [r for r in rows if series_key(r) not in test],[r for r in rows if series_key(r) in test]

def metrics(pairs,total=None):
    # Each tuple: measured, prediction, interval low, interval high.
    if not pairs:return {'n':0,'mae':None,'mape_percent':None,'interval_coverage':None,'prediction_coverage':0.0}
    for y,p,lo,hi in pairs:
        if not all(math.isfinite(v) for v in (y,p,lo,hi)) or y<=0 or not 0<lo<=p<=hi:raise ValueError('Invalid evaluation sample')
    n=len(pairs)
    return {'n':n,'mae':sum(abs(p-y) for y,p,_,_ in pairs)/n,
            'mape_percent':100*sum(abs(p-y)/y for y,p,_,_ in pairs)/n,
            'interval_coverage':sum(lo<=y<=hi for y,_,lo,hi in pairs)/n,
            'prediction_coverage':n/(total or n)}

def validation_report():
    archive=json.loads((Path(__file__).resolve().parents[1]/'data/fps_measurements.json').read_text(encoding='utf-8'))
    eligible=[r for r in archive['records'] if measured_native(r)]
    train,test=grouped_split(eligible)
    return {'archive_rows':len(archive['records']),'eligible_native_windows':len(eligible),
        'games':len({r['game_id'] for r in eligible}),'series':len({series_key(r) for r in eligible}),
        'training_rows':len(train),'held_out_rows':len(test),
        'legacy':metrics([]),'candidate':metrics([]),
        'promoted':False,'reason':'Insufficient independent CPU/GPU/game test series; no defensible calibration or holdout comparison.',
        'source':archive['_source'],'license':archive['_license'],
        'legacy_external_diagnostic':legacy_external_diagnostic(eligible)}


def legacy_external_diagnostic(rows):
    """External observations not used to fit a new engine. Not a global score.

Only seed models that match an exact canonical model and supported settings
are evaluated. No translation from other presets/resolutions or laptop GPUs.
"""
    from app.services.offers import signature
    from app.services.performance import estimate_fps,fps_outlook,ram_performance_factor
    from app.schemas.calculate import GameName,CalcMode
    seed=json.loads((Path(__file__).resolve().parents[2]/'seed_data.json').read_text(encoding='utf-8'))
    cpus={signature(c['name'],'CPU'):c for c in seed['cpus'] if c.get('category')=='Desktop'}
    gpus={signature(g['name'],'GPU'):g for g in seed['gpus'] if g.get('category')=='Desktop'}
    pairs=[];samples=[]
    for row in rows:
        if row['game_id']!='cyberpunk_2077_benchmark':continue
        try:mode=CalcMode(row['resolution']+'_'+row['graphics_preset'].lower())
        except ValueError:continue
        cpu=cpus.get(signature(row['cpu'],'CPU'));gpu=gpus.get(signature(row['gpu_name'],'GPU'))
        if not cpu or not gpu:continue
        ram_type=row['memory_type'].split('-')[0]
        factor=ram_performance_factor(GameName.CYBERPUNK,cpu['name'],ram_type,row.get('memory_channels'))
        estimate=estimate_fps(cpu['score'],gpu['score'],gpu['name'],GameName.CYBERPUNK,mode,factor,cpu['name'])
        interval=fps_outlook(estimate,gpu['name'],GameName.CYBERPUNK,mode)
        pairs.append((row['avg_fps'],estimate,interval['minimum'],interval['maximum']))
        samples.append({'id':row['id'],'series':series_key(row),'measured':row['avg_fps'],'predicted':estimate,
                        'interval':[interval['minimum'],interval['maximum']],'mode':mode.value,
                        'cpu':cpu['name'],'gpu':gpu['name'],'cpu_mark':cpu['score'],'g3d_mark':gpu['score']})
    return {'metrics':metrics(pairs,total=len(rows)),'samples':samples,
            'note':'External legacy diagnostic only, one hardware/test series. Not a train/test comparison or proof of general accuracy.'}

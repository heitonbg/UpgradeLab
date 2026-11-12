"""Offline model comparison. No estimator in this file is used by the API.

Publisher-held-out folds, settings matching and abstention precede fitting.
Small or incomplete cohorts never justify promotion to production.
"""
import json,math,statistics
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from app.services.benchmark_data import native_cohort,ROOT

def error_metrics(pairs,total):
    if not total and pairs:raise ValueError('Invalid denominator')
    if len(pairs)>total:raise ValueError('More predictions than observations')
    if not pairs:return dict(n=0,mae=None,mape_percent=None,mdape_percent=None,interval_coverage=None,prediction_coverage=0 if total else None)
    if any(not all(math.isfinite(x) for x in p) or p[0]<=0 or not 0<p[2]<=p[1]<=p[3] for p in pairs):raise ValueError('Invalid prediction/interval')
    errors=[abs(p-y) for y,p,_,_ in pairs];ape=[abs(p-y)/y*100 for y,p,_,_ in pairs]
    return dict(n=len(pairs),mae=statistics.mean(errors),mape_percent=statistics.mean(ape),mdape_percent=statistics.median(ape),
        interval_coverage=sum(lo<=y<=hi for y,_,lo,hi in pairs)/len(pairs),prediction_coverage=len(pairs)/total)

@lru_cache(maxsize=1)
def seed_features():
    from app.services.offers import signature
    seed=json.loads((ROOT.parents[1]/'seed_data.json').read_text(encoding='utf-8'))
    return ({signature(c['name'],'CPU'):c for c in seed['cpus'] if c.get('category')=='Desktop' and signature(c['name'],'CPU')},
            {signature(g['name'],'GPU'):g for g in seed['gpus'] if g.get('category')=='Desktop' and signature(g['name'],'GPU')})

def features(row):
    from app.services.offers import signature
    cpus,gpus=seed_features();cpu=cpus.get(signature(row['cpu'] or '','CPU'));gpu=gpus.get(signature(row['gpu'] or '','GPU'))
    if not cpu or not gpu or cpu['score']<=0 or gpu['score']<=0:return None
    if row.get('vram_gb') is not None and gpu.get('vram') is not None and row['vram_gb']!=gpu['vram']:return None
    return cpu['score'],gpu['score']

def legacy_prediction(row):
    from app.schemas.calculate import GameName,CalcMode
    from app.services.performance import estimate_fps,fps_outlook,ram_performance_factor
    f=features(row)
    if not f or not native_cohort(row):return None
    try:game=GameName(row['game']);mode=CalcMode(row['resolution']+'_'+row['preset'].lower())
    except ValueError:return None
    factor=ram_performance_factor(game,row['cpu'],(row.get('ram_type') or '').split('-')[0],row.get('ram_channels'))
    value=estimate_fps(f[0],f[1],row['gpu'],game,mode,factor,row['cpu'])
    interval=fps_outlook(value,row['gpu'],game,mode)
    return value,interval['minimum'],interval['maximum']

def settings_key(row):
    return tuple(row.get(k) for k in ('game','game_version','resolution','preset','rt','upscaling',
        'frame_generation','frame_generation_mode','render_scale','os','ram_gb','ram_type','ram_channels','overclocked','scene'))

def relative_prediction(row,training):
    """Unfitted anchor baseline; never treat CPU Mark as a measured FPS ratio."""
    target=features(row)
    if not target or not native_cohort(row):return None
    candidates=[]
    for anchor in training:
        f=features(anchor)
        if not f or not native_cohort(anchor) or settings_key(anchor)!=settings_key(row):continue
        if anchor['publisher']==row['publisher'] or anchor['series_id']==row['series_id']:continue
        # No transfer of an unknown X3D/cache effect between different CPUs.
        if anchor['cpu']!=row['cpu'] and ('x3d' in anchor['cpu'].lower() or 'x3d' in row['cpu'].lower()):continue
        ratios=(target[0]/f[0],target[1]/f[1])
        if not all(.5<=r<=2 for r in ratios):continue
        distance=sum(abs(math.log(r)) for r in ratios)
        candidates.append((distance,anchor['id'],anchor['average_fps']*min(ratios)))
    return min(candidates)[2] if candidates else None

def solve_frametime(points):
    """Fit nonnegative t_ms = a / CPU_Mark + b / G3D_Mark.

Caller must independently check cohort diversity/holdouts. Boundary solutions
are evaluated rather than clipping a negative unconstrained coefficient.
"""
    if len(points)<6 or len({c for c,g,f in points})<3 or len({g for c,g,f in points})<3:return None
    if any(not all(math.isfinite(x) and x>0 for x in p) for p in points):raise ValueError('Invalid feature/FPS')
    xs=[(1/c,1/g,1000/f) for c,g,f in points]
    aa=sum(x*x for x,y,t in xs);bb=sum(y*y for x,y,t in xs);ab=sum(x*y for x,y,t in xs)
    at=sum(x*t for x,y,t in xs);bt=sum(y*t for x,y,t in xs);det=aa*bb-ab*ab
    if det<=aa*bb*1e-10:return None
    candidates=[(at/aa,0),(0,bt/bb)]
    a,b=(at*bb-bt*ab)/det,(bt*aa-at*ab)/det
    if a>=0 and b>=0:candidates.append((a,b))
    return min(candidates,key=lambda c:sum((c[0]*x+c[1]*y-t)**2 for x,y,t in xs))

def fit_frametime(training):
    eligible=[r for r in training if native_cohort(r) and features(r)]
    # Cross-source validation needs more than one training publisher, plus a
    # held-out publisher. One hardware pair cannot identify CPU and GPU terms.
    if len({r['publisher'] for r in eligible})<2 or len({r['series_id'] for r in eligible})<3:return {}
    groups=defaultdict(list)
    for row in eligible:groups[settings_key(row)].append(row)
    result={}
    for k,rows in groups.items():
        if len({r['publisher'] for r in rows})<2 or len({r['series_id'] for r in rows})<3:continue
        model=solve_frametime([(*features(r),r['average_fps']) for r in rows])
        if model:result[k]=model
    return result

def publisher_folds(rows):
    for publisher in sorted({r['publisher'] for r in rows}):
        train=[r for r in rows if r['publisher']!=publisher];test=[r for r in rows if r['publisher']==publisher]
        # A mirrored/cross-published series must not cross folds either.
        test_series={r['series_id'] for r in test}
        train=[r for r in train if r['series_id'] not in test_series]
        yield publisher,train,test

def x3d_pairs(rows):
    result=[]
    for a in rows:
        if 'x3d' not in (a['cpu'] or '').lower() or not native_cohort(a):continue
        for b in rows:
            if 'x3d' in (b['cpu'] or '').lower() or not features(b) or not native_cohort(b):continue
            if a['series_id']!=b['series_id'] or a['gpu']!=b['gpu'] or settings_key(a)!=settings_key(b):continue
            result.append({'x3d_id':a['id'],'non_x3d_id':b['id'],'ratio':a['average_fps']/b['average_fps']})
    return result

def configuration_rows(rows):
    # Repeated captures are observations, not independent test configurations.
    groups=defaultdict(list)
    fields=('data_type','publisher','series_id','game','game_version','cpu','gpu','ram_gb','ram_type','ram_channels',
            'vram_gb','resolution','preset','rt','upscaling','frame_generation','frame_generation_mode',
            'render_scale','os','driver','power_profile','overclocked','scene','form_factor')
    for row in rows:groups[tuple(row.get(k) for k in fields)].append(row)
    result=[]
    for points in groups.values():
        row=dict(points[0]);row['observation_count']=len(points)
        if len(points)>1:
            import hashlib
            row['id']='config:'+hashlib.sha256('|'.join(sorted(p['id'] for p in points)).encode()).hexdigest()[:24]
            row['average_fps']=statistics.mean(p['average_fps'] for p in points)
            row['one_percent_low']=None  # Cannot pool a 1% percentile from per-run summaries.
            row['source_ids']=sorted({v for p in points for v in p['source_ids']})
            row['record_kind']='summary';row['run_count']=sum(p['run_count'] for p in points) if all(p['run_count'] is not None for p in points) else None
            row['notes']=[*row['notes'],'Evaluation aggregates repeated configuration means with equal weight per run; 1% low is not pooled.']
        result.append(row)
    return result

def compare_models(rows):
    observations=rows;rows=configuration_rows(rows)
    scoring=[r for r in rows if native_cohort(r)]
    predictions={name:{} for name in ('legacy','relative_transfer','cpu_gpu_frametime','regression')};folds=[]
    for publisher,training,testing in publisher_folds(rows):
        models=fit_frametime(training);eligible=[r for r in testing if native_cohort(r)]
        for row in eligible:
            legacy=legacy_prediction(row)
            if legacy:predictions['legacy'][row['id']]=legacy
            relative=relative_prediction(row,training)
            if relative:predictions['relative_transfer'][row['id']]=(relative,relative,relative)
            model=models.get(settings_key(row));f=features(row)
            if model and f:
                value=1000/(model[0]/f[0]+model[1]/f[1]);predictions['cpu_gpu_frametime'][row['id']]=(value,value,value)
        folds.append({'held_out_publisher':publisher,'train_rows':len(training),'test_rows':len(testing),
            'native_windows_test_rows':len(eligible),'frametime_models_fitted':len(models)})
    by_id={r['id']:r for r in scoring};reports={}
    for name,values in predictions.items():
        pairs=[(by_id[k]['average_fps'],*v) for k,v in values.items()]
        report=error_metrics(pairs,len(scoring))
        # Only legacy currently supplies intervals; point baseline intervals
        # must not masquerade as calibrated uncertainty.
        if name!='legacy':report['interval_coverage']=None
        report['all_configuration_prediction_coverage']=len(values)/len(rows) if rows else None
        report['all_observation_prediction_coverage']=sum(by_id[k]['observation_count'] for k in values)/len(observations) if observations else None
        report['by_group']={}
        for field in ('game','cpu','gpu','resolution'):
            groups={}
            for v in sorted({r[field] for r in scoring}):
                ids=[r['id'] for r in scoring if r[field]==v]
                groups[v]=error_metrics([(by_id[k]['average_fps'],*values[k]) for k in ids if k in values],len(ids))
            report['by_group'][field]=groups
        report['by_group']['x3d']={}
        for tag in ('X3D','non-X3D'):
            ids=[r['id'] for r in scoring if ('x3d' in (r['cpu'] or '').lower())==(tag=='X3D')]
            report['by_group']['x3d'][tag]=error_metrics([(by_id[k]['average_fps'],*values[k]) for k in ids if k in values],len(ids))
        if name!='legacy':
            for groups in report['by_group'].values():
                for group in groups.values():group['interval_coverage']=None
        reports[name]=report
    common=set(predictions['legacy'])
    for name in ('relative_transfer','cpu_gpu_frametime','regression'):common&=set(predictions[name])
    return {'scoring_cohort':'measured native stock desktop Windows; matching declared settings, no OS/RT/FG/OC mixing',
        'scoring_rows':len(scoring),'input_observations':len(observations),'distinct_configurations':len(rows),'repeat_policy':'Equal mean per repeated configuration; repeated runs are not separate validation configurations.','folds':folds,'models':reports,
        'common_support_all_models':len(common),'x3d_comparisons':x3d_pairs(rows),
        'regression_status':'not fitted: inadequate independent sources/series, CPU/GPU diversity and feature coverage; no imputation of Single Thread/L3/architecture',
        'promotion':{'allowed':False,'reason':'No common-support cross-source improvement; independent X3D contrasts absent. Production engine unchanged.'},
        'predictions':[{'id':k,'measured':by_id[k]['average_fps'],'predicted':v[0],'interval':[v[1],v[2]],'model':name} for name,vs in predictions.items() for k,v in vs.items()],
        'cautions':['Legacy intervals are heuristic, not calibrated.', 'n=0 means abstention, not zero error.',
                    'Only two publishers, three hardware pairs and three native Windows observations; no global accuracy claim.']}

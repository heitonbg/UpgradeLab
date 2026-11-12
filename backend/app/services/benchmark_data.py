"""Offline licensed FPS observations. This module never changes production FPS.

Unknown settings remain null. Estimated points and synthetic workloads are not
promoted to measured game data. Source snapshots and hashes permit replay.
"""
import hashlib,json,math,re
from collections import Counter
from datetime import date
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator
from typing import Literal
ROOT=Path(__file__).resolve().parents[1]/'data'
DIRECTORY=ROOT/'benchmarks'

class Observation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str
    game:str
    game_version:str|None=None
    version_consistent:bool|None=None
    cpu:str|None=None
    gpu:str|None=None
    ram_gb:float|None=None
    ram_type:str|None=None
    ram_channels:int|None=None
    vram_gb:float|None=None
    resolution:str|None=None
    preset:str|None=None
    rt:bool|None=None
    upscaling:str|None=None
    frame_generation:bool|None=None
    frame_generation_mode:str|None=None
    form_factor:str|None=None
    render_scale:str|None=None
    average_fps:float=Field(gt=0,allow_inf_nan=False)
    one_percent_low:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    data_type:Literal['measured','estimated']='measured'
    record_kind:Literal['raw_run','summary','publisher_point']='publisher_point'
    observation_count:int=Field(default=1,ge=1)
    publisher:str
    source_url:str
    source_ids:list[str]
    license:Literal['CC-BY-4.0']
    attribution:str
    observed_date:str|None=None
    observed_time:str|None=None
    date_window:str|None=None
    scene:str|None=None
    os:str|None=None
    driver:str|None=None
    power_profile:str|None=None
    overclocked:bool|None=None
    series_id:str
    run_count:int|None=None
    proof_level:str|None=None
    notes:list[str]=Field(default_factory=list)
    @field_validator('average_fps','one_percent_low',mode='before')
    @classmethod
    def not_boolean(cls,value):
        if isinstance(value,bool):raise ValueError('Boolean is not an FPS measurement')
        return value
    @model_validator(mode='after')
    def validate_evidence(self):
        if self.one_percent_low is not None and self.one_percent_low>self.average_fps:raise ValueError('1% low exceeds mean')
        if not self.source_ids or not self.source_url.startswith('https://'):raise ValueError('Missing provenance')
        if self.observed_date:date.fromisoformat(self.observed_date)
        return self

def identity(row):
    # Publisher is part of identity: equal FPS from different publishers is NOT
    # proof of a duplicate. 1% low can be missing on a repeated chart point.
    keys=('data_type','publisher','series_id','game','game_version','cpu','gpu','resolution','preset','rt',
          'upscaling','frame_generation','frame_generation_mode','render_scale','os','power_profile','overclocked',
          'ram_gb','ram_type','ram_channels','vram_gb','driver','scene','form_factor','observed_date','observed_time','date_window','average_fps')
    return tuple(row[k] for k in keys)

def deduplicate(rows):
    found={};duplicates=[]
    for value in rows:
        row=Observation.model_validate(value).model_dump()
        k=identity(row)
        if k not in found:found[k]=row;continue
        existing=found[k]
        if existing['one_percent_low'] is not None and row['one_percent_low'] is not None and existing['one_percent_low']!=row['one_percent_low']:
            raise ValueError('Conflicting repeated observation')
        existing['one_percent_low']=existing['one_percent_low'] if existing['one_percent_low'] is not None else row['one_percent_low']
        existing['source_ids']=sorted(set(existing['source_ids']+row['source_ids']))
        duplicates.append({'kept':existing['id'],'duplicate':row['id'],'reason':'Same publisher/series/settings/mean; repeated chart evidence merged, not counted as an independent run.'})
    return list(found.values()),duplicates

def import_open_gpu(archive):
    if archive.get('_license',{}).get('name')!='CC-BY-4.0':raise ValueError('Unapproved Open GPU license')
    result=[];excluded=[]
    raw_records='game_summaries' in archive
    for r in archive['records']:
        if r.get('game_type')!='game' or r.get('synthetic') is not False or r.get('data_type','measured')!='measured':
            excluded.append({'source_id':r['id'],'reason':'Not a measured game workload'});continue
        preset=r.get('graphics_preset');upscaling=r.get('upscaling')
        # The OGB schema distinguishes named Ray Tracing presets from raster
        # presets. Retain the source label and state this normalization.
        rt=True if preset and preset.startswith('Ray Tracing:') else False if preset in ('Low','Medium','High','Ultra','Steam Deck') else None
        native=upscaling=='' or upscaling in ('Native','Off','None')
        game='Cyberpunk 2077' if r['game_id']=='cyberpunk_2077_benchmark' else r['game']
        series='ogb:'+':'.join(str(r.get(k) or 'unknown') for k in ('source','testbench_source_id','game_id','game_version','os'))
        value=Observation(id='ogb:'+r['id'],game=game,game_version=r.get('game_version') or None,version_consistent=True if raw_records and r.get('game_version') else None,
            cpu=r.get('cpu') or None,gpu=r.get('gpu_name') or None,ram_gb=r.get('memory_gb'),ram_type=r.get('memory_type') or None,
            ram_channels=r.get('memory_channels'),vram_gb=r.get('vram_gb'),resolution=r.get('resolution'),preset=preset,
            rt=rt,upscaling='off' if native else upscaling,frame_generation=r.get('frame_generation'),
            frame_generation_mode='off' if r.get('frame_generation') is False else None,form_factor=r.get('form_factor'),
            render_scale='native' if native else None,average_fps=r['avg_fps'],one_percent_low=r.get('p1_low'),
            record_kind='raw_run' if raw_records else 'summary',publisher='Open GPU Benchmarks',source_url=archive['_source']['url'],source_ids=[r['id'],r['source_file']],
            license='CC-BY-4.0',attribution='Open GPU Benchmarks — https://opengpubenchmarks.com',
            observed_date=r.get('date') or None,observed_time=r.get('time') or None,scene='built-in benchmark' if r['game_id']=='cyberpunk_2077_benchmark' else None,
            os=r.get('os') or None,driver=r.get('driver') or None,power_profile=r.get('power_mode') or None,
            overclocked=r.get('overclocked'),series_id=series,run_count=1 if raw_records else r.get('run_count'),proof_level=r.get('proof_level'),
            notes=['RT normalized from source preset labels; empty upscaling denotes native per published comparison policy.',
                   'Per-run FPS aggregate; not a raw frametime capture.' if raw_records else 'Source summary; game version is not a grouping key, so not suitable for version-sensitive fitting.'])
        result.append(value.model_dump())
    return result,excluded

def import_techfuel(archive):
    if archive.get('license',{}).get('spdx_id')!='CC-BY-4.0':raise ValueError('Unapproved TechFuel license')
    system=archive['system_under_test'];memory=re.search(r'(\d+(?:\.\d+)?)\s*GB\s+(DDR\d+(?:-\d+)?)',system['memory']);vram=re.search(r'(\d+(?:\.\d+)?)\s*GB',archive['card_under_test']['memory']);source='https://techfuelhq.com/data/gpu/'+archive['dataset_id']+'/'
    result=[]
    # Explicit source mappings; an unnamed preset/render scale/FG state stays
    # unknown. Native rendering alone does not prove frame generation was off.
    settings={
      'Native PT (no DLSS, no FG)':('Cyberpunk 2077','RT Overdrive',True,'off',False,'native'),
      'DLSS-Q, no FG':('Cyberpunk 2077','RT Overdrive',True,'DLSS Quality',False,None),
      'MFG 2x':('Cyberpunk 2077','RT Overdrive',True,'DLSS Quality',True,None),
      'MFG 4x':('Cyberpunk 2077','RT Overdrive',True,'DLSS Quality',True,None),
      'Cyberpunk Ultra (raster)':('Cyberpunk 2077','Ultra',False,'off',None,'native'),
      'Cyberpunk RT-Ultra + DLSS-Q':('Cyberpunk 2077','RT Ultra',True,'DLSS Quality',None,None),
      'Cyberpunk Path Tracing (native)':('Cyberpunk 2077','RT Overdrive',True,'off',False,'native'),
      'Alan Wake 2 RT + DLSS-Q':('Alan Wake 2',None,True,'DLSS Quality',None,None),
      'Black Myth: Wukong Cinematic':('Black Myth: Wukong','Cinematic',None,None,None,None)}
    for chart in archive['charts']:
        if chart['chart_id'] not in ('05-dlss4-mfg-cyberpunk','06-4k-gaming'):continue
        for index,point in enumerate(chart['data_points']):
            if not point.get('source','').startswith('TechFuelHQ first-party'):raise ValueError('Unconfirmed first-party provenance')
            game,preset,rt,up,fg,scale=settings[point['label']]
            value=Observation(id='techfuel:'+chart['chart_id']+':'+str(index),game=game,
                cpu=system['cpu'],gpu=archive['card_under_test']['model'],ram_gb=float(memory[1]) if memory else None,ram_type=memory[2] if memory else None,vram_gb=float(vram[1]) if vram else None,
                resolution='4K',preset=preset,rt=rt,upscaling=up,frame_generation=fg,render_scale=scale,
                frame_generation_mode=point['label'] if point['label'].startswith('MFG ') else 'off' if fg is False else None,form_factor='Desktop',
                average_fps=point.get('avg_fps',point.get('fps')),one_percent_low=point.get('low_1pct_fps'),
                publisher='TechFuelHQ',source_url=source,source_ids=[chart['chart_id']+':'+str(index)],
                license='CC-BY-4.0',attribution=archive['license']['attribution_required'],
                date_window=system['test_date_window'],scene='built-in benchmark' if game=='Cyberpunk 2077' else None,
                power_profile=chart.get('gpu_profile'),overclocked=True,series_id='techfuel:'+archive['dataset_id'],
                proof_level='publisher first-party assertion',
                notes=['Game build, OS, driver, RAM channels, exact capture date and repeat count not supplied.',
                       'Manual overclock profile is not equivalent to stock RTX 5080.',
                       'Repeated native PT point occurs in two charts; source references are merged.'])
            result.append(value.model_dump())
    return result

def complete_settings(row):
    keys=('game_version','cpu','gpu','ram_gb','vram_gb','resolution','preset','rt','upscaling','frame_generation','scene','os')
    return all(row.get(k) is not None and row.get(k)!='' for k in keys)

def native_cohort(row,os='windows'):
    return (row['data_type']=='measured' and row['os']==os and row['form_factor']=='Desktop' and row['rt'] is False
        and row['frame_generation'] is False and row['upscaling']=='off' and row['render_scale']=='native'
        and row['preset'] in ('Low','Medium','High','Ultra') and complete_settings(row)
        and row['overclocked'] is False and row['version_consistent'] is True)

def quality_report(rows,duplicates,excluded):
    n=len(rows)
    return {'observations':n,'raw_runs':sum(r['record_kind']=='raw_run' for r in rows),'publisher_points':sum(r['record_kind']=='publisher_point' for r in rows),'measured_observations':sum(r['data_type']=='measured' for r in rows),'estimated_observations':sum(r['data_type']=='estimated' for r in rows),'games':len({r['game'] for r in rows}),
        'cpus':len({r['cpu'] for r in rows if r['cpu']}),'gpus':len({r['gpu'] for r in rows if r['gpu']}),
        'publishers':len({r['publisher'] for r in rows}),'series':len({r['series_id'] for r in rows}),
        'complete_settings':sum(complete_settings(r) for r in rows),'complete_settings_fraction':sum(complete_settings(r) for r in rows)/n if n else None,
        'native_windows_stock':sum(native_cohort(r) for r in rows),'native_linux_stock':sum(native_cohort(r,'linux') for r in rows),
        'with_one_percent_low':sum(r['one_percent_low'] is not None for r in rows),
        'by_publisher':dict(Counter(r['publisher'] for r in rows)),'by_game':dict(Counter(r['game'] for r in rows)),
        'missing_fields':{k:sum(r.get(k) is None for r in rows) for k in ('game_version','ram_channels','rt','frame_generation','os','driver','scene','observed_date')},
        'duplicates_merged':duplicates,'excluded':excluded,
        'note':'Observations include source summaries and RT/upscaling/FG/OC cohorts. Counts do not imply calibration eligibility.'}

def build_dataset(open_gpu_path=None,techfuel_path=None):
    paths=[Path(open_gpu_path)] if open_gpu_path else [DIRECTORY/'ogb_rtx5080_raw.json',DIRECTORY/'ogb_steam_machine_raw.json']
    techfuel=Path(techfuel_path or DIRECTORY/'techfuel_raw.json');all_rows=[];excluded=[];sources=[]
    for path in paths:
        rows,rejected=import_open_gpu(json.loads(path.read_text(encoding='utf-8')))
        all_rows.extend(rows);excluded.extend(rejected)
        sources.append({'publisher':'Open GPU Benchmarks','file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    all_rows.extend(import_techfuel(json.loads(techfuel.read_text(encoding='utf-8'))))
    sources.append({'publisher':'TechFuelHQ','file':techfuel.name,'sha256':hashlib.sha256(techfuel.read_bytes()).hexdigest()})
    rows,duplicates=deduplicate(all_rows)
    return {'schema_version':1,'sources':sources,'rows':rows,'quality':quality_report(rows,duplicates,excluded)}

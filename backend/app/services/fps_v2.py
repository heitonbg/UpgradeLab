"""Evidence gate around the retained legacy FPS engine.

Unknown features and unsupported settings produce no invented v2 FPS.
"""
from app.schemas.calculate import GameName,CalcMode
from app.services.performance import estimate_fps,fps_outlook,cpu_capacity,gpu_capacity,cs2_cpu_basis
from app.core.constants import GAME_PROFILES
from app.services.benchmark_model_v2 import predict_pair

def predict(cpu,gpu,game,resolution='1080p',preset='high',ram_type=None,ram_channels=None,ram_capacity_gb=None,rt=False,upscaling='off',frame_generation=False):
    unavailable={'status':'insufficient_data','average_fps':None,'one_percent_low':None,'interval':None,
        'method':'unavailable','confidence':'insufficient','note':'Недостаточно подтверждённых данных для этой игры, оборудования или настроек.',
        'model_version':'fps-engine-v2-candidate-0.1','production_baseline':'legacy'}
    empirical = predict_pair(cpu.name, gpu.name, str(game), resolution,
        preset=preset, ram_type=ram_type, ram_channels=ram_channels,
        ram_capacity_gb=ram_capacity_gb, rt=rt, upscaling=upscaling,
        frame_generation=frame_generation)
    unavailable['candidate_v2'] = empirical
    try:game=GameName(game);mode=CalcMode(resolution+'_'+preset.lower())
    except ValueError:return unavailable
    if rt or upscaling!='off' or frame_generation or cpu.raw_score<=0 or gpu.raw_score<=0:return unavailable
    # RAM remains test context only; it is not an FPS-model coefficient.
    value=estimate_fps(cpu.raw_score,gpu.raw_score,gpu.name,game,mode,1.0,cpu.name)
    scale=GAME_PROFILES[game][mode]['overhead']
    # RAM is context only: keep the legacy calculation independent of memory.
    cc=cpu_capacity(cpu.raw_score,cpu.name,game,mode,1.0)*scale
    gc=gpu_capacity(gpu.raw_score,gpu.name,game,mode)*scale
    outlook=fps_outlook(value,gpu.name,game,mode)
    warnings=['Модель v2 не прошла независимую валидацию; сохранён прежний расчёт.']
    if 'x3d' in cpu.name.lower() and cs2_cpu_basis(cpu.name) is None:
        warnings.append('Для этой X3D-модели нет игровой CPU-опоры; преимущество кеша не подтверждено и отдельный бонус не применяется.')
    warnings.append('Single Thread Rating, архитектура, частоты и L3 отсутствуют в текущем Hardware; отдельные коэффициенты не подставлены.')
    if ram_capacity_gb is None:warnings.append('Объём RAM неизвестен.')
    else:warnings.append('Влияние объёма RAM не откалибровано; оценка не гарантирует отсутствие подгрузок и просадок.')
    return {'status':'legacy_estimate','average_fps':value,'one_percent_low':None,
        'model_version':'fps-engine-v2-candidate-0.1',
        'production_baseline':'legacy',
        'candidate_v2':empirical,
        'interval':{'minimum':outlook['minimum'],'maximum':outlook['maximum'],'calibrated':False},
        'method':outlook['method'],'confidence':'heuristic','cpu_ceiling':cc,'gpu_ceiling':gc,
        'limiting_component':'CPU' if cc<gc else 'GPU','cpu_basis':'game_reference_or_legacy_curve',
        'features':{'cpu_mark':cpu.raw_score,'single_thread_rating':None,'gpu_g3d_mark':gpu.raw_score,
                    'gpu_vram_gb':gpu.vram,'ram_capacity_gb':ram_capacity_gb,'ram_type':ram_type,'ram_channels':ram_channels},
        'sources':outlook['sources'],'warnings':warnings,'note':outlook['note']}

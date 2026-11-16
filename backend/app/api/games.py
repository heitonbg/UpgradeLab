from app.services.steam_storage import with_requirements
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from functools import lru_cache
from sqlalchemy import select

from app.api.deps import DBSession
from app.db.models import Hardware
from app.services.game_catalog import search_games, catalog
from app.services.adaptive_fps import adaptive_game_coverage, predict_adaptive_fps
from app.services.fps_engine_v4 import relative_pair_proxy
from app.services.benchmark_model_v2 import model_coverage
from app.services.external_fps_model import external_game_coverage, profiles_by_id
from app.services.cpu_requirements import requirement_coverage_summary, requirement_resolution_summary

router = APIRouter(prefix='/api', tags=['games'])


@lru_cache(maxsize=1)
def _cpu_requirement_coverage():
    return requirement_coverage_summary(profiles_by_id().values())


@router.get('/games')
def games(q: str = Query(default='', max_length=100), limit: int = Query(default=50, ge=1, le=100)):
    return search_games(q.strip(), limit)


@router.get('/games/coverage')
def game_coverage(db: DBSession):
    items = catalog()
    counts = {}
    for game in items:
        level = game.get('fps_capability', 'insufficient_data')
        counts[level] = counts.get(level, 0) + 1
    metadata = {
        'steam_app_id': sum(bool(item.get('steam_app_id') or item.get('appid')) for item in items),
        'minimum_requirements': sum(bool(item.get('minimum_requirements') or item.get('minimum_system_requirements')) for item in items),
        'recommended_requirements': sum(bool(item.get('recommended_requirements') or item.get('recommended_system_requirements')) for item in items),
        'release_year': sum(item.get('release_year') is not None for item in items),
        'genres_or_tags': sum(bool(item.get('genres') or item.get('tags')) for item in items),
    }
    external = external_game_coverage()
    cpu_requirements = _cpu_requirement_coverage()
    cpu_catalog = list(db.scalars(select(Hardware).where(
        Hardware.type == 'CPU', Hardware.raw_score > 0)))
    gpu_catalog = list(db.scalars(select(Hardware).where(
        Hardware.type == 'GPU', Hardware.raw_score > 0)))
    cpu_resolution = requirement_resolution_summary(profiles_by_id().values(), cpu_catalog)
    return {
        'total_games': len(items),
        'selectable_games': sum(bool(item.get('selectable')) for item in items),
        'capability_counts': counts,
        'metadata_coverage': metadata,
        'cpu_requirement_coverage': cpu_requirements,
        'cpu_requirement_resolution': cpu_resolution,
        'legacy_profile_games': sum(item.get('fps_capability') in {'legacy_profile', 'measured_pair_data_and_legacy_profile'} for item in items),
        'benchmark_model_coverage': model_coverage(),
        'adaptive_strategy_coverage': adaptive_game_coverage(cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog),
        'external_fps_coverage': {
            **external,
            'numeric_gpu_oriented_estimate_games': external['games_with_external_model_estimate'],
            'full_system_predictions_from_external_model': 0,
            'cpu_bottleneck_predictions_from_external_model': 0,
            'supported_settings': '1080p High, native, without RT/upscaling/frame generation',
            'note': 'Число внешних оценок GPU не равно числу подтверждённых FPS всей системы; CPU-ограничение этой моделью не рассчитывается.',
        },
        'note': 'Сервис выбирает одно наиболее обоснованное основание: опубликованный тест, расчётную модель или отдельно подписанный ориентир видеокарты. Внешние GPU-оценки не являются FPS полной системы; PassMark не преобразуется напрямую в FPS.',
    }


class FpsQuery(BaseModel):
    cpu_id: int = Field(gt=0)
    gpu_id: int = Field(gt=0)
    game: str = Field(min_length=1, max_length=200)
    resolution: Literal['1080p', '1440p', '4K'] = '1080p'
    preset: Literal['low', 'medium', 'high', 'ultra'] = 'high'
    ram_type: Literal['DDR3', 'DDR4', 'DDR5'] | None = None
    ram_channels: Literal[1, 2] | None = None
    ram_capacity_gb: int | None = Field(default=None, ge=2, le=512)
    rt: bool = False
    upscaling: Literal['off', 'dlss', 'fsr', 'xess'] = 'off'
    frame_generation: bool = False


@router.post('/fps/predict')
@with_requirements
def fps(payload: FpsQuery, db: DBSession):
    cpu = db.get(Hardware, payload.cpu_id)
    gpu = db.get(Hardware, payload.gpu_id)
    if cpu is None or cpu.type != 'CPU' or gpu is None or gpu.type != 'GPU':
        raise HTTPException(400, 'CPU или GPU не найдены')
    cpu_catalog = list(db.scalars(select(Hardware).where(
        Hardware.type == 'CPU', Hardware.raw_score > 0)))
    gpu_catalog = list(db.scalars(select(Hardware).where(
        Hardware.type == 'GPU', Hardware.raw_score > 0)))
    settings = payload.model_dump(exclude={'cpu_id', 'gpu_id'})
    result = predict_adaptive_fps(cpu, gpu, payload.game, settings, cpu_catalog=cpu_catalog, gpu_catalog=gpu_catalog)
    cpu_scores = [row.raw_score for row in cpu_catalog]
    gpu_scores = [row.raw_score for row in gpu_catalog]
    result['relative_hardware'] = relative_pair_proxy(
        cpu.raw_score, gpu.raw_score, cpu_scores, gpu_scores)
    return result

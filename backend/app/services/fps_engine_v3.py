"""Experimental hardware-frame-time model.

This model deliberately abstains when calibrated workload inputs are absent;
synthetic hardware scores are not treated as measured game FPS.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class CpuHardware:
    single_thread_index: float | None = None
    performance_cores: int | None = None
    efficient_cores: int | None = None
    threads: int | None = None
    l3_cache_mb: float | None = None
    architecture_index: float | None = None


@dataclass(frozen=True)
class GpuHardware:
    compute_index: float | None = None
    bandwidth_gbps: float | None = None
    texture_rate: float | None = None
    pixel_rate: float | None = None
    vram_gb: float | None = None
    desktop: bool | None = None
    tgp_w: float | None = None


@dataclass(frozen=True)
class GameWorkload:
    serial_work_ms_index: float | None = None
    parallel_work_ms_index: float | None = None
    compute_work_ms_index: float | None = None
    memory_work_ms_index: float | None = None
    texture_work_ms_index: float | None = None
    raster_work_ms_index: float | None = None
    extra_ms: float | None = None
    pixel_alpha: float | None = None
    confidence: str = "insufficient"


def _valid_positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value > 0


def parallel_efficiency(p_cores: int, e_cores: int = 0, threads: int | None = None) -> float:
    """Sublinear capacity; SMT contributes at most a bounded quarter-core."""
    if p_cores < 1 or e_cores < 0:
        raise ValueError("invalid core topology")
    physical = p_cores + 0.35 * e_cores
    smt = max(0, (threads or p_cores) - p_cores - e_cores)
    raw = physical + min(smt, p_cores) * 0.25
    return raw / (1.0 + 0.12 * max(0.0, raw - 1.0))


def predict_fps(cpu: CpuHardware, gpu: GpuHardware, workload: GameWorkload,
                resolution: str, preset_scale: float = 1.0, rt: bool = False,
                upscaling_scale: float = 1.0) -> dict:
    """Return a hardware-model estimate only with explicit calibrated work.

    RAM is intentionally absent from the interface. `*_work_ms_index` values
    must be calibrated workload anchors, not arbitrary PassMark-to-FPS factors.
    """
    base = {"fps": None, "cpu_frame_time_ms": None, "gpu_frame_time_ms": None,
            "bottleneck": None, "confidence": "insufficient_data",
            "method": "hardware_model_v3", "model_version": "3.0",
            "missing_inputs": [], "measurement_type": "estimated"}
    required = ["CPU single-thread/workload anchors", "GPU resource/workload anchors",
                "game workload calibration"]
    if not (_valid_positive(cpu.single_thread_index) and
            _valid_positive(gpu.compute_index) and
            _valid_positive(workload.serial_work_ms_index) and
            _valid_positive(workload.compute_work_ms_index) and
            _valid_positive(workload.pixel_alpha)):
        base["missing_inputs"] = required
        return base
    pixels = {"1080p": 1920*1080, "1440p": 2560*1440, "4k": 3840*2160}.get(resolution.casefold())
    if not pixels or not _valid_positive(preset_scale) or not _valid_positive(upscaling_scale):
        base["missing_inputs"] = ["supported resolution/preset/upscaling parameters"]
        return base
    t_cpu = workload.serial_work_ms_index / cpu.single_thread_index
    if workload.parallel_work_ms_index is not None:
        if cpu.performance_cores is None:
            base["missing_inputs"] = ["CPU core topology for parallel workload"]
            return base
        q_parallel = cpu.single_thread_index * parallel_efficiency(
            cpu.performance_cores, cpu.efficient_cores or 0, cpu.threads)
        t_cpu += workload.parallel_work_ms_index / q_parallel
    p_ref = 1920*1080
    pixel_factor = (pixels / p_ref / upscaling_scale) ** workload.pixel_alpha
    gpu_terms = [workload.compute_work_ms_index / gpu.compute_index]
    if workload.memory_work_ms_index is not None:
        if not _valid_positive(gpu.bandwidth_gbps):
            base["missing_inputs"] = ["GPU memory bandwidth"]
            return base
        gpu_terms.append(workload.memory_work_ms_index / gpu.bandwidth_gbps * pixel_factor)
    if workload.texture_work_ms_index is not None:
        if not _valid_positive(gpu.texture_rate):
            base["missing_inputs"] = ["GPU texture throughput"]
            return base
        gpu_terms.append(workload.texture_work_ms_index / gpu.texture_rate * pixel_factor)
    t_gpu = max(gpu_terms) * preset_scale
    if rt:
        base["missing_inputs"] = ["calibrated RT workload and RT hardware throughput"]
        return base
    extra = workload.extra_ms or 0.0
    frame = max(t_cpu, t_gpu) + extra
    if not _valid_positive(frame):
        return base
    base.update(fps=round(1000/frame, 2), cpu_frame_time_ms=round(t_cpu, 3),
                gpu_frame_time_ms=round(t_gpu, 3),
                bottleneck="CPU" if t_cpu > t_gpu else "GPU",
                confidence=workload.confidence if workload.confidence != "insufficient" else "uncalibrated",
                missing_inputs=[])
    return base


def legacy_anchored(fps: float | None, cpu_limit_fps: float | None,
                    gpu_limit_fps: float | None, *, source: str = "UpgradeLab GAME_PROFILES") -> dict:
    """Adapt the current game estimate without relabeling it as independent v3.

    This is a compatibility path until measured per-game workload anchors and
    verified hardware specifications exist. All times are derived from the
    same legacy estimate; RAM must be excluded by the caller.
    """
    result = {"average_fps": None, "cpu_frame_time_ms": None,
        "gpu_frame_time_ms": None, "bottleneck": None,
        "confidence": "insufficient_data", "method": "hardware_model_v3",
        "model_version": "3.0", "used_hardware_features": [],
        "missing_data": [], "explanation": "Недостаточно данных для FPS Engine v3."}
    if not _valid_positive(fps):
        result["missing_data"] = ["положительная опорная оценка FPS"]
        return result
    cpu_ms = 1000 / cpu_limit_fps if _valid_positive(cpu_limit_fps) else None
    gpu_ms = 1000 / gpu_limit_fps if _valid_positive(gpu_limit_fps) else None
    if cpu_ms is None or gpu_ms is None:
        result["missing_data"] = ["CPU и GPU игровые опоры"]
        return result
    result.update(average_fps=float(fps), cpu_frame_time_ms=round(cpu_ms, 3),
        gpu_frame_time_ms=round(gpu_ms, 3),
        bottleneck="CPU" if cpu_ms > gpu_ms else "GPU",
        confidence="uncalibrated", method="legacy_anchored",
        used_hardware_features=["PassMark CPU score (relative)", "PassMark GPU G3D score (relative)"],
        missing_data=["independent game workload calibration", "verified extended CPU/GPU specifications"],
        explanation=f"Игровая нагрузка и абсолютный FPS привязаны к {source}; это не независимый hardware-прогноз и не измерение.")
    return result

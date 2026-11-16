"""Offline aggregation of licensed, measured FPS observations."""
from collections import defaultdict
from statistics import mean, median, pstdev
from app.services.benchmark_data import Observation

COHORT_FIELDS = (
    'game', 'game_version', 'cpu', 'gpu', 'vram_gb', 'ram_gb', 'ram_type',
    'ram_channels', 'resolution', 'preset', 'rt', 'upscaling',
    'frame_generation', 'frame_generation_mode', 'render_scale',
    'scene', 'overclocked', 'os', 'form_factor', 'power_profile',
)


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (position - lower)


def aggregate(rows):
    """Average repeated runs inside a series before comparing independent series.

    Missing settings are retained in the key. One-percent low is not inferred
    from between-series FPS percentiles or mixed capture methods.
    """
    groups = defaultdict(lambda: defaultdict(list))
    seen = set()
    for raw in rows:
        row = Observation.model_validate(raw).model_dump()
        if row['data_type'] != 'measured':
            continue
        if row['id'] in seen:
            raise ValueError('Duplicate observation id')
        seen.add(row['id'])
        # Names are matched exactly after whitespace/case normalization; no
        # unreviewed aliases or missing values are synthesized.
        key = tuple(' '.join(row[field].split()).casefold() if field in ('cpu', 'gpu') and row[field]
                    else row[field] for field in COHORT_FIELDS)
        groups[key][(row['publisher'], row['series_id'])].append(row)
    result = []
    for key, series in groups.items():
        publisher_series = defaultdict(list)
        publisher_low_series = defaultdict(list)
        low_observations = 0
        for (publisher, _), runs in series.items():
            publisher_series[publisher].append(mean(row['average_fps'] for row in runs))
            lows = [row['one_percent_low'] for row in runs if row['one_percent_low'] is not None]
            low_observations += len(lows)
            if len(lows) == len(runs):
                publisher_low_series[publisher].append(mean(lows))
        # Each publisher contributes once after its independent series are
        # averaged; a prolific single publisher cannot outvote other sources.
        independent_values = [mean(values) for values in publisher_series.values()]
        all_observations = sum(map(len, series.values()))
        complete_low = low_observations == all_observations
        low_values = [mean(values) for values in publisher_low_series.values()] if complete_low else []
        center = median(independent_values)
        result.append({
            'settings': dict(zip(COHORT_FIELDS, key)),
            'mean_fps': mean(independent_values), 'median_fps': center,
            'p10_between_publishers_fps': percentile(independent_values, .10) if len(independent_values) >= 2 else None,
            'p90_between_publishers_fps': percentile(independent_values, .90) if len(independent_values) >= 2 else None,
            'stddev_between_publishers_fps': pstdev(independent_values),
            'mad_between_publishers_fps': median(abs(value - center) for value in independent_values),
            'observations': all_observations,
            'independent_series': len(series),
            'independent_publishers': len({publisher for publisher, _ in series}),
            'one_percent_low_fps': mean(low_values) if complete_low else None,
            'one_percent_low_observations': low_observations,
            'confidence': 'limited' if len(series) < 3 or len({p for p, _ in series}) < 2 else 'multi_source',
            'source_urls': sorted({row['source_url'] for runs in series.values() for row in runs}),
        })
    return sorted(result, key=lambda row: repr(row['settings']))

"""Information conditions and observable tool timing summaries."""
from statistics import mean


def duration_references(condition, calibration, completed, window=3):
    """Return (reference, counts); incomplete and invalid calls never enter completed."""
    if condition not in ('A', 'B', 'C'):
        raise ValueError('unknown condition')
    if window < 1 or any(not samples for samples in calibration.values()):
        raise ValueError('each tool needs calibration samples; window must be positive')
    if condition == 'A':
        return None, {}
    values, counts = {}, {}
    for name, samples in calibration.items():
        recent = completed.get(name, [])[-window:]
        used = recent if condition == 'C' and recent else samples
        values[name] = mean(used)
        counts[name] = len(used)
    return values, counts


def target_delay(profile, elapsed, budget, shift_fraction, fast, slow):
    if profile not in ('stable_fast', 'fast_to_slow', 'slow_to_fast'):
        raise ValueError('unknown latency profile')
    shifted = elapsed >= budget * shift_fraction
    if profile == 'stable_fast':
        return fast
    if profile == 'fast_to_slow':
        return slow if shifted else fast
    return fast if shifted else slow

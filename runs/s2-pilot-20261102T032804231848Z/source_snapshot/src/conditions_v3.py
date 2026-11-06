"""Study 2 information ladder: none / static prior / adaptive / oracle.

Condition semantics (identical observables, one difference in the observation):
  A  no duration reference at all (raw history and time_status only)
  B  per-tool mean of the pre-episode calibration samples (a static prior)
  C  per-tool mean of the last <=window completed calls, calibration fallback
  O  the delay the host is applying *right now* (perfect instantaneous oracle)

A/B/C/O share the same question, tools, budget and clock. O is an information
upper bound, not a deployable interface; it quantifies how much any latency
predictor could ever change the outcome in this environment.
"""
from statistics import mean

from src.conditions import target_delay

CONDITIONS = ('A', 'B', 'C', 'O')
DESCRIPTIONS = {
    'B': '基于开局前历史观察的固定参考值，不保证未来调用耗时。',
    'C': '基于最近若干次同类调用观察的参考值，不保证未来调用耗时。',
    'O': '宿主当前时刻实际施加的工具耗时；该值可能随时间变化。',
}


def duration_references(condition, calibration, completed, window=3, oracle=None):
    """Return (reference, counts); incomplete and invalid calls never enter completed."""
    if condition not in CONDITIONS:
        raise ValueError('unknown condition')
    if window < 1 or any(not samples for samples in calibration.values()):
        raise ValueError('each tool needs calibration samples; window must be positive')
    if condition == 'A':
        return None, {}
    if condition == 'O':
        if not oracle or set(oracle) != set(calibration):
            raise ValueError('oracle requires one value per tool')
        return dict(oracle), {}
    values, counts = {}, {}
    for name, samples in calibration.items():
        recent = list(completed.get(name, []))[-window:]
        used = recent if condition == 'C' and recent else list(samples)
        values[name] = mean(used)
        counts[name] = len(used)
    return values, counts


def reference_error(condition, reference, actual):
    """Absolute error of the reference supplied for a call, for behaviour analysis."""
    if reference is None or actual is None:
        return None
    return abs(reference - actual)


__all__ = ['CONDITIONS', 'DESCRIPTIONS', 'duration_references', 'target_delay',
           'reference_error']

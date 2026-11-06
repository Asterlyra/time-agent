"""Study 2 information ladder: none / static prior / adaptive / oracle.

Condition semantics (identical observables, one difference in the observation):
  A  no duration reference at all (raw history and time_status only)
  B  per-tool mean of the pre-episode calibration samples (a static prior)
  C  per-tool mean of the last <=window completed calls, calibration fallback
  O  the delay the host is applying *right now* (perfect instantaneous oracle)

A/B/C/O share the same question, tools, budget and clock. O is an information
upper bound, not a deployable interface; it quantifies how much any latency
predictor could ever change the outcome in this environment.

Latency profiles (the delay of a call is fixed by the moment the call starts):
  stable_fast   constant fast
  fast_to_slow  fast, then slow after shift_fraction of the budget
  slow_to_fast  slow, then fast after shift_fraction of the budget
  drift_up      geometric drift from fast to slow across the whole budget,
                d(t) = fast * (slow/fast) ** (t/budget)
"""
from statistics import mean

CONDITIONS = ('A', 'B', 'C', 'O')
PROFILES = ('stable_fast', 'fast_to_slow', 'slow_to_fast', 'drift_up')
DESCRIPTIONS = {
    'B': '基于开局前历史观察的固定参考值，不保证未来调用耗时。',
    'C': '基于最近若干次同类调用观察的参考值，不保证未来调用耗时。',
    'O': '宿主当前时刻实际施加的工具耗时；该值可能随时间变化。',
}


def target_delay(profile, elapsed, budget, shift_fraction, fast, slow):
    if profile not in PROFILES:
        raise ValueError('unknown latency profile')
    if profile == 'drift_up':
        if budget <= 0 or fast <= 0:
            raise ValueError('drift profile needs a positive budget and fast delay')
        ratio = slow / fast
        return fast * ratio ** min(1.0, max(0.0, elapsed / budget))
    shifted = elapsed >= budget * shift_fraction
    if profile == 'stable_fast':
        return fast
    if profile == 'fast_to_slow':
        return slow if shifted else fast
    return fast if shifted else slow


def duration_references(condition, calibration, completed, window=1, oracle=None):
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


__all__ = ['CONDITIONS', 'PROFILES', 'DESCRIPTIONS', 'duration_references', 'target_delay']

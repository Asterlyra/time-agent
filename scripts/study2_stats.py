"""S2 statistics: paired cluster bootstrap, randomisation test, behaviour metrics.

Unit of inference. The S2 environment is a single scenario instantiated with
fresh random item values, so a task instance is an exchangeable replicate, not a
distinct benchmark item. The independent unit is therefore the (model, task,
profile) block in which all four conditions were run back to back; resampling
draws whole blocks and uses the same draw for all three models so that the
model-averaged contrast stays paired.
"""
import argparse
import collections
import math
import json
import random
import statistics
from pathlib import Path

MODELS = ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash')
CONDITIONS = ('A', 'B', 'C', 'O')
PROFILES = ('stable_fast', 'fast_to_slow', 'drift_up')
CONTRASTS = (('B', 'A'), ('C', 'A'), ('C', 'B'), ('O', 'A'), ('O', 'B'), ('O', 'C'))


def load(batch):
    batch = Path(batch)
    config = json.loads((batch / 'config.json').read_text())
    records = []
    # Archived host-suspend failures are re-accounted as score-0 observations so the
    # matrix stays complete; they are flagged and never presented as model behaviour.
    for archive in sorted((batch / 'environment_failures').glob('*.json')):
        if archive.name == 'MANIFEST.json':
            continue
        row = json.loads(archive.read_text())
        records.append({
            'model': row['manifest']['model_id'], 'task_id': row['manifest']['task_id'],
            'profile': row['manifest']['profile'], 'condition': row['manifest']['condition'],
            'block_id': row['manifest']['block_id'], 'score': 0, 'total_items': None,
            'submitted': False, 'termination': 'environment_interruption',
            'elapsed_s': row['result'].get('elapsed_s'), 'budget_s': None,
            'n_fetches': 0, 'n_requests': 0, 'submit_remaining_s': None,
            'last_fetch_remaining_s': None, 'request_wall_s': [], 'tool_durations_s': [],
            'references': [], 'decisions': [], 'reference_errors': [], 'archived': True})
    for path in sorted((batch / 'episodes').glob('*.json')):
        row = json.loads(path.read_text())
        entry, result = row['manifest'], row['result']
        events = result.get('events') or []
        tools = [e for e in events if isinstance(e, dict) and e.get('event_type') == 'tool'
                 and not e.get('invalid') and 'observed_duration_s' in e]
        requests = [e for e in events if isinstance(e, dict) and e.get('event_type') == 'model_request'
                    and 'response_end_offset_s' in e]
        records.append({
            'model': entry['model_id'], 'task_id': entry['task_id'], 'profile': entry['profile'],
            'condition': entry['condition'], 'block_id': entry['block_id'],
            'score': int(result.get('score') or 0),
            'total_items': result.get('total_items'),
            'submitted': result['termination_reason'] == 'submitted',
            'termination': result['termination_reason'],
            'elapsed_s': result.get('elapsed_s'),
            'budget_s': result.get('budget_s'),
            'n_fetches': len(tools),
            'n_requests': len(requests),
            'submit_remaining_s': (result['budget_s'] - result['elapsed_s'])
            if result['termination_reason'] == 'submitted' else None,
            'last_fetch_remaining_s': (result['budget_s'] - tools[-1]['tool_start_offset_s'])
            if tools else None,
            'request_wall_s': [r['response_end_offset_s'] - r['request_start_offset_s'] for r in requests],
            'tool_durations_s': [t['observed_duration_s'] for t in tools],
            'archived': bool(result.get('archived_interruption')),
            'references': [r['observation'].get('duration_reference_s', {}).get('fetch')
                           for r in requests],
            'decisions': [{'remaining': r['remaining_at_request_s'],
                           'reference': r['observation'].get('duration_reference_s', {}).get('fetch'),
                           'fetched': isinstance(r.get('action'), dict) and r['action'].get('type') == 'tool',
                           'valid': isinstance(r.get('action'), dict),
                           'collected': (r['observation'].get('collected_items') or {}).get('count')}
                          for r in requests],
            'reference_errors': [(t.get('reference_at_request_s'), t.get('observed_duration_s'))
                                 for t in tools if t.get('reference_at_request_s') is not None],
        })
    return config, records


def _mean(xs):
    return statistics.mean(xs) if xs else None


def _cells(records):
    out = collections.OrderedDict()
    for profile in PROFILES:
        for model in MODELS:
            for condition in CONDITIONS:
                z = [r for r in records if r['profile'] == profile and r['model'] == model
                     and r['condition'] == condition]
                if not z:
                    continue
                out[(profile, model, condition)] = {
                    'n': len(z),
                    'mean_score': _mean([r['score'] for r in z]),
                    'median_score': statistics.median([r['score'] for r in z]),
                    'p_submitted': _mean([r['submitted'] for r in z]),
                    'mean_fetches': _mean([r['n_fetches'] for r in z]),
                    'mean_last_fetch_remaining_s': _mean([r['last_fetch_remaining_s'] for r in z
                                                          if r['last_fetch_remaining_s'] is not None]),
                    'max_score': max(r['score'] for r in z),
                    'mean_request_wall_s': _mean([statistics.mean(r['request_wall_s'])
                                                  for r in z if r['request_wall_s']]),
                }
    return out


def _paired(records, profile, x, y):
    """(model, task) -> score difference, only where both conditions exist."""
    index = {(r['model'], r['task_id'], r['condition']): r
             for r in records if r['profile'] == profile}
    tasks = sorted({r['task_id'] for r in records if r['profile'] == profile})
    diffs = {}
    for model in MODELS:
        for task in tasks:
            a, b = index.get((model, task, x)), index.get((model, task, y))
            if a is not None and b is not None:
                diffs[(model, task)] = a['score'] - b['score']
    return diffs, tasks


def contrast(records, profile, x, y, *, draws=10000, seed=911):
    diffs, tasks = _paired(records, profile, x, y)
    if not diffs:
        return None
    by_model = {m: [diffs[(m, t)] for t in tasks if (m, t) in diffs] for m in MODELS}
    point_models = {m: _mean(v) for m, v in by_model.items() if v}
    point = _mean(list(point_models.values()))
    rng = random.Random(seed)
    stats = []
    for _ in range(draws):
        draw = [rng.choice(tasks) for _ in tasks]
        per_model = []
        for m in MODELS:
            values = [diffs[(m, t)] for t in draw if (m, t) in diffs]
            if values:
                per_model.append(_mean(values))
        if per_model:
            stats.append(_mean(per_model))
    stats.sort()
    lo = stats[int(.025 * len(stats))]
    hi = stats[int(.975 * len(stats)) - 1]
    # Randomisation test: sign-flip each task's model-averaged difference.
    task_level = []
    for task in tasks:
        values = [diffs[(m, task)] for m in MODELS if (m, task) in diffs]
        if values:
            task_level.append(_mean(values))
    extreme = sum(1 for v in task_level if v != 0)
    hits = 0
    flips = 2000
    for _ in range(flips):
        acc = [v if rng.random() < .5 else -v for v in task_level]
        if abs(_mean(acc)) >= abs(point):
            hits += 1
    p = (hits + 1) / (flips + 1)
    return {'profile': profile, 'contrast': f'{x}-{y}', 'pooled': point,
            'per_model': point_models, 'ci': [lo, hi],
            'n_blocks': len(tasks), 'n_pairs': len(diffs),
            'p_randomisation': p, 'nonzero_task_diffs': extreme}


def behaviour(records):
    out = {}
    for profile in PROFILES:
        for condition in CONDITIONS:
            z = [r for r in records if r['profile'] == profile and r['condition'] == condition]
            if not z:
                continue
            out[f'{profile}:{condition}'] = {
                'n': len(z),
                'p_submitted': _mean([r['submitted'] for r in z]),
                'mean_last_fetch_remaining_s': _mean([r['last_fetch_remaining_s'] for r in z
                                                      if r['last_fetch_remaining_s'] is not None]),
                'mean_submit_remaining_s': _mean([r['submit_remaining_s'] for r in z
                                                  if r['submit_remaining_s'] is not None]),
                'mean_fetches': _mean([r['n_fetches'] for r in z]),
                'max_reference': max([max([v for v in r['references'] if v is not None], default=0)
                                      for r in z], default=None),
            }
    return out


def decision_curve(records, edges=(0, 20, 40, 60, 80, 100, 130, 170, 210)):
    """Probability of another fetch as a function of remaining time, per condition."""
    out = {}
    for profile in PROFILES:
        for condition in CONDITIONS:
            z = [d for r in records if r['profile'] == profile and r['condition'] == condition
                 for d in r['decisions']]
            if not z:
                continue
            buckets = []
            for lo, hi in zip(edges, edges[1:]):
                bucket = [d for d in z if lo <= d['remaining'] < hi]
                if bucket:
                    buckets.append({'remaining_lo': lo, 'remaining_hi': hi, 'n': len(bucket),
                                    'p_fetch': _mean([d['fetched'] for d in bucket])})
            out[f'{profile}:{condition}'] = buckets
    return out


def reference_error(records):
    """Mean absolute error between the displayed reference and the delay actually applied."""
    out = {}
    for profile in PROFILES:
        for condition in CONDITIONS:
            pairs = [p for r in records if r['profile'] == profile and r['condition'] == condition
                     for p in r['reference_errors']]
            if not pairs:
                continue
            out[f'{profile}:{condition}'] = {
                'n': len(pairs),
                'mae_s': _mean([abs(a - b) for a, b in pairs]),
                'signed_mean_s': _mean([b - a for a, b in pairs])}
    return out


def stop_threshold(records):
    """Logistic fit of "make another fetch" on remaining time, per condition.

    A single-predictor IRLS fit gives the remaining time at which the predicted
    probability of continuing falls through one half, i.e. the agent's effective
    stopping threshold. If the displayed latency reference drives the decision, the
    threshold should move with it across conditions; if it does not, the interface
    is inert.
    """
    def fit(xs, ys):
        beta = [0.0, 0.0]
        for _ in range(60):
            g = [0.0, 0.0]
            h = [[0.0, 0.0], [0.0, 0.0]]
            for x, y in zip(xs, ys):
                eta = beta[0] + beta[1] * x
                p = 1 / (1 + math.exp(-max(-30.0, min(30.0, eta))))
                w = max(p * (1 - p), 1e-9)
                g[0] += y - p
                g[1] += (y - p) * x
                h[0][0] += w
                h[0][1] += w * x
                h[1][0] += w * x
                h[1][1] += w * x * x
            det = h[0][0] * h[1][1] - h[0][1] * h[1][0]
            if abs(det) < 1e-12:
                return None
            step = [(h[1][1] * g[0] - h[0][1] * g[1]) / det,
                    (-h[1][0] * g[0] + h[0][0] * g[1]) / det]
            beta = [beta[0] + step[0], beta[1] + step[1]]
            if abs(step[0]) + abs(step[1]) < 1e-9:
                break
        if beta[1] <= 0:
            return None  # no positive relation between remaining time and continuing
        return -beta[0] / beta[1]

    out = {}
    for profile in PROFILES:
        for condition in CONDITIONS:
            decisions = [d for r in records if r['profile'] == profile and r['condition'] == condition
                         for d in r['decisions'] if d['valid']]
            if len(decisions) < 20:
                out[f'{profile}:{condition}'] = {'n': len(decisions), 'threshold_s': None}
                continue
            threshold = fit([d['remaining'] for d in decisions], [1.0 if d['fetched'] else 0.0 for d in decisions])
            references = [d['reference'] for d in decisions if d['reference'] is not None]
            out[f'{profile}:{condition}'] = {
                'n': len(decisions),
                'threshold_s': round(threshold, 1) if threshold else None,
                'mean_reference_s': round(_mean(references), 1) if references else None,
                'p_fetch': round(_mean([1.0 if d['fetched'] else 0.0 for d in decisions]), 3)}
    return out


def stopping_regret(records):
    """Counterfactual value of stopping earlier.

    At every request the host knows how many items are already banked and how much
    budget is left. Submitting at that request would have scored that count as long
    as the request itself completed before the deadline. The regret is the best such
    counterfactual minus what the episode actually scored; it measures how much was
    lost by continuing rather than by any latency estimate.
    """
    out = {}
    for profile in PROFILES:
        for condition in CONDITIONS:
            z = [r for r in records if r['profile'] == profile and r['condition'] == condition]
            if not z:
                continue
            regrets, misses = [], 0
            for r in z:
                best = 0
                for d in r['decisions']:
                    if d['collected'] is None:
                        continue
                    # A submission issued here completes only if the remaining budget
                    # covers this request; request time is unknown a priori, so use a
                    # conservative 5 s guard rather than 0.
                    if d['remaining'] > 5.0:
                        best = max(best, d['collected'])
                regrets.append(best - r['score'])
                misses += 1 if r['score'] == 0 else 0
            out[f'{profile}:{condition}'] = {
                'n': len(z), 'mean_regret': _mean(regrets), 'zero_episodes': misses,
                'share_of_best_lost': _mean([g / b for g, b in
                                            ((g, max(1, g + r['score'])) for g, r in zip(regrets, z))])}
    return out


def _batch_request_times(batch):
    """Per-model request wall times measured inside this batch."""
    import glob as _glob
    out = collections.defaultdict(list)
    for path in _glob.glob(str(Path(batch) / 'episodes' / '*.json')):
        row = json.loads(Path(path).read_text())
        model = row['manifest']['model_id']
        for event in row['result'].get('events') or []:
            if isinstance(event, dict) and event.get('event_type') == 'model_request' \
                    and 'response_end_offset_s' in event:
                out[model].append(event['response_end_offset_s'] - event['request_start_offset_s'])
    return {k: sorted(v) for k, v in out.items() if v}


def planner_benchmark(config, batch=None, *, n=800, seed=7):
    """Simulated rational-planner score for each (profile, model, belief).

    Request latency is resampled from this batch's own measurements when available,
    so the benchmark reflects the service conditions the agents actually faced;
    Study 1 latencies are the fallback.
    """
    from scripts.study2_simulate import empirical_request_times, run
    times = _batch_request_times(batch) if batch else {}
    if not times:
        times = empirical_request_times()
    out = {}
    for profile in PROFILES:
        for model in MODELS:
            if model not in times:
                continue
            for belief in ('B', 'C', 'O'):
                rng = random.Random(seed)
                values = []
                for _ in range(n):
                    score, _term = run(profile, belief, budget=config['budget_by_model'][model],
                                       shift=config['shift_fraction'], fast=config['fast_s'],
                                       slow=config['slow_s'], request_times=times[model], rng=rng,
                                       window=config['window'])
                    values.append(score)
                out[f'{profile}|{model}|{belief}'] = round(_mean(values), 2)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--out', default=None)
    parser.add_argument('--draws', type=int, default=10000)
    args = parser.parse_args()
    config, records = load(args.batch)
    cells = _cells(records)
    contrasts = [c for profile in PROFILES for c in
                 [contrast(records, profile, x, y, draws=args.draws) for x, y in CONTRASTS] if c]
    summary = {
        'batch': str(args.batch), 'stage': config['stage'], 'n_episodes': len(records),
        'n_archived_environment_failures': sum(1 for r in records if r.get('archived')),
        'budget_by_model': config.get('budget_by_model'), 'fast_s': config.get('fast_s'),
        'slow_s': config.get('slow_s'), 'shift_fraction': config.get('shift_fraction'),
        'cells': {f'{p}|{m}|{c}': v for (p, m, c), v in cells.items()},
        'contrasts': contrasts,
        'behaviour': behaviour(records),
        'reference_error': reference_error(records),
        'stopping_regret': stopping_regret(records),
        'stop_threshold': stop_threshold(records),
        'planner_benchmark': planner_benchmark(config, args.batch),
        'decision_curve': decision_curve(records),
        'primary': next((c for c in contrasts
                         if c['profile'] == 'drift_up' and c['contrast'] == 'C-B'),
                        next((c for c in contrasts
                              if c['profile'] == 'fast_to_slow' and c['contrast'] == 'C-B'), None)),
    }
    out = Path(args.out) if args.out else Path(args.batch) / 'stats_summary.json'
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'primary': summary['primary'], 'out': str(out)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

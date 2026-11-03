"""Study 3 statistics: block-cluster paired bootstrap over the five arms.

Inference unit is the (model, task, regime) block in which all five arms run back
to back. Resampling draws whole blocks and uses the same draw for every model so
the model-averaged contrast stays paired. Primary estimand is fixed in advance:
heterogeneous family, E minus I0, equal weight over the four models.
"""
import argparse
import collections
import json
import math
import random
import statistics
from pathlib import Path

MODELS = ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash', 'mimo-v2.6-flash')
ARMS = ('I0', 'I1', 'C', 'E', 'O')
FAMILIES = ('uniform', 'hetero')
REGIMES = ('light_tail', 'fast_heavy', 'slow_heavy', 'drift_heavy')
CONTRASTS = (('E', 'I0'), ('I1', 'I0'), ('C', 'I0'), ('C', 'E'), ('E', 'O'), ('O', 'I0'))


def load(batch):
    batch = Path(batch)
    config = json.loads((batch / 'config.json').read_text())
    records = []
    archive = batch / 'environment_failures'
    if archive.exists():
        for path in sorted(archive.glob('*.json')):
            if path.name == 'MANIFEST.json':
                continue
            row = json.loads(path.read_text())
            records.append({'model': row['manifest']['model_id'], 'task_id': row['manifest']['task_id'],
                            'family': row['manifest']['task_family'], 'regime': row['manifest']['regime'],
                            'arm': row['manifest']['condition'], 'block_id': row['manifest']['block_id'],
                            'score': 0, 'termination': 'environment_interruption',
                            'forced': False, 'denied': 0, 'banked': 0, 'archived': True,
                            'elapsed_s': row['result'].get('elapsed_s'),
                            'budget_s': row['manifest'].get('budget_s')})
    for path in sorted((batch / 'episodes').glob('*.json')):
        row = json.loads(path.read_text())
        entry, result = row['manifest'], row['result']
        details = result.get('verifier_details') or {}
        records.append({'model': entry['model_id'], 'task_id': entry['task_id'],
                        'family': entry['task_family'], 'regime': entry['regime'],
                        'arm': entry['condition'], 'block_id': entry['block_id'],
                        'score': result.get('score') or 0,
                        'termination': result['termination_reason'],
                        'forced': bool(result.get('forced_submit')),
                        'denied': result.get('denied_fetches', 0),
                        'banked': details.get('banked', 0),
                        'archived': bool(result.get('archived_interruption')),
                        'elapsed_s': result.get('elapsed_s'),
                        'budget_s': result.get('budget_s')})
    return config, records


def _mean(values):
    return statistics.mean(values) if values else None


def cells(records):
    out = collections.OrderedDict()
    for family in FAMILIES:
        for regime in REGIMES:
            for arm in ARMS:
                z = [r for r in records if r['family'] == family and r['regime'] == regime and r['arm'] == arm]
                if not z:
                    continue
                out[f'{family}|{regime}|{arm}'] = {
                    'n': len(z), 'mean_score': _mean([r['score'] for r in z]),
                    'p_submitted': _mean([1.0 if r['termination'] in ('submitted', 'forced_submit') else 0.0 for r in z]),
                    'p_forced': _mean([1.0 if r['forced'] else 0.0 for r in z]),
                    'mean_banked': _mean([r['banked'] for r in z]),
                    'mean_denied': _mean([r['denied'] for r in z]),
                    'termination': dict(collections.Counter(r['termination'] for r in z))}
    return out


def _paired(records, family, regime, x, y):
    # A cell is (model, task, arm) and contains `repeats` episodes. Repeats are averaged inside
    # the cell before pairing: every repeat is an equal draw from the same cell, and keeping one
    # of them arbitrarily would both discard data and make the estimate depend on file order.
    pool = collections.defaultdict(list)
    for r in records:
        if r['family'] != family:
            continue
        if regime is not None and r['regime'] != regime:
            continue
        pool[(r['model'], r['task_id'], r['arm'])].append(r['score'])
    index = {key: _mean(values) for key, values in pool.items()}
    tasks = sorted({r['task_id'] for r in records if r['family'] == family
                    and (regime is None or r['regime'] == regime)})
    diffs = {}
    for model in MODELS:
        for task in tasks:
            a, b = index.get((model, task, x)), index.get((model, task, y))
            if a is not None and b is not None:
                diffs[(model, task)] = a - b
    return diffs, tasks


def contrast(records, family, regime, x, y, *, draws=10000, seed=911):
    diffs, tasks = _paired(records, family, regime, x, y)
    if not diffs:
        return None
    by_model = {m: [diffs[(m, t)] for t in tasks if (m, t) in diffs] for m in MODELS}
    per_model = {m: _mean(v) for m, v in by_model.items() if v}
    point = _mean(list(per_model.values()))
    rng = random.Random(seed)
    stats = []
    for _ in range(draws):
        draw = [rng.choice(tasks) for _ in tasks]
        values = []
        for model in MODELS:
            picked = [diffs[(model, t)] for t in draw if (model, t) in diffs]
            if picked:
                values.append(_mean(picked))
        if values:
            stats.append(_mean(values))
    stats.sort()
    lo = stats[int(.025 * len(stats))]
    hi = stats[int(.975 * len(stats)) - 1]
    task_level = []
    for task in tasks:
        values = [diffs[(m, task)] for m in MODELS if (m, task) in diffs]
        if values:
            task_level.append(_mean(values))
    hits = 0
    flips = 2000
    for _ in range(flips):
        acc = [v if rng.random() < .5 else -v for v in task_level]
        if abs(_mean(acc)) >= abs(point):
            hits += 1
    sd = statistics.stdev(stats) if len(stats) > 2 else float('nan')
    return {'family': family, 'regime': regime or 'all', 'contrast': f'{x}-{y}',
            'pooled': point, 'per_model': per_model, 'ci': [lo, hi],
            'se': sd, 'z': (point / sd) if sd and sd == sd and sd > 0 else None,
            'p_randomisation': (hits + 1) / (flips + 1),
            'n_blocks': len(tasks), 'n_pairs': len(diffs)}


def model_cells(records):
    """Per-model arm aggregates over all regimes, for the "who benefits" analysis."""
    out = collections.OrderedDict()
    for family in FAMILIES:
        for arm in ARMS:
            for model in MODELS:
                z = [r for r in records if r['family'] == family and r['arm'] == arm and r['model'] == model]
                if not z:
                    continue
                out[f'{family}|{arm}|{model}'] = {
                    'n': len(z), 'mean_score': _mean([r['score'] for r in z]),
                    'p_timeout_model': _mean([1.0 if r['termination'] == 'timeout_model' else 0.0 for r in z]),
                    'p_submitted': _mean([1.0 if r['termination'] in ('submitted', 'forced_submit') else 0.0 for r in z]),
                    'p_forced': _mean([1.0 if r['forced'] else 0.0 for r in z]),
                    'mean_banked': _mean([r['banked'] for r in z])}
    return out


def behaviour(records):
    out = {}
    for family in FAMILIES:
        for arm in ARMS:
            z = [r for r in records if r['family'] == family and r['arm'] == arm]
            if not z:
                continue
            out[f'{family}|{arm}'] = {
                'n': len(z),
                'p_submitted': _mean([1.0 if r['termination'] in ('submitted', 'forced_submit') else 0.0 for r in z]),
                'p_forced': _mean([1.0 if r['forced'] else 0.0 for r in z]),
                'mean_banked': _mean([r['banked'] for r in z]),
                'mean_denied': _mean([r['denied'] for r in z]),
                'termination': dict(collections.Counter(r['termination'] for r in z))}
    return out


def _interrupted(record):
    return bool(record['archived']) or record['termination'] == 'environment_interruption'


def sensitivity(records, *, draws=2000):
    """Re-estimate the pre-specified contrasts with host interruptions dropped rather than zeroed.

    Scoring an interrupted episode zero assumes the interruption is independent of the arm; it is
    not, because an episode that is still running when the host pauses is more likely to be one
    that never stops by itself, which is what the I0/I1 arms do most. Dropping such episodes
    removes the pair instead of imputing a zero, so the two policies bracket the answer.
    """
    dropped = collections.Counter(
        f"{r['family']}|{r['arm']}" for r in records if _interrupted(r))
    kept = [r for r in records if not _interrupted(r)]
    rows = {}
    for family in FAMILIES:
        for x, y in CONTRASTS:
            zero = contrast(records, family, None, x, y, draws=draws)
            drop = contrast(kept, family, None, x, y, draws=draws)
            if not zero or not drop:
                continue
            rows[f'{family}|{x}-{y}'] = {
                'zero_policy': {'pooled': zero['pooled'], 'ci': zero['ci'], 'n_pairs': zero['n_pairs']},
                'drop_policy': {'pooled': drop['pooled'], 'ci': drop['ci'], 'n_pairs': drop['n_pairs']},
                'delta': drop['pooled'] - zero['pooled'],
                'sign_flip': (drop['pooled'] > 0) != (zero['pooled'] > 0),
                'ci_loses_zero_under_drop': not (drop['ci'][0] <= 0.0 <= drop['ci'][1])}
    return {'dropped_by_cell': dict(sorted(dropped.items())),
            'n_dropped': sum(dropped.values()), 'n_kept': len(kept), 'contrasts': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--out', default=None)
    parser.add_argument('--draws', type=int, default=10000)
    args = parser.parse_args()
    config, records = load(args.batch)
    table = cells(records)
    contrasts = []
    for family in FAMILIES:
        for regime in [None] + list(REGIMES):
            for x, y in CONTRASTS:
                row = contrast(records, family, regime, x, y, draws=args.draws)
                if row:
                    contrasts.append(row)
    primary = next(c for c in contrasts
                   if c['family'] == 'hetero' and c['regime'] == 'all' and c['contrast'] == 'E-I0')
    manifest = json.loads((Path(args.batch) / 'manifest.json').read_text())
    summary = {'batch': str(args.batch), 'part': config.get('part'),
               'planned': len(manifest), 'n_episodes': len(records),
               'n_archived_environment_failures': sum(1 for r in records if r.get('archived')),
               'cells': {k: v for k, v in table.items()},
               'contrasts': contrasts, 'behaviour': behaviour(records), 'model_cells': model_cells(records),
               'sensitivity': sensitivity(records, draws=max(2000, args.draws // 5)),
               'primary': primary}
    out = Path(args.out) if args.out else Path(args.batch) / 'stats_summary.json'
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'primary': primary, 'out': str(out)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Read recorded episode results and report paired, task-clustered differences."""
import argparse
import collections
import json
import random
from pathlib import Path


def summarize(directory, seed=911, iterations=10000):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    rows = []
    missing = []
    for entry in manifest:
        p = directory / 'episodes' / (entry['run_id'] + '.json')
        if not p.exists():
            missing.append(entry['run_id'])
            continue
        row = json.loads(p.read_text(encoding='utf-8'))
        if row['manifest'] != entry:
            raise ValueError('episode manifest mismatch: ' + entry['run_id'])
        rows.append(row)
    cells = collections.defaultdict(list)
    blocks = collections.defaultdict(dict)
    for row in rows:
        e, r = row['manifest'], row['result']
        cells[(e['model_id'], e['profile'], e['condition'])].append(r)
        blocks[(e['model_id'], e['profile'], e['task_id'], e['repeat'])][e['condition']] = bool(r['deadline_success'])
    table = []
    for (model, profile, condition), values in sorted(cells.items()):
        n = len(values)
        table.append({'model_id': model, 'profile': profile, 'condition': condition,
                      'n': n, 'successes': sum(bool(v['deadline_success']) for v in values),
                      'termination_counts': dict(collections.Counter(v['termination_reason'] for v in values))})
    # Require each included task's B/C entries for every planned model and repeat.
    # This keeps the model set fixed in every cluster bootstrap draw. It is still
    # a selected complete-case subset if any planned result is missing.
    planned = collections.defaultdict(set)
    expected_models = {e['model_id'] for e in manifest if e['profile'] == 'fast_to_slow'}
    for e in manifest:
        if e['profile'] == 'fast_to_slow' and e['condition'] in ('B', 'C'):
            planned[e['task_id']].add((e['model_id'], e['repeat'], e['condition']))
    observed = collections.defaultdict(set)
    for row in rows:
        e = row['manifest']
        if e['profile'] == 'fast_to_slow' and e['condition'] in ('B', 'C'):
            observed[e['task_id']].add((e['model_id'], e['repeat'], e['condition']))
    eligible = {task for task, requirements in planned.items()
                if requirements <= observed[task]
                and {model for model, _, _ in requirements} == expected_models}
    excluded = sorted(set(planned) - eligible)
    paired = [(k, v) for k,v in blocks.items() if k[1] == 'fast_to_slow' and k[2] in eligible and 'B' in v and 'C' in v]
    by_task = collections.defaultdict(list)
    for (model, profile, task, repeat), v in paired:
        by_task[task].append((model, int(v['C']) - int(v['B'])))
    def mean_diff(sampled):
        by_model = collections.defaultdict(list)
        for task in sampled:
            for model, d in by_task[task]:
                by_model[model].append(d)
        if set(by_model) != expected_models:
            raise ValueError('incomplete model set in bootstrap draw')
        means = [sum(by_model[m])/len(by_model[m]) for m in sorted(expected_models)]
        return sum(means)/len(means)
    tasks = sorted(by_task)
    estimate = mean_diff(tasks) if tasks else None
    interval = None
    if tasks:
        rng = random.Random(seed)
        samples = sorted(mean_diff([rng.choice(tasks) for _ in tasks]) for _ in range(iterations))
        interval = [samples[int(.025 * (iterations-1))], samples[int(.975 * (iterations-1))]]
    return {'counts': table, 'expected_episodes': len(manifest), 'completed_episodes': len(rows),
            'missing_run_ids': missing, 'paired_blocks_fast_to_slow': len(paired),
            'task_clusters': len(tasks), 'excluded_incomplete_task_ids': excluded,
            'models_in_aggregate': sorted(expected_models), 'C_minus_B_equal_model_mean': estimate,
            'bootstrap_95_percentile': interval, 'bootstrap_iterations': iterations, 'analysis_seed': seed,
            'warning': 'Tasks with any missing planned B/C result are excluded; the result is a selected complete-case sensitivity estimate, not the full-sample effect. Small clusters give unstable intervals.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('batch')
    parser.add_argument('--seed', type=int, default=911)
    parser.add_argument('--iterations', type=int, default=10000)
    args = parser.parse_args()
    if args.iterations < 1: parser.error('iterations must be positive')
    print(json.dumps(summarize(args.batch, args.seed, args.iterations), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()

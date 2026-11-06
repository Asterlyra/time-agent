"""Behavioural metrics that the score alone hides.

The primary endpoint is points, but a paper about *stopping* needs to say what the
points were made of: how much work was collected and then forfeited, how far each
episode ended from the best submission it could have made with the same calls, and
what the extra calls cost in model time and money.

Definitions, all computed from the archived episode records:

ceiling       sum of every item's points in that instance (from tasks.data_v7).
collected     sum of points of the fetches that actually completed.
forfeited     collected - score, i.e. work that was done and never submitted.
forfeited_share  forfeited / collected, i.e. the share of finished work thrown away.
model_time    wall-clock time not spent inside a tool call, i.e. the agent thinking
              and the provider serving.
cost          provider allowance summed over every model request (USD).

Writes <batch>/metrics_summary.json.
"""
import argparse
import collections
import json
import statistics
from pathlib import Path

from tasks import data_v7

ARMS = ('I0', 'I1', 'C', 'E', 'O')
FAMILIES = ('uniform', 'hetero')


def ceilings():
    return {task['task_id']: float(sum(task['private']['values'].values()))
            for task in data_v7.generate('test')}


def episode_metrics(row, ceiling):
    manifest, result = row['manifest'], row['result']
    events = result.get('events') or []
    calls = denied = 0
    tool_time = 0.0
    collected = 0.0
    model_time = 0.0
    cost = 0.0
    for event in events:
        kind = event.get('event_type')
        if kind == 'model_request':
            for attempt in event.get('attempts') or []:
                usage = (attempt.get('adapter_diagnostics') or {}).get('usage') or {}
                cost += float(usage.get('allowance') or 0.0)
            continue
        if kind != 'tool':
            continue
        start = event.get('tool_start_offset_s')
        if event.get('admitted') is False:
            denied += 1
            continue
        calls += 1
        end = event.get('tool_end_offset_s')
        if start is not None and end is not None:
            tool_time += max(0.0, end - start)
        if end is not None and not event.get('is_censored'):
            value = (event.get('tool_result') or {}).get('value')
            if isinstance(value, (int, float)):
                collected += float(value)
    elapsed = float(result.get('elapsed_s') or 0.0)
    model_time = max(0.0, elapsed - tool_time)
    score = float(result.get('score') or 0)
    submitted = result.get('termination_reason') in ('submitted', 'forced_submit')
    return {
        'family': manifest['task_family'], 'arm': manifest['condition'],
        'model': manifest['model_id'], 'task_id': manifest['task_id'],
        'regime': manifest['regime'], 'repeat': manifest.get('repeat'),
        'score': score, 'ceiling': ceiling, 'calls': calls, 'denied': denied,
        'collected': collected,
        'forfeited': max(0.0, collected - score),
        'model_time_s': model_time, 'cost': cost,
        'submitted': submitted,
        'slack_s': (float(result.get('budget_s') or 0.0) - elapsed) if submitted else None,
    }


def summarise(rows):
    if not rows:
        return None
    out = {'n': len(rows)}
    out['score'] = statistics.mean(r['score'] for r in rows)
    out['ceiling_share'] = statistics.mean(
        r['score'] / r['ceiling'] for r in rows if r['ceiling'])
    out['share_zero'] = statistics.mean(1.0 if r['score'] == 0 else 0.0 for r in rows)
    out['collected'] = statistics.mean(r['collected'] for r in rows)
    out['forfeited'] = statistics.mean(r['forfeited'] for r in rows)
    out['forfeited_share'] = statistics.mean(
        r['forfeited'] / r['collected'] for r in rows if r['collected'] > 0)
    out['calls'] = statistics.mean(r['calls'] for r in rows)
    out['denied'] = statistics.mean(r['denied'] for r in rows)
    out['model_time_s'] = statistics.mean(r['model_time_s'] for r in rows)
    out['points_per_100s'] = (100.0 * out['score'] / out['model_time_s']) if out['model_time_s'] else None
    out['cost_usd'] = statistics.mean(r['cost'] for r in rows)
    out['cost_per_point'] = (out['cost_usd'] / out['score']) if out['score'] else None
    out['points_per_call'] = (out['collected'] / out['calls']) if out['calls'] else None
    out['collected_per_call'] = out['points_per_call']
    slack = [r['slack_s'] for r in rows if r['slack_s'] is not None]
    out['submitted_share'] = len(slack) / len(rows)
    if slack:
        out['slack_median_s'] = statistics.median(slack)
        out['share_slack_15'] = statistics.mean(1.0 if s < 15 else 0.0 for s in slack)
    return out


def cell_reliability(rows):
    """How a cell behaves across its repeats: an arm that swings from 0 to ceiling
    is a different claim from one that always lands in the middle."""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[(r['family'], r['arm'], r['model'], r['task_id'], r['regime'])].append(r['score'])
    out = collections.defaultdict(dict)
    multi = {k: v for k, v in groups.items() if len(v) > 1}
    for family in FAMILIES:
        for arm in ARMS:
            scores = [v for (f, a, *_), v in multi.items() if f == family and a == arm]
            if not scores:
                continue
            out[family][arm] = {
                'cells': len(scores),
                'worst_mean': statistics.mean(min(v) for v in scores),
                'sd_mean': statistics.mean(statistics.pstdev(v) for v in scores),
                'share_all_zero': statistics.mean(1.0 if max(v) == 0 else 0.0 for v in scores),
                'share_stable': statistics.mean(1.0 if len(set(v)) == 1 else 0.0 for v in scores),
            }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    batch = Path(args.batch).resolve()
    table = ceilings()
    rows = []
    skipped = 0
    for path in sorted((batch / 'episodes').glob('*.json')):
        row = json.loads(path.read_text())
        ceiling = table.get(row['manifest']['task_id'])
        if ceiling is None:
            continue
        if row['result'].get('termination_reason') == 'service_error':
            skipped += 1   # the harness never ran it; nothing was observed
            continue
        rows.append(episode_metrics(row, ceiling))
    summary = {family: {arm: summarise([r for r in rows if r['family'] == family and r['arm'] == arm])
                        for arm in ARMS} for family in FAMILIES}
    payload = {'n_episodes': len(rows), 'excluded_service_errors': skipped,
               'by_family_arm': summary,
               'reliability': cell_reliability(rows)}
    (batch / 'metrics_summary.json').write_text(json.dumps(payload, indent=2, sort_keys=True))
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f'{len(rows)} episodes ({skipped} service errors excluded)')
    for family in FAMILIES:
        print(f'\n{family}: score | ceiling | forfeited(share) | calls | +pts/100s | $/ep | $/pt')
        for arm in ARMS:
            s = summary[family][arm]
            if not s:
                continue
            print(f"  {arm:3s} {s['score']:6.2f} | {s['ceiling_share']:5.2f} | "
                  f"{s['forfeited']:6.2f} | {s['forfeited_share']:5.2f} | "
                  f"{s['calls']:4.2f} | {s['points_per_100s'] or 0:5.2f} | "
                  f"{s['cost_usd']:.5f} | {s['cost_per_point'] or 0:.5f}")
    print('\nreliability: worst repeat | sd | share all-zero | share stable')
    for family, arms in payload['reliability'].items():
        for arm, s in arms.items():
            print(f"  {family:7s} {arm:3s} {s['worst_mean']:5.2f} | {s['sd_mean']:4.2f} | "
                  f"{s['share_all_zero']:4.2f} | {s['share_stable']:4.2f}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

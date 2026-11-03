"""Where in the budget each arm chooses to start a call.

The informational arms are supposed to change *when* the agent spends time. This
script reads the decision itself off the episodes: the remaining budget at the
moment a fetch was admitted, per arm and per model, and the share of those calls
that could not finish given the model's own request latency.

    python -m scripts.study3_decisions runs/s3-A-... [--out decisions.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

ARMS = ('I0', 'I1', 'C', 'E', 'O')


def load(batch: Path):
    rows = []
    for path in sorted((batch / 'episodes').glob('*.json')):
        doc = json.loads(path.read_text())
        res = doc.get('result') or {}
        meta = res.get('metadata') or {}
        events = res.get('events') or []
        budget = res.get('budget_s') or meta.get('budget_s')
        if not meta or not budget:
            continue
        starts, requests = [], []
        for ev in events:
            if ev.get('event_type') == 'model_request' and ev.get('response_end_offset_s') is not None:
                requests.append(ev['response_end_offset_s'] - ev['request_start_offset_s'])
            elif ev.get('event_type') == 'tool' and ev.get('admitted') and ev.get('tool_name') == 'fetch':
                starts.append(budget - ev['tool_start_offset_s'])
        rows.append({
            'arm': meta['condition'], 'model': meta['model_id'], 'family': meta['task_family'],
            'regime': meta['regime'], 'budget': budget, 'starts': starts,
            'latency': requests, 'score': res.get('score', 0),
            'termination': res.get('termination_reason'),
            'commit': res.get('commit') if isinstance(res.get('commit'), (int, float)) else None,
        })
    return rows


def summarise(rows):
    by_model_lat = collections.defaultdict(list)
    for r in rows:
        by_model_lat[r['model']].extend(r['latency'])
    p90 = {m: (statistics.quantiles(v, n=10)[8] if len(v) >= 10 else (max(v) if v else 0.0))
           for m, v in by_model_lat.items()}

    out = {}
    for scope, keep in (('all', lambda r: True), ('hetero', lambda r: r['family'] == 'hetero')):
        cells = {}
        for arm in ARMS:
            sel = [r for r in rows if r['arm'] == arm and keep(r)]
            starts = [s for r in sel for s in r['starts']]
            risky = [s for r in sel for s in r['starts'] if s < p90.get(r['model'], 0.0)]
            tight = [s for r in sel for s in r['starts'] if s < 15.0]
            last_fetch = [r for r in sel if r['termination'] == 'timeout_model'
                          and r['starts'] and r['starts'][-1] < p90.get(r['model'], 0.0)]
            hist = collections.Counter(min(int(x // 15), 13) for x in starts)
            cells[arm] = {
                'n_episodes': len(sel),
                'histogram_15s': [hist.get(i, 0) for i in range(14)],
                'n_calls': len(starts),
                'calls_per_episode': round(len(starts) / len(sel), 2) if sel else None,
                'median_remaining_at_start_s': round(statistics.median(starts), 1) if starts else None,
                'share_started_below_15s': round(len(tight) / len(starts), 3) if starts else None,
                'share_started_below_own_p90': round(len(risky) / len(starts), 3) if starts else None,
                'deaths_on_a_call_too_slow_to_finish': len(last_fetch),
                'deaths_on_a_call_too_slow_to_finish_rate': (
                    round(len(last_fetch) / len(sel), 3) if sel else None),
            }
        out[scope] = cells
    out['request_p90_s'] = {m: round(v, 2) for m, v in p90.items()}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('batch')
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    batch = Path(args.batch).resolve()
    rows = load(batch)
    result = summarise(rows)
    out = Path(args.out) if args.out else batch / 'decisions.json'
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result['hetero'], indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

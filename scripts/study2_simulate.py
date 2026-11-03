"""Offline planner simulation for the S2 design (no API calls, no model output).

Purpose: show that the S2 environment has *decision leverage* — that the optimal
stopping rule depends on the latency estimate — and quantify how large the gap
between a static prior (B), an adaptive estimate (C) and a perfect oracle (O) is
for a rational planner. If this gap were zero, no interface change could matter
and the design would be uninformative by construction; that is exactly the
defect of the v4 task family, where the only scoring path was to collect every
required row.

Request latency r is resampled from the empirically observed per-model request
wall times of the completed S1 formal batch, so the simulated episode budget is
calibrated to the real service, not to an idealised number.
"""
import argparse
import collections
import glob
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
S1_BATCH = ROOT / 'runs' / 'go-formal-20261031T041031911245Z'


def empirical_request_times(batch=S1_BATCH):
    """Per-model request wall times observed in S1; empty list if unavailable."""
    out = collections.defaultdict(list)
    for path in glob.glob(str(Path(batch) / 'episodes' / '*.json')):
        row = json.loads(Path(path).read_text())
        model = row['manifest']['model_id']
        for event in row['result']['events']:
            if isinstance(event, dict) and event.get('event_type') == 'model_request' \
                    and 'response_end_offset_s' in event:
                out[model].append(event['response_end_offset_s'] - event['request_start_offset_s'])
    return {k: sorted(v) for k, v in out.items()}


def delay_at(profile, t, budget, fast, slow, shift):
    if profile == 'drift_up':
        return fast * (slow / fast) ** min(1.0, max(0.0, t / budget))
    shifted = t >= budget * shift
    if profile == 'stable_fast':
        return fast
    if profile == 'fast_to_slow':
        return slow if shifted else fast
    return fast if shifted else slow


def run(profile, belief, *, budget, shift, fast, slow, request_times, rng,
        window=1, items=20, margin=0.0):
    """Simulate one episode; every request draws a resampled wall time."""
    initial = slow if profile == 'slow_to_fast' else fast
    t, score, observed = 0.0, 0, []

    def req():
        return rng.choice(request_times)

    while True:
        r = req()
        if belief == 'B':
            estimate = initial
        elif belief == 'C':
            estimate = statistics.mean(observed[-window:]) if observed else initial
        elif belief == 'O':
            estimate = delay_at(profile, t + r, budget, fast, slow, shift)
        else:
            raise ValueError('unknown belief')
        if t + r > budget:
            return 0, 'timeout_on_request'
        if score >= items or t + r + estimate + r > budget - margin:
            return score, 'submitted'
        start = t + r
        d = delay_at(profile, start, budget, fast, slow, shift)
        if start + d >= budget:
            # Censored call: no submission ever happens, so the episode scores zero.
            return 0, 'timeout_tool'
        t = start + d
        observed.append(d)
        score += 1


def cell(profile, belief, *, budget, shift, fast, slow, request_times, n=2000, seed=7):
    rng = random.Random(seed)
    scores, terms = [], collections.Counter()
    for _ in range(n):
        s, term = run(profile, belief, budget=budget, shift=shift, fast=fast, slow=slow,
                      request_times=request_times, rng=rng)
        scores.append(s)
        terms[term] += 1
    no_submit = terms['timeout_tool'] + terms['timeout_on_request']
    return {'mean': statistics.mean(scores), 'no_submit_frac': no_submit / n}


def criterion_table(budget, shift, fast, slow, n=1500):
    """Simulated means for the design criterion, per model and belief."""
    times = empirical_request_times()
    rows = []
    for model in sorted(times):
        for profile in ('stable_fast', 'fast_to_slow', 'slow_to_fast'):
            for belief in ('B', 'C', 'O'):
                res = cell(profile, belief, budget=budget, shift=shift, fast=fast, slow=slow,
                           request_times=times[model], n=n)
                rows.append({'model': model, 'profile': profile, 'belief': belief,
                             'mean': round(res['mean'], 2),
                             'p_no_submit': round(res['no_submit_frac'], 2)})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--budget', type=float, default=200.0)
    parser.add_argument('--shift', type=float, default=0.30)
    parser.add_argument('--fast', type=float, default=8.0)
    parser.add_argument('--slow', type=float, default=45.0)
    parser.add_argument('--n', type=int, default=1500)
    parser.add_argument('--grid', action='store_true')
    args = parser.parse_args()
    if args.grid:
        times = empirical_request_times()
        models = sorted(times)
        print('slow budget shift | ' + ' | '.join(f'{m[:7]}:B,C,O' for m in models))
        for slow in (9.0, 12.0, 16.0):
            for budget in (90.0, 100.0, 110.0):
                for shift in (0.35, 0.45):
                    cells = []
                    for model in models:
                        vals = []
                        for belief in ('B', 'C', 'O'):
                            r = cell('fast_to_slow', belief, budget=budget, shift=shift,
                                     fast=args.fast, slow=slow, request_times=times[model], n=600)
                            vals.append(f"{r['mean']:.1f}")
                        cells.append(','.join(vals))
                    print(f'{slow:5.1f} {budget:6.1f} {shift:5.2f} | ' + ' | '.join(cells))
        return
    for row in criterion_table(args.budget, args.shift, args.fast, args.slow, args.n):
        print(f"{row['model']:20s} {row['profile']:13s} {row['belief']} "
              f"mean={row['mean']:5.2f} p_no_submit={row['p_no_submit']:.2f}")


if __name__ == '__main__':
    main()

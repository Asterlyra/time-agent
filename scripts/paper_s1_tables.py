"""Assemble the Study 1 numbers used in the manuscript from the frozen batch.

Read-only: the S1 formal batch and its episodes are never modified. Output is a
single JSON document plus a short markdown table, written under reports/paper_s1/.
"""
import argparse
import collections
import glob
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash')
CONDITIONS = ('A', 'B', 'C')
PROFILES = ('stable_fast', 'fast_to_slow', 'slow_to_fast')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', default=str(ROOT / 'runs' / 'go-formal-20261031T041031911245Z'))
    parser.add_argument('--out-dir', default=str(ROOT / 'reports' / 'paper_s1'))
    args = parser.parse_args()
    batch = Path(args.batch)
    rows = [json.loads(Path(p).read_text()) for p in sorted(glob.glob(str(batch / 'episodes' / '*.json')))]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = collections.OrderedDict()
    for model in MODELS:
        for profile in PROFILES:
            for condition in CONDITIONS:
                z = [r for r in rows if r['manifest']['model_id'] == model
                     and r['manifest']['profile'] == profile and r['manifest']['condition'] == condition]
                if not z:
                    continue
                results = [r['result'] for r in z]
                cells[f'{model}|{profile}|{condition}'] = {
                    'n': len(z),
                    'success': sum(1 for r in results if r['deadline_success']),
                    'termination': dict(collections.Counter(r['termination_reason'] for r in results)),
                    'mean_elapsed_s': round(statistics.mean(r['elapsed_s'] for r in results), 1),
                    'mean_remaining_at_end_s': round(statistics.mean(
                        r['budget_s'] - r['elapsed_s'] for r in results), 1),
                }

    requests = collections.defaultdict(list)
    for row in rows:
        for event in row['result']['events']:
            if isinstance(event, dict) and event.get('event_type') == 'model_request' \
                    and 'response_end_offset_s' in event:
                requests[row['manifest']['model_id']].append(
                    event['response_end_offset_s'] - event['request_start_offset_s'])
    latency = {}
    for model, values in requests.items():
        values.sort()
        n = len(values)
        latency[model] = {'n': n, 'median': round(values[n // 2], 2),
                          'p90': round(values[int(.9 * n)], 2),
                          'mean': round(statistics.mean(values), 2)}

    totals = {
        'episodes': len(rows),
        'success': sum(1 for r in rows if r['result']['deadline_success']),
        'termination': dict(collections.Counter(r['result']['termination_reason'] for r in rows)),
        'per_model_total': {m: {'n': sum(1 for r in rows if r['manifest']['model_id'] == m),
                                'success': sum(1 for r in rows if r['manifest']['model_id'] == m
                                               and r['result']['deadline_success'])}
                            for m in MODELS},
    }
    document = {'batch': str(batch), 'totals': totals, 'cells': cells, 'request_latency_s': latency}
    (out_dir / 's1_tables.json').write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')

    lines = ['# S1 formal batch summary\n',
             f"episodes {totals['episodes']}, success {totals['success']}\n",
             '| model | profile | cond | n | success | mean elapsed | mean remaining |',
             '|---|---|---|---:|---:|---:|---:|']
    for key, cell in cells.items():
        model, profile, condition = key.split('|')
        lines.append(f"| {model} | {profile} | {condition} | {cell['n']} | {cell['success']} | "
                     f"{cell['mean_elapsed_s']} | {cell['mean_remaining_at_end_s']} |")
    lines.append('\n## request wall time (s)\n')
    for model, value in latency.items():
        lines.append(f"- {model}: n={value['n']} median={value['median']} p90={value['p90']}")
    (out_dir / 's1_tables.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'totals': totals, 'latency': latency}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

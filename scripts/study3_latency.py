"""Per-model request latency and the size of the prize enforcement rescues.

Two quantities per model, both read straight from the episodes:

  * the distribution of the time the model itself takes between tool calls
    (end of one call to the start of the next), which is the cost the agent cannot
    observe directly;
  * among *unguarded* episodes (I0, I1) that die at the deadline, how many items
    the agent had already fetched. Those items are banked work that a submission
    would have turned into points, so their value is the upper bound on what
    enforcement can recover.

Read-only over a batch; writes ``latency_by_model.json`` beside the episodes.
"""
import argparse
import glob
import json
import statistics
from collections import defaultdict
from pathlib import Path

MODELS = ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash', 'mimo-v2.6-flash')
UNGUARDED = ('I0', 'I1')


def quantile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[int(p * (len(ordered) - 1))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--family', default='hetero')
    args = parser.parse_args()
    batch = Path(args.batch).resolve()

    gaps = defaultdict(list)
    arm_calls = defaultdict(list)
    arm_items = defaultdict(list)
    arm_requests = defaultdict(list)
    episodes = defaultdict(int)
    unguarded = defaultdict(int)
    killed = defaultdict(int)
    items_at_death = defaultdict(list)

    for path in glob.glob(str(batch / 'episodes' / '*.json')):
        record = json.loads(Path(path).read_text())
        result = record['result']
        meta = result['metadata']
        if meta['task_family'] != args.family:
            continue
        model = meta['model_id']
        episodes[model] += 1
        previous = 0.0
        calls = 0
        fetched = set()
        for event in result['events']:
            if event.get('event_type') == 'model_request':
                end, start_ = event.get('response_end_offset_s'), event.get('request_start_offset_s')
                if end is not None and start_ is not None and 0 <= end - start_ < 600:
                    arm_requests[meta['condition']].append(end - start_)
                continue
            if event.get('event_type') != 'tool':
                continue
            start = event.get('tool_start_offset_s')
            if start is not None:
                gap = start - previous
                if 0 < gap < 600:
                    gaps[model].append(gap)
            previous = event.get('tool_end_offset_s', start or previous)
            calls += 1
            if event.get('tool_result'):
                fetched.add(event['tool_result'].get('item_id'))
        arm_calls[meta['condition']].append(calls)
        arm_items[meta['condition']].append(len(fetched))
        if meta['condition'] in UNGUARDED:
            unguarded[model] += 1
            if result['termination_reason'].startswith('timeout_model'):
                killed[model] += 1
                items_at_death[model].append(len(fetched))

    arms = {}
    for arm, values in arm_calls.items():
        requests = arm_requests.get(arm, [])
        arms[arm] = {
            'episodes': len(values),
            'mean_calls': sum(values) / len(values),
            'mean_items_fetched': sum(arm_items[arm]) / len(arm_items[arm]),
            'requests': len(requests),
            'request_p50': quantile(requests, 0.50),
            'request_p90': quantile(requests, 0.90),
            'request_p99': quantile(requests, 0.99),
            'request_mean': (sum(requests) / len(requests)) if requests else None,
        }
    out = {'family': args.family, 'arms': arms, 'models': {}}
    for model in MODELS:
        values = gaps.get(model, [])
        out['models'][model] = {
            'episodes': episodes.get(model, 0),
            'requests': len(values),
            'p50': quantile(values, 0.50),
            'p90': quantile(values, 0.90),
            'p99': quantile(values, 0.99),
            'max': max(values) if values else None,
            'share_over_30s': (sum(1 for v in values if v > 30) / len(values)) if values else None,
            'unguarded_episodes': unguarded.get(model, 0),
            'unguarded_death_rate': (killed[model] / unguarded[model]) if unguarded.get(model) else None,
            'items_in_hand_at_death': (statistics.mean(items_at_death[model])
                                       if items_at_death.get(model) else None),
        }
    target = batch / 'latency_by_model.json'
    target.write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()

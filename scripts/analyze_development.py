"""Descriptive diagnostics only, including exposure to changed tool latency."""
import argparse
import collections
import json
from pathlib import Path


def summarize(path):
    path = Path(path)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    cells = collections.defaultdict(lambda: {'n': 0, 'success': 0, 'terminations': collections.Counter(),
                                                'shift_observed': 0, 'post_shift_decision': 0})
    total = 0
    for entry in manifest:
        file = path / 'episodes' / (entry['run_id'] + '.json')
        if not file.exists(): continue
        data = json.loads(file.read_text(encoding='utf-8'))
        if data['manifest'] != entry: raise ValueError('manifest mismatch')
        r = data['result']
        group = cells[(entry['profile'], entry['condition'], entry['task_family'])]
        group['n'] += 1
        group['success'] += int(r['deadline_success'])
        group['terminations'][r['termination_reason']] += 1
        shifted = [e for e in r['events'] if e['event_type'] == 'tool' and not e.get('is_censored')
                   and 'observed_duration_s' in e and e['tool_start_offset_s'] >= r['budget_s'] * r['shift_fraction']]
        if entry['profile'] != 'stable_fast' and shifted:
            group['shift_observed'] += 1
            if any(e['event_type'] == 'model_request' and e['request_start_offset_s'] >= shifted[0]['tool_end_offset_s']
                   for e in r['events']):
                group['post_shift_decision'] += 1
        total += 1
    groups = [{'profile': p, 'condition': c, 'family': f, **v, 'terminations': dict(v['terminations'])}
              for (p, c, f), v in sorted(cells.items())]
    return {'purpose': 'exploratory development only; incomplete batches are not valid comparisons',
            'planned': len(manifest), 'completed': total, 'uncompleted': len(manifest)-total, 'groups': groups}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('batch')
    args = parser.parse_args()
    print(json.dumps(summarize(args.batch), ensure_ascii=False, indent=2))

"""Move credential (HTTP 401) episodes out of the S3 matrix so they can be re-run.

A 401 means the harness never reached the model: `call_count` is absent, the
episode lasts ~1.5 s and the only event carries status_codes == [401].  Such a
row is not an observation of agent behaviour, so it must not be scored as a
zero.  Episodes are moved byte-identically (together with their `started/`
marker, so the driver treats them as never having run) and listed in
`invalid_service_auth/MANIFEST.json`.

Service errors that carried a real HTTP 200 response are left in place: those
are genuine model failures and stay in the matrix as score-0 rows.

Not part of the frozen code set: it only moves files.
"""
import argparse
import json
from pathlib import Path


def status_codes(result):
    codes = set()
    for event in result.get('events', []):
        for attempt in event.get('attempts', []):
            codes.update((attempt.get('adapter_diagnostics') or {}).get('status_codes') or [])
    return codes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--apply', action='store_true', help='move files (default: dry run)')
    parser.add_argument('--sync-journals', action='store_true',
                        help='move journals of episodes quarantined by an earlier run')
    args = parser.parse_args()
    batch = Path(args.batch).resolve()
    manifest = json.loads((batch / 'manifest.json').read_text())
    dest = batch / 'invalid_service_auth'
    if args.sync_journals:
        print(json.dumps({'journals_moved': sync_journals(batch, dest)}, ensure_ascii=False))
        return
    moved = []
    for entry in manifest:
        path = batch / 'episodes' / (entry['run_id'] + '.json')
        if not path.exists():
            continue
        row = json.loads(path.read_text())
        result = row['result']
        if result.get('termination_reason') != 'service_error':
            continue
        codes = status_codes(result)
        if 401 not in codes:
            continue
        moved.append({'run_id': entry['run_id'], 'model': entry['model_id'],
                      'task': entry['task_id'], 'regime': entry['regime'],
                      'condition': entry['condition'], 'status_codes': sorted(codes),
                      'elapsed_s': result.get('elapsed_s'),
                      'end_utc': result.get('end_utc'),
                      'call_count': result.get('call_count')})
    print(json.dumps({'candidates': len(moved), 'apply': args.apply}, ensure_ascii=False))
    if not moved or not args.apply:
        return
    (dest / 'episodes').mkdir(parents=True, exist_ok=True)
    (dest / 'started').mkdir(parents=True, exist_ok=True)
    (dest / 'journals').mkdir(parents=True, exist_ok=True)
    for item in moved:
        run_id = item['run_id']
        episode = batch / 'episodes' / (run_id + '.json')
        marker = batch / 'started' / (run_id + '.json')
        target = dest / 'episodes' / (run_id + '.json')
        if target.exists():
            raise ValueError('already quarantined: ' + run_id)
        episode.replace(target)
        if marker.exists():
            marker.replace(dest / 'started' / (run_id + '.json'))
        journal = batch / 'journals' / (run_id + '.jsonl')
        if journal.exists():
            journal.replace(dest / 'journals' / (run_id + '.jsonl'))
    record = {'reason': 'HTTP 401 invalid credential; the model was never reached',
              'policy': 'excluded from the matrix as non-observations and scheduled for rerun; '
                        'started markers and journals moved with the episodes so the driver '
                        'treats them as unstarted',
              'moved': moved}
    (dest / 'MANIFEST.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'moved': len(moved), 'manifest': str(dest / 'MANIFEST.json')}, ensure_ascii=False))


def sync_journals(batch, dest):
    """Move journals left behind by episodes quarantined before this flag existed."""
    record = json.loads((dest / 'MANIFEST.json').read_text())
    (dest / 'journals').mkdir(parents=True, exist_ok=True)
    moved = 0
    for item in record['moved']:
        journal = batch / 'journals' / (item['run_id'] + '.jsonl')
        if journal.exists():
            journal.replace(dest / 'journals' / journal.name)
            moved += 1
    return moved


if __name__ == '__main__':
    main()

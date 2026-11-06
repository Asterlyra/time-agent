"""Finish episodes that never started, in a derived top-up batch.

The main S3 batch ran out of plan allowance: from that moment every request was
billed to the account balance, and the adapter refused it by policy, so the
episodes that had not yet started were never attempted (and thousands that did
start were refused).  Those episodes contain no behaviour at all.

This module re-runs *only the never-started entries* under a derived batch with
its own frozen manifest, then moves the resulting episodes into the main batch
so that one canonical directory holds every observation.  Nothing is rewritten
in place: the main batch keeps its original config and manifest as provenance.

Usage:
  python -m scripts.study3_topup runs/s3-A-... --dry-run
  TIME_AGENT_ALLOW_PAID_BILLING=1 python -m scripts.study3_topup runs/s3-A-... --run
"""
import argparse
import asyncio
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

from scripts import study3
from scripts.matrix import code_hash, digest, write_new

ROOT = Path(__file__).resolve().parent.parent


def never_started(batch, manifest):
    out = []
    for entry in manifest:
        rid = entry['run_id']
        if (batch / 'episodes' / (rid + '.json')).exists():
            continue
        if (batch / 'started' / (rid + '.json')).exists():
            continue
        out.append(entry)
    return out


def build(main, entries):
    config = json.loads((main / 'config.json').read_text())
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    top = ROOT / 'runs' / ('s3-T-' + stamp)
    top.mkdir(parents=True, exist_ok=False)
    config = dict(config)
    config['manifest_hash'] = digest(entries)
    config['code_hash'] = code_hash(study3.CODE_PATHS)
    config['derived_from'] = main.name
    config['derived_reason'] = (
        'top-up of manifest entries that never started: the account moved to balance '
        'billing mid-batch and the frozen adapter refused paid requests by policy')
    config['topup'] = {'n_entries': len(entries),
                       'policy': 'identical episode code and policies; only the billing '
                                 'acceptance flag differs (TIME_AGENT_ALLOW_PAID_BILLING=1)'}
    write_new(top / 'config.json', config)
    write_new(top / 'config_hash.json', {'sha256': digest(config)})
    write_new(top / 'manifest.json', entries)
    return top


def merge(top, main, entries):
    moved, failed = 0, 0
    for entry in entries:
        rid = entry['run_id']
        src = top / 'episodes' / (rid + '.json')
        if not src.exists():
            failed += 1
            continue
        target = main / 'episodes' / (rid + '.json')
        if target.exists():
            raise ValueError(f'refusing to overwrite {target}')
        shutil.move(str(src), str(target))
        journal = top / 'journals' / (rid + '.jsonl')
        if journal.exists():
            shutil.move(str(journal), str(main / 'journals' / (rid + '.jsonl')))
        marker = top / 'started' / (rid + '.json')
        if marker.exists():
            shutil.move(str(marker), str(main / 'started' / (rid + '.json')))
        moved += 1
    return moved, failed


def summarize(main, entries):
    import collections
    reasons = collections.Counter()
    for entry in entries:
        path = main / 'episodes' / (entry['run_id'] + '.json')
        if path.exists():
            reasons[json.loads(path.read_text())['result']['termination_reason']] += 1
        else:
            reasons['no_result'] += 1
    return dict(reasons)


def main_entry(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('batch')
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--run', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args(argv)

    main = Path(args.batch).resolve()
    manifest = json.loads((main / 'manifest.json').read_text())
    entries = never_started(main, manifest)
    if args.limit:
        entries = entries[:args.limit]
    print(f'never started: {len(entries)} of {len(manifest)}', flush=True)
    if args.dry_run:
        import collections
        print('by arm:', dict(sorted(collections.Counter(e['condition'] for e in entries).items())))
        print('by model:', dict(sorted(collections.Counter(e['model_id'] for e in entries).items())))
        return 0
    if not entries:
        print('nothing to do')
        return 0

    top = build(main, entries)
    print(f'derived batch: {top.name}', flush=True)
    os.environ['TIME_AGENT_ALLOW_PAID_BILLING'] = '1'
    try:
        asyncio.run(study3.execute(top))
    finally:
        lock = top / 'run_lock.json'
        if lock.exists():
            lock.unlink()
    moved, failed = merge(top, main, entries)
    print(f'merged {moved} episodes into {main.name} ({failed} without result)', flush=True)
    print('terminations:', summarize(main, entries), flush=True)
    note = ('Top-up run. Episodes were executed in this derived batch under the same code '
            'except for a billing-acceptance flag, then moved into the parent batch.\n')
    (top / 'TOPUP.md').write_text(note)
    return 0


if __name__ == '__main__':
    sys.exit(main_entry())

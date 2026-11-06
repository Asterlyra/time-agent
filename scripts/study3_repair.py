"""Retire abandoned `started` markers so their episodes can run again.

A run that is killed between writing `started/<run_id>.json` and writing
`episodes/<run_id>.json` leaves a marker with no result. The frozen driver never
revisits such an entry (scripts/study3.py:276), and `analyze()` counts it as a
zero-score `environment_interruption` row. That is the right reading for a host
suspend, which is why those are archived, but a marker left by a clean restart of
the supervisor is not an observation at all: the model was never asked anything.

This script moves markers that are old enough to be certainly abandoned out of
`started/` (with their journal, which would otherwise collide on re-run), so the
next `study3_continue` pass schedules those episodes again.

Not part of the frozen code set.
"""
import argparse
import collections
import datetime
import json
import shutil
from pathlib import Path


def stale_orphans(batch, min_age_s):
    episodes = {p.stem for p in (batch / 'episodes').glob('*.json')}
    now = datetime.datetime.now().timestamp()
    out = []
    for marker in (batch / 'started').glob('*.json'):
        if marker.stem in episodes:
            continue
        age = now - marker.stat().st_mtime
        if age >= min_age_s:
            out.append((marker, age, json.loads(marker.read_text())))
    out.sort(key=lambda row: row[0].stat().st_mtime)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--min-age-s', type=int, default=1800,
                        help='only retire markers older than this (default 1800)')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    batch = Path(args.batch).resolve()
    rows = stale_orphans(batch, args.min_age_s)
    print(f'{len(rows)} abandoned marker(s) older than {args.min_age_s}s')
    if not rows:
        return 0

    by_hour = collections.Counter(
        datetime.datetime.fromtimestamp(m.stat().st_mtime).strftime('%m-%d %H')
        for m, _, _ in rows)
    by_arm = collections.Counter(d['condition'] for _, _, d in rows)
    for hour, count in sorted(by_hour.items()):
        print(f'  {hour}: {count}')
    print('  arms:', dict(sorted(by_arm.items())))
    for marker, age, _ in rows[:5]:
        print(f'  e.g. {marker.name} age={age / 3600:.1f}h')
    if len(rows) > 5:
        print(f'  ... and {len(rows) - 5} more')

    if not args.apply:
        print('dry run; pass --apply to move them aside')
        return 0

    retired = batch / 'retired_started'
    retired_journals = batch / 'retired_journals'
    retired.mkdir(exist_ok=True)
    retired_journals.mkdir(exist_ok=True)
    moved_markers = moved_journals = 0
    for marker, _, _ in rows:
        shutil.move(str(marker), str(retired / marker.name))
        moved_markers += 1
        journal = batch / 'journals' / (marker.stem + '.jsonl')
        if journal.exists():
            shutil.move(str(journal), str(retired_journals / journal.name))
            moved_journals += 1
    print(f'moved {moved_markers} marker(s) and {moved_journals} journal(s)')
    print('next: .venv/bin/python -m scripts.study3_continue ' + str(batch))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

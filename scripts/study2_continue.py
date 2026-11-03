"""Continue a frozen S2 batch after a host suspend.

Not part of the frozen code set: it only schedules. Before touching anything it
verifies every frozen source file against the byte hashes archived at freeze time,
so the episode-executing code is guaranteed identical to the registered snapshot.
Episodes that ended because the host suspended are moved, byte-identical, into
`environment_failures/` and remain accounted for by `analyze()` as score-0
environment failures (their `started/` markers are kept).
"""
import argparse
import hashlib
import json
from pathlib import Path

from scripts import study2

ROOT = Path(__file__).resolve().parent.parent


def verify_snapshot(batch):
    archived = json.loads((batch / 'source_snapshot_hashes.json').read_text())
    for relative, expected in archived.items():
        path = batch / 'source_snapshot' / relative
        if not path.exists():
            raise ValueError('archived snapshot is incomplete: ' + relative)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('archived snapshot changed: ' + relative)
        current = ROOT / relative
        if not current.exists() or hashlib.sha256(current.read_bytes()).hexdigest() != expected:
            raise ValueError('working source differs from the frozen snapshot: ' + relative)
    return len(archived)


def archive_failures(batch):
    dest = batch / 'environment_failures'
    dest.mkdir(exist_ok=True)
    manifest_path = dest / 'MANIFEST.json'
    record = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'reason': 'host suspend; the runner clock detected a continuous-vs-monotonic gap',
        'policy': 'records are preserved byte-identical here and are re-accounted by analyze() '
                  'as score-0 environment failures',
        'moved': []}
    moved = []
    for path in sorted((batch / 'episodes').glob('*.json')):
        row = json.loads(path.read_text())
        if row['result']['termination_reason'] == 'environment_interruption':
            target = dest / path.name
            if target.exists():
                raise ValueError('duplicate archived failure: ' + path.name)
            path.replace(target)
            moved.append({'run_id': path.stem, 'model': row['manifest']['model_id'],
                          'task': row['manifest']['task_id'],
                          'profile': row['manifest']['profile'],
                          'condition': row['manifest']['condition'],
                          'elapsed_s': row['result']['elapsed_s'],
                          'suspend_gap_s': row['result'].get('suspend_gap_s')})
    if moved:
        record['moved'].extend(moved)
        manifest_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    return moved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    args = parser.parse_args()
    batch = Path(args.batch).resolve()
    checked = verify_snapshot(batch)
    moved = archive_failures(batch)
    print(json.dumps({'verified_snapshot_files': checked, 'archived_now': len(moved),
                      'episodes': len(list((batch / 'episodes').glob('*.json')))}, ensure_ascii=False))
    report = study2.analyze(batch)
    print(json.dumps({k: v for k, v in report.items() if k != 'cells'}, ensure_ascii=False))
    if not report['missing']:
        print('nothing left to run')
        return
    import asyncio
    asyncio.run(study2.execute(batch, resume=True))


if __name__ == '__main__':
    main()

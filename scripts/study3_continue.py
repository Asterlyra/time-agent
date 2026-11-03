"""Continue a frozen S3 batch after a host suspend or a crash.

Not part of the frozen code set: it only schedules. It verifies every frozen
source file against the bytes archived at freeze time, clears a stale run lock
left by a killed process, moves host-suspend results into environment_failures/
byte-identically, and then resumes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from scripts import study3

ROOT = Path(__file__).resolve().parent.parent


def verify_snapshot(batch):
    archived = json.loads((batch / 'source_snapshot_hashes.json').read_text())
    for relative, expected in archived.items():
        copy = batch / 'source_snapshot' / relative
        current = ROOT / relative
        if not copy.exists() or hashlib.sha256(copy.read_bytes()).hexdigest() != expected:
            raise ValueError('archived snapshot changed: ' + relative)
        if not current.exists() or hashlib.sha256(current.read_bytes()).hexdigest() != expected:
            raise ValueError('working source differs from the frozen snapshot: ' + relative)
    return len(archived)


def clear_stale_lock(batch):
    lock = batch / 'run_lock.json'
    if not lock.exists():
        return None
    try:
        pid = json.loads(lock.read_text()).get('pid')
    except (ValueError, OSError):
        pid = None
    alive = False
    if isinstance(pid, int):
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            alive = False
    if alive:
        raise ValueError('run lock is held by a live process')
    lock.unlink()
    return pid


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
        if row['result'].get('termination_reason') != 'environment_interruption':
            continue
        entry = row['manifest']
        target = dest / path.name
        if target.exists():
            raise ValueError('duplicate archived failure: ' + path.name)
        path.replace(target)
        moved.append({'run_id': path.stem, 'model': entry.get('model_id'),
                      'task': entry.get('task_id'), 'regime': entry.get('regime'),
                      'condition': entry.get('condition'),
                      'elapsed_s': row['result'].get('elapsed_s'),
                      'suspend_gap_s': row['result'].get('suspend_gap_s')})
    if moved:
        record['moved'].extend(moved)
        manifest_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    return moved


def preflight_auth():
    """Fail before the first episode if the credential is dead.

    A revoked key makes every episode die in ~1.5 s with a 401, and the frozen
    runner records that as a score-0 `service_error` row.  A hundred and four of
    those landed in the matrix on 2026-11-03 before anyone noticed, so the
    scheduler now checks the credential and refuses to start.
    """
    import httpx
    from src.adapters.opencode_go import BASE_URL, load_api_key
    try:
        response = httpx.get(BASE_URL + '/v1/models',
                             headers={'Authorization': 'Bearer ' + load_api_key()},
                             timeout=20)
    except Exception as exc:  # a network outage is not an auth verdict
        return {'ok': True, 'note': 'auth probe skipped: ' + type(exc).__name__}
    if response.status_code in (401, 403):
        return {'ok': False, 'status': response.status_code, 'body': response.text[:200]}
    return {'ok': True, 'status': response.status_code}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    args = parser.parse_args()
    batch = Path(args.batch).resolve()
    checked = verify_snapshot(batch)
    auth = preflight_auth()
    if not auth['ok']:
        (batch / 'AUTH_FAILED.json').write_text(json.dumps(
            {'status': auth['status'], 'body': auth['body'],
             'advice': 'rotate OPENCODE_GO_API_KEY in .env, then restart the supervisor'},
            ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'auth': 'failed', 'status': auth['status'],
                          'body': auth['body']}, ensure_ascii=False), flush=True)
        return 2
    (batch / 'AUTH_FAILED.json').unlink(missing_ok=True)
    stale = clear_stale_lock(batch)
    moved = archive_failures(batch)
    print(json.dumps({'verified': checked, 'stale_lock_pid': stale, 'archived_now': len(moved),
                      'episodes': len(list((batch / 'episodes').glob('*.json')))}, ensure_ascii=False))
    report = study3.analyze(batch)
    print(json.dumps({k: v for k, v in report.items() if k != 'cells'}, ensure_ascii=False))
    if not report['missing']:
        print('nothing left to run')
        return
    import asyncio
    asyncio.run(study3.execute(batch, resume=True))


if __name__ == '__main__':
    main()

"""Keep the S3 supervisor alive across an unattended run.

The supervisor itself already refuses to spin: it exits after three restarts that
produce no new episode, and after an authentication preflight fails. What it cannot
do is come back after the machine, the network, or a stray signal removes it. This
watchdog watches only for that case.

It deliberately does *not* restart when:

  * `STOP_SUPERVISOR` exists  -- the supervisor stopped itself because it could not
    make progress; restarting would recreate the loop it just escaped;
  * `AUTH_FAILED.json` exists -- the credential is dead and every episode written
    would be a zero-score artefact;
  * the batch is complete     -- there is nothing left to restart.

Killing this process is how a human stops the batch for the night.
"""
import json
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

BATCH = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                     'runs/s3-A-20261102T094306204655Z').resolve()
INTERVAL = int(sys.argv[2]) if len(sys.argv) > 2 else 600
MISSES_BEFORE_RESTART = 2
MAX_RESTARTS = 20


def log(message):
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    print(f'[{stamp}] {message}', flush=True)


def episodes():
    return len(list((BATCH / 'episodes').glob('*.json')))


def planned():
    return len(json.loads((BATCH / 'manifest.json').read_text()))


def supervisor_running():
    # Match on the directory name only: the supervisor may have been started with
    # either a relative or an absolute path.
    probe = subprocess.run(['pgrep', '-f', f'scripts/supervise.py.*{BATCH.name}'],
                           capture_output=True, text=True)
    return probe.returncode == 0


def start_supervisor():
    for name in ('run_lock.json',):
        (BATCH / name).unlink(missing_ok=True)
    handle = open('/tmp/s3formal_watch.log', 'a')
    subprocess.Popen(
        ['.venv/bin/python', 'scripts/supervise.py', str(BATCH),
         '--module', 'scripts.study3', '--continue-module', 'scripts.study3_continue',
         '--max-restarts', '80'],
        stdout=handle, stderr=handle, start_new_session=True)


def assemble_paper():
    """Once the matrix is complete, build the final manuscript without a human present."""
    marker = BATCH / 'AUTO_ASSEMBLED'
    if marker.exists():
        return
    log('batch complete; assembling the final manuscript')
    handle = open('/tmp/s3_auto_assemble.log', 'a')
    proc = subprocess.run(['.venv/bin/python', '-m', 'scripts.assemble_paper_s3', str(BATCH)],
                          stdout=handle, stderr=handle, timeout=3600)
    log(f'assembly finished with code {proc.returncode}')
    if proc.returncode == 0:
        marker.write_text('assembled by watch_supervisor')


def main():
    once = '--once' in sys.argv
    if once:
        done, total = episodes(), planned()
        for marker, reason in (('STOP_SUPERVISOR', 'supervisor stopped itself'),
                               ('AUTH_FAILED.json', 'credential rejected')):
            if (BATCH / marker).exists():
                log(f'{reason} ({marker}); nothing to do')
                return 2
        if done >= total:
            assemble_paper()
            return 0
        if not supervisor_running():
            log(f'supervisor absent ({done}/{total}); restarting')
            start_supervisor()
        return 0
    log(f'watchdog start: {BATCH} every {INTERVAL}s')
    misses = 0
    restarts = 0
    while True:
        done, total = episodes(), planned()
        if done >= total:
            log(f'batch complete at {done}/{total}; watchdog exiting')
            return 0
        for marker, reason in (('STOP_SUPERVISOR', 'supervisor stopped itself'),
                               ('AUTH_FAILED.json', 'credential rejected')):
            if (BATCH / marker).exists():
                log(f'{reason} ({marker}); watchdog exiting for a human to look')
                return 2
        if supervisor_running():
            misses = 0
        else:
            misses += 1
            log(f'supervisor absent ({done}/{total}), miss {misses}/{MISSES_BEFORE_RESTART}')
            if misses >= MISSES_BEFORE_RESTART:
                if restarts >= MAX_RESTARTS:
                    log('restart budget exhausted; exiting')
                    return 3
                start_supervisor()
                restarts += 1
                misses = 0
                log(f'restarted supervisor (restart {restarts}/{MAX_RESTARTS})')
        time.sleep(INTERVAL)


if __name__ == '__main__':
    sys.exit(main())

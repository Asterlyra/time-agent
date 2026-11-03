"""Keep a long batch awake and restart it after host suspend or crash.

Two mechanisms, both unprivileged (the machine's `sleep` timer is 1 minute and
the assertions held by unrelated apps can disappear at any time):

1. the batch itself runs under `caffeinate -dims -u`, which holds display, idle,
   disk and system assertions for exactly as long as the child process lives;
2. a pinger calls `caffeinate -u -t 2` every 60 s, which resets the user-activity
   timer even if some other component drops its assertion.

On every child exit the supervisor asks the batch how much is left, verifies the
frozen sources against the archived snapshot, archives host-suspend failures,
and restarts. It never silently reruns a started episode.

This wrapper only schedules. It changes nothing about how an episode is run, so
it cannot affect the measurements.
"""
import argparse
import datetime
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def log(path, message):
    stamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    line = f'[{stamp}] {message}'
    print(line, flush=True)
    if path:
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')


class Pinger(threading.Thread):
    """Reset the user-activity timer so the 1-minute idle sleep never fires."""

    def __init__(self, interval=60):
        super().__init__(daemon=True)
        self.interval = interval
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            subprocess.run(['/usr/bin/caffeinate', '-u', '-t', '2'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.stop_event.wait(self.interval)

    def stop(self):
        self.stop_event.set()


def assertions():
    try:
        out = subprocess.run(['/usr/bin/pmset', '-g', 'assertions'], capture_output=True, text=True).stdout
    except OSError:
        return None
    keep = [line.strip() for line in out.splitlines()
            if 'PreventUserIdleSystemSleep' in line or 'PreventSystemSleep' in line
            or 'user' in line.lower()]
    return keep[:12]


def count_episodes(batch):
    return len(list((batch / 'episodes').glob('*.json')))


def run_once(batch, module, continue_module, timeout_hours):
    # The continuation module clears a stale lock, archives host-suspend results and
    # then resumes; calling it directly makes every restart self-healing.
    command = ['/usr/bin/caffeinate', '-dims', '-u',
               sys.executable, '-m', continue_module, str(batch)]
    started = time.time()
    child = subprocess.Popen(command, cwd=str(ROOT))
    while child.poll() is None:
        if time.time() - started > timeout_hours * 3600:
            child.terminate()
            return 'timeout'
        time.sleep(5)
    return f'exit={child.returncode}'


def continue_once(batch, continue_module):
    command = [sys.executable, '-m', continue_module, str(batch)]
    done = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True)
    return done.returncode, (done.stdout or '')[-400:], (done.stderr or '')[-400:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    parser.add_argument('--module', default='scripts.study2')
    parser.add_argument('--continue-module', default='scripts.study2_continue')
    parser.add_argument('--max-restarts', type=int, default=40)
    parser.add_argument('--episode-timeout-hours', type=float, default=8.0)
    parser.add_argument('--stop-file', default='STOP_SUPERVISOR')
    args = parser.parse_args()
    batch = Path(args.batch).resolve()
    logfile = batch / 'supervisor.log'
    log(logfile, f'supervisor start: disk sleep={shutil.which("caffeinate") is not None}')
    for line in assertions() or []:
        log(logfile, 'assertion: ' + line)
    pinger = Pinger()
    pinger.start()
    stalled = 0
    previous = -1
    try:
        for attempt in range(1, args.max_restarts + 1):
            if (batch / args.stop_file).exists():
                log(logfile, 'stop file present; exiting')
                return 0
            if (batch / 'AUTH_FAILED.json').exists():
                log(logfile, 'credential rejected; exiting (see AUTH_FAILED.json)')
                return 2
            manifest = json.loads((batch / 'manifest.json').read_text())
            have = count_episodes(batch)
            if have >= len(manifest):
                log(logfile, f'complete: {have}/{len(manifest)}')
                return 0
            if have == previous:
                stalled += 1
            else:
                stalled = 0
            previous = have
            if stalled >= 3:
                log(logfile, f'no progress in {stalled} restarts at {have}/{len(manifest)}; '
                             f'writing {args.stop_file} and exiting')
                (batch / args.stop_file).write_text('supervisor stopped after three restarts '
                                                    'with no new episodes\n')
                return 2
            log(logfile, f'attempt {attempt}: {have}/{len(manifest)} episodes on disk')
            result = run_once(batch, args.module, args.continue_module, args.episode_timeout_hours)
            have = count_episodes(batch)
            log(logfile, f'child {result}; {have} episodes on disk')
            if have >= len(manifest):
                log(logfile, f'complete: {have}/{len(manifest)}')
                return 0
            time.sleep(5)
        log(logfile, 'max restarts reached')
        return 1
    finally:
        pinger.stop()
        log(logfile, 'supervisor stop')


if __name__ == '__main__':
    raise SystemExit(main())

"""Frozen, balanced episode manifest and crash-safe run bookkeeping.

This module intentionally requires a caller-provided episode coroutine. It does
not assert model isolation or authorize a formal study on its own.
"""
import asyncio
import hashlib
import itertools
import json
import os
import random
from pathlib import Path


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def code_hash(paths):
    return digest({str(Path(p).as_posix()): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(map(str, paths))})


def build_manifest(tasks, models, profiles=('stable_fast', 'fast_to_slow', 'slow_to_fast'), repeats=2, seed=4125):
    if not tasks or not models or repeats < 1:
        raise ValueError('tasks, models and positive repeats required')
    keys = [(m, t, p, r) for m in models for t in tasks for p in profiles for r in range(repeats)]
    if len({(m, t['task_id'], p, r) for m,t,p,r in keys}) != len(keys):
        raise ValueError('duplicate model/task/profile/repeat')
    rng = random.Random(seed)
    rng.shuffle(keys)
    # Across each set of six blocks, all condition orders occur once.
    perms = list(itertools.permutations('ABC'))
    result = []
    for i, (model, task, profile, repeat) in enumerate(keys):
        if i % len(perms) == 0:
            rng.shuffle(perms)
        for condition in perms[i % len(perms)]:
            entry = {'model_id': model, 'task_id': task['task_id'], 'task_family': task['task_family'],
                     'template_id': task['template_id'], 'data_seed': task['data_seed'],
                     'profile': profile, 'repeat': repeat, 'condition': condition}
            entry['run_id'] = digest(entry)[:24]
            result.append(entry)
    return result


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


class EpisodeJournal:
    """Append-only JSONL checkpoint. The callback must emit every visible event.

    Entries are flushed and fsynced individually. A crash can leave a partial
    final line; earlier complete lines remain readable and must not be overwritten.
    Do not send secrets or private reasoning to emit().
    """
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open('x', encoding='utf-8', newline='\n')

    def emit(self, event):
        line = canonical(event).decode('utf-8') + '\n'
        self._file.write(line)
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self):
        self._file.close()


def freeze(directory, config, tasks, code_paths):
    """Create one immutable-by-convention configuration; refuses existing folder.

    config must include protocol, prompt, model settings, per-tool calibration,
    delays, seed and analysis plan. Sensitive values must never be passed here.
    """
    for name in ('models', 'profiles', 'repeats', 'manifest_seed', 'protocol', 'model_settings',
                 'calibration', 'timing', 'analysis', 'prompt', 'isolation_evidence'):
        if name not in config:
            raise ValueError('missing frozen field: ' + name)
    if not config['isolation_evidence']:
        raise ValueError('verified isolation evidence is required')
    manifest = build_manifest(tasks, config['models'], config['profiles'], config['repeats'], config['manifest_seed'])
    frozen = {'config': config, 'task_hash': digest(tasks), 'code_hash': code_hash(code_paths),
              'manifest_hash': digest(manifest)}
    frozen['config_hash'] = digest(frozen)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_new(directory / 'frozen_config.json', frozen)
    write_new(directory / 'manifest.json', manifest)
    return frozen, manifest


def verify_frozen(directory, tasks, code_paths):
    directory = Path(directory)
    frozen = json.loads((directory / 'frozen_config.json').read_text(encoding='utf-8'))
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    base = {k: v for k, v in frozen.items() if k != 'config_hash'}
    if (digest(base) != frozen['config_hash'] or digest(manifest) != frozen['manifest_hash']
        or digest(tasks) != frozen['task_hash'] or code_hash(code_paths) != frozen['code_hash']):
        raise ValueError('frozen config, manifest, task or code has changed')
    return frozen, manifest


async def execute_pending(directory, run_episode, *, tasks, code_paths,
                          stop_on=('service_error', 'protocol_violation')):
    """Execute never-started manifest entries serially. Previously started entries
    without result are reported as interrupted, never silently rerun or overwritten.
    Hashes are verified before execution. Caller provides async function(entry,
    journal) -> result and MUST emit each model/tool event as it occurs. Creating
    a journal cannot capture events that the caller does not emit.
    """
    directory = Path(directory)
    _, manifest = verify_frozen(directory, tasks, code_paths)
    interrupted = []
    for entry in manifest:
        start = directory / 'started' / (entry['run_id'] + '.json')
        result_path = directory / 'episodes' / (entry['run_id'] + '.json')
        if result_path.exists():
            continue
        if start.exists():
            interrupted.append(entry['run_id'])
            continue
        write_new(start, entry)
        journal = EpisodeJournal(directory / 'journals' / (entry['run_id'] + '.jsonl'))
        try:
            journal.emit({'event_type': 'episode_started', 'manifest': entry})
            try:
                result = await run_episode(entry, journal)
            except BaseException as exc:
                journal.emit({'event_type': 'episode_interrupted', 'exception_type': type(exc).__name__})
                raise
            journal.emit({'event_type': 'episode_completed', 'result': result})
            write_new(result_path, {'manifest': entry, 'result': result})
        finally:
            journal.close()
        if result.get('termination_reason') in stop_on:
            break
    return interrupted

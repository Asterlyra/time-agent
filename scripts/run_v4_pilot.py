"""Bounded exploratory v4 pilot; not a formal experiment or isolation proof.

Runs one development instance per family with fast_to_slow and A/B/C, serially.
Started episodes are never overwritten or resumed. No test task is generated.
"""
import asyncio
import argparse
import datetime
import hashlib
import json
from pathlib import Path

from tasks import data_v4
from src.runner_v2 import run_episode
from src.calibration import calibrate
from src.adapters.codex_mxc_v2 import CodexMXCV2
from scripts.matrix import build_manifest, code_hash, digest, write_new, EpisodeJournal

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ('fast_to_slow',)
NAMES = ('search', 'read_document', 'lookup_rows', 'calculate')
CODE_PATHS = tuple(ROOT / x for x in (
    'tasks/data.py', 'tasks/data_v2.py', 'tasks/data_v3.py', 'tasks/data_v4.py', 'src/runner_v2.py',
    'src/conditions.py', 'src/protocol.py', 'src/calibration.py',
    'src/adapters/codex_mxc.py', 'src/adapters/codex_mxc_v2.py',
    'src/adapters/codex_events_v2.py', 'scripts/run_diagnostic.py',
    'scripts/matrix.py', 'scripts/run_v4_pilot.py'))


def selected_tasks():
    tasks = data_v4.generate('dev')
    return [next(t for t in tasks if t['task_family'] == family)
            for family in ('evidence', 'table')]


def load_verified_batch(batch, tasks, executable):
    """Return config, manifest, never-started entries and interrupted IDs.

    Refuse changed inputs, corrupt records, and any completed service/protocol
    error. An interrupted episode is retained, not restarted or overwritten.
    """
    batch = Path(batch).resolve()
    if batch.parent != (ROOT / 'runs').resolve() or not batch.name.startswith('v4-pilot-'):
        raise ValueError('resume directory must be an existing v4 pilot under runs')
    config = json.loads((batch/'config.json').read_text(encoding='utf-8'))
    recorded_hash = json.loads((batch/'config_hash.json').read_text(encoding='utf-8'))['sha256']
    manifest = json.loads((batch/'manifest.json').read_text(encoding='utf-8'))
    expected = build_manifest(tasks, ['gpt-6-luna'], PROFILES, 1, 4125)
    if (digest(config) != recorded_hash or digest(manifest) != config['manifest_hash']
            or manifest != expected or digest(tasks) != config['task_hash']
            or code_hash(CODE_PATHS) != config['code_hash']
            or hashlib.sha256(Path(executable).read_bytes()).hexdigest() != config['binary_sha256']
            or config['tool_schemas'] != data_v4.tool_schemas()):
        raise ValueError('resume refused: configuration, data, code, binary or manifest changed')
    pending, interrupted = [], []
    for entry in manifest:
        ident = entry['run_id']
        started = batch/'started'/(ident+'.json')
        journal = batch/'journals'/(ident+'.jsonl')
        result = batch/'episodes'/(ident+'.json')
        if result.exists():
            row = json.loads(result.read_text(encoding='utf-8'))
            if not started.exists() or not journal.exists():
                raise ValueError('completed episode missing started marker or journal')
            if json.loads(started.read_text(encoding='utf-8')) != entry or row.get('manifest') != entry:
                raise ValueError('completed episode manifest mismatch')
            outcome = row['result']
            if outcome.get('metadata', {}).get('config_hash') != recorded_hash:
                raise ValueError('completed episode config mismatch')
            if outcome.get('termination_reason') in ('service_error', 'protocol_violation'):
                raise ValueError('service or protocol failure requires review and a new batch')
            events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines()]
            if not events or events[-1].get('kind') != 'episode_finished':
                raise ValueError('completed journal is incomplete')
        elif started.exists() or journal.exists():
            if not started.exists() or json.loads(started.read_text(encoding='utf-8')) != entry:
                raise ValueError('invalid interrupted episode marker')
            interrupted.append(ident)
        else:
            pending.append(entry)
    return batch, config, manifest, pending, interrupted


async def main(resume=None):
    tasks = selected_tasks()
    schemas = data_v4.tool_schemas()
    model = CodexMXCV2(denied_roots=[str(ROOT)])
    executable = Path(model.executable)
    binary_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    if resume:
        batch, config, manifest, pending, interrupted = load_verified_batch(resume, tasks, executable)
        fast = config['calibration']['fast']
    else:
        fast = await calibrate(NAMES, 2, tool_call=data_v4.call_tool)
        manifest = build_manifest(tasks, ['gpt-6-luna'], PROFILES, 1, 4125)
        config = {'purpose': 'exploratory v4 development; not formal', 'model': model.model,
              'budget_s': 120, 'fast_s': 2, 'slow_s': 15, 'shift_fraction': 0.30,
              'repeats': 1, 'concurrency': 1, 'manifest_seed': 4125,
              'calibration': {'fast': fast},
              'calibration_note': 'separate concurrent measurements per tool outside episodes',
              'task_hash': digest(tasks), 'manifest_hash': digest(manifest),
              'code_hash': code_hash(CODE_PATHS), 'binary_sha256': binary_hash,
              'tool_schemas': schemas, 'token_usage': None, 'estimated_cost': None,
              'isolation': 'candidate MXC, no independent end-to-end isolation proof',
              'timing': 'CLI terminal event timing is conservative and requires validation'}
        batch = ROOT/'runs'/('v4-pilot-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        batch.mkdir(parents=True, exist_ok=False)
        write_new(batch/'config.json', config)
        write_new(batch/'config_hash.json', {'sha256': digest(config)})
        write_new(batch/'manifest.json', manifest)
        pending, interrupted = manifest, []
    task_map = {t['task_id']: t for t in tasks}
    print(json.dumps({'batch': str(batch), 'planned_episodes': len(manifest),
                      'pending': len(pending), 'interrupted': interrupted,
                      'purpose': config['purpose']}, ensure_ascii=False), flush=True)
    try:
        for entry in pending:
            if code_hash(CODE_PATHS) != config['code_hash']:
                raise RuntimeError('source changed during batch')
            if hashlib.sha256(executable.read_bytes()).hexdigest() != config['binary_sha256']:
                raise RuntimeError('CLI binary changed during batch')
            run_id = entry['run_id']
            write_new(batch/'started'/(run_id+'.json'), entry)
            journal = EpisodeJournal(batch/'journals'/(run_id+'.jsonl'))
            task = task_map[entry['task_id']]
            schema = schemas[task['task_family']]
            baseline = fast
            try:
                result = await run_episode(model, question=task['public']['question'], tool_schemas=schema,
                    calibration={name: baseline[name] for name in schema},
                    call_tool=lambda name, args: data_v4.call_tool(task['public'], name, args),
                    verify=lambda answer: data_v4.verify(task['private'], answer),
                    condition=entry['condition'], profile=entry['profile'], budget_s=120,
                    shift_fraction=.30, event_sink=journal.emit,
                    metadata={**entry, 'config_hash': digest(config), 'purpose': config['purpose'],
                              'isolation': config['isolation'], 'token_usage': None, 'estimated_cost': None})
                write_new(batch/'episodes'/(run_id+'.json'), {'manifest': entry, 'result': result})
                print(json.dumps({'run_id': run_id, 'termination_reason': result['termination_reason'],
                                  'deadline_success': result['deadline_success'],
                                  'elapsed_s': result['elapsed_s']}, ensure_ascii=False), flush=True)
                if result['termination_reason'] in ('service_error', 'protocol_violation'):
                    break
            except BaseException as exc:
                journal.emit({'kind': 'episode_interrupted', 'exception_type': type(exc).__name__})
                raise
            finally:
                journal.close()
    finally:
        await model.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', help='validated v4 pilot; only never-started entries run')
    args = parser.parse_args()
    asyncio.run(main(args.resume))

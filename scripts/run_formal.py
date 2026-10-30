"""Formal Luna batch entry point. SAFETY GATES ARE NOT IMPLEMENTED: no run can start.

The checked-in CodexMXC wrapper does not yet prove end-to-end isolation.
This module deliberately refuses both
freeze and run until those integrations exist. Never edit this guard simply to
force a run; preserve the evidence and implement independently verifiable gates.
"""
import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path

from tasks.data_v2 import generate, call_tool, verify
from src.runner import run_episode
from src.adapters.codex_mxc import CodexMXC
from scripts.run_diagnostic import SCHEMAS
from scripts.matrix import freeze, verify_frozen, execute_pending

ROOT = Path(__file__).resolve().parent.parent
CODE_FILES = tuple(ROOT / p for p in (
    'tasks/data.py', 'tasks/data_v2.py', 'src/runner.py', 'src/conditions.py', 'src/protocol.py',
    'src/adapters/codex_mxc.py', 'scripts/run_diagnostic.py', 'scripts/matrix.py',
    'scripts/run_formal.py', 'scripts/analyze_matrix.py'))
PROFILES = ['stable_fast', 'fast_to_slow', 'slow_to_fast']


def _evidence_file(item, name):
    if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
        raise ValueError(name + ' must provide path and sha256')
    path = Path(item['path']).resolve()
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError(name + ' evidence missing or checksum mismatch')
    return path


def validate_inputs(config):
    """Reject incomplete study configuration before any model invocation."""
    if config.get('models') != ['gpt-6-luna'] or config.get('profiles') != PROFILES:
        raise ValueError('only the specified Luna model and three profiles are supported')
    if config.get('repeats') != 2 or config.get('concurrency') != 1:
        raise ValueError('formal matrix requires two repetitions and serial execution')
    if type(config.get('manifest_seed')) is not int:
        raise ValueError('manifest_seed required')
    timing = config.get('timing', {})
    for key in ('budget_s', 'fast_s', 'slow_s'):
        x = timing.get(key)
        if type(x) not in (int, float) or not math.isfinite(x) or x <= 0:
            raise ValueError('invalid timing: ' + key)
    fraction = timing.get('shift_fraction')
    if type(fraction) not in (int, float) or not 0 < fraction < 1 or timing.get('window') != 3 or timing.get('max_steps') != 20:
        raise ValueError('invalid shift, window or step limit')
    cal = config.get('calibration', {})
    for phase in ('fast', 'slow'):
        for name in ('search', 'read_document', 'lookup_rows', 'calculate'):
            samples = cal.get(phase, {}).get(name, [])
            if len(samples) < 3 or any(type(x) not in (int,float) or not math.isfinite(x) or x < 0 for x in samples):
                raise ValueError('calibration samples missing: ' + phase + '/' + name)
    resources = config.get('resource_budget', {})
    allowed_seconds = resources.get('max_budget_s_per_episode')
    if (resources.get('max_episodes') != 360 or type(allowed_seconds) not in (int, float)
            or not math.isfinite(allowed_seconds) or allowed_seconds < timing['budget_s']):
        raise ValueError('resource budget must cover 360 Luna episodes and the per-episode deadline')
    for field in ('protocol', 'prompt', 'model_settings', 'analysis'):
        if not config.get(field):
            raise ValueError('missing frozen setting: ' + field)
    for field in ('isolation_evidence', 'development_evidence'):
        _evidence_file(config.get(field), field)


def readiness(config):
    validate_inputs(config)
    validate_development(_evidence_file(config['development_evidence'], 'development_evidence'))
    # Evidence-file existence alone cannot establish isolation. Fail closed
    # until an independently enforced boundary and a real verifier exist.
    raise RuntimeError('Formal execution blocked: end-to-end isolation is not independently verified.')


def validate_development(manifest_file):
    """Check trace coverage and observable shifts; no test-set data is consulted."""
    directory = manifest_file.parent
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    dev_config = json.loads((directory / 'config.json').read_text(encoding='utf-8'))
    from scripts.matrix import digest
    tasks = generate('dev')
    expected = {(t['task_id'], profile, condition) for t in tasks for profile in PROFILES for condition in 'ABC'}
    actual = {(e['task_id'], e['profile'], e['condition']) for e in manifest if e.get('model_id') == 'gpt-6-luna'}
    if len(manifest) != len(expected) or actual != expected:
        raise ValueError('development manifest does not cover the required 72 unique episodes')
    families = set()
    observed = 0
    shifted = 0
    for entry in manifest:
        path = directory / 'episodes' / (entry['run_id'] + '.json')
        row = json.loads(path.read_text(encoding='utf-8'))
        result = row['result']
        if row.get('manifest') != entry or result.get('metadata', {}).get('config_hash') != digest(dev_config):
            raise ValueError('development record or config mismatch')
        if result['termination_reason'] in ('service_error', 'protocol_violation'):
            raise ValueError('development includes unresolved service or protocol failures')
        if result.get('valid_submission'):
            families.add(entry['task_family'])
        if entry['profile'] != 'stable_fast':
            shifted += 1
            ev = result['events']
            boundary = result['budget_s'] * result['shift_fraction']
            if any(e.get('event_type') == 'tool' and not e.get('is_censored')
                   and 'observed_duration_s' in e and e['tool_start_offset_s'] >= boundary
                   and any(n.get('event_type') == 'model_request' and n['request_start_offset_s'] >= e['tool_end_offset_s'] for n in ev)
                   for e in ev):
                observed += 1
    if families != {'evidence', 'table'}:
        raise ValueError('both development task families require an on-time valid submission')
    if observed * 2 < shifted:
        raise ValueError('most shifted development episodes lack an observable shift followed by a decision')


def prepare(batch, config):
    readiness(config)
    return freeze(batch, config, generate('test'), CODE_FILES)


def inspect_existing(batch, manifest, config_hash):
    """Validate existing output before resuming; require repair after service faults."""
    for entry in manifest:
        run_id = entry['run_id']
        result_file = Path(batch)/'episodes'/(run_id+'.json')
        started = Path(batch)/'started'/(run_id+'.json')
        if not result_file.exists():
            continue
        row = json.loads(result_file.read_text(encoding='utf-8'))
        if not started.exists() or row.get('manifest') != entry or row.get('result',{}).get('metadata',{}).get('config_hash') != config_hash:
            raise ValueError('inconsistent completed record ' + run_id)
        if row['result'].get('termination_reason') in ('service_error', 'protocol_violation'):
            raise ValueError('batch halted after error; repair and document recovery before proceeding')


async def run(batch):
    tasks = generate('test')
    frozen, manifest = verify_frozen(batch, tasks, CODE_FILES)
    config = frozen['config']
    readiness(config)
    inspect_existing(batch, manifest, frozen['config_hash'])
    task_map = {task['task_id']: task for task in tasks}
    timing = config['timing']
    async def one(entry, journal):
        task = task_map[entry['task_id']]
        schemas = SCHEMAS[task['task_family']]
        phase = 'slow' if entry['profile'] == 'slow_to_fast' else 'fast'
        model = CodexMXC(model=entry['model_id'], denied_roots=[str(ROOT)])
        return await run_episode(model, question=task['public']['question'], tool_schemas=schemas,
            calibration={name: config['calibration'][phase][name] for name in schemas},
            call_tool=lambda name, args: call_tool(task['public'], name, args),
            verify=lambda answer: verify(task['private'], answer),
            condition=entry['condition'], profile=entry['profile'], budget_s=timing['budget_s'],
            fast_s=timing['fast_s'], slow_s=timing['slow_s'], shift_fraction=timing['shift_fraction'],
            window=timing['window'], max_steps=timing['max_steps'], event_sink=journal.emit,
            metadata={**entry, 'config_hash': frozen['config_hash'], 'token_usage': None, 'estimated_cost': None})
    return await execute_pending(batch, one, tasks=tasks, code_paths=CODE_FILES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('freeze'); p.add_argument('--config', required=True); p.add_argument('--batch', required=True)
    p = sub.add_parser('run'); p.add_argument('--batch', required=True)
    args = parser.parse_args()
    if args.command == 'freeze':
        config = json.loads(Path(args.config).read_text(encoding='utf-8'))
        prepare(args.batch, config)
    else:
        print(json.dumps(asyncio.run(run(args.batch)), ensure_ascii=False))

if __name__ == '__main__': main()

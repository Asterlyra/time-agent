"""Study 2 driver: deadline-budgeted partial-credit information gathering.

Commands
  prepare <stage>   build a frozen batch (stage: pilot|formal) with hashes
  run <batch>       execute never-started manifest entries
  analyze <batch>   structural summary; statistical analysis lives in study2_stats

Design in one paragraph. Each episode gives a fixed wall-clock budget and 20
opaque items; every `fetch` call costs real time and reveals one integer. The
agent may submit any subset at any moment, one point per correct item, zero for
unsubmitted items, and zero for the whole episode if the deadline passes without
a submission. Because partial credit exists, the expected cost of the next call
changes the optimal stopping point, so a latency reference can change the action
— the property the v4 task family lacked. Conditions A/B/C/O differ only in the
duration reference shown in the observation.
"""
import argparse
import asyncio
import collections
import datetime
import hashlib
import json
import math
import os
import statistics
from pathlib import Path

import httpx

from scripts.matrix import EpisodeJournal, canonical, code_hash, digest, write_new
from src.adapters.go_items import MODELS, PROMPT_ITEMS
from src.adapters.opencode_go import BASE_URL
from src.adapters.go_items import GoItems
from src.conditions_v3 import CONDITIONS
from src.elapsed_clock import EpisodeClock, clock_metadata
from src.runner_v3 import run_episode
from tasks import data_v6

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ('stable_fast', 'fast_to_slow', 'drift_up')
CODE_PATHS = tuple(ROOT / p for p in (
    'src/adapters/opencode_go.py', 'src/adapters/sse.py', 'src/adapters/go_items.py',
    'src/runner_v3.py', 'src/conditions.py', 'src/conditions_v3.py',
    'src/elapsed_clock.py', 'src/protocol.py', 'src/calibration.py',
    'tasks/data_v6.py', 'scripts/matrix.py', 'scripts/study2.py', 'requirements.txt'))

DEFAULTS = {
    'budget_s': 200.0, 'shift_fraction': 0.30, 'fast_s': 8.0, 'slow_s': 60.0,
    'window': 1, 'max_steps': 32, 'max_tokens': 2048, 'streaming': True,
    'concurrency_per_model': 2, 'manifest_seed': 20261102,
}


def tasks_for(stage):
    return data_v6.generate('test' if stage == 'formal' else 'dev')


def build_manifest2(tasks, models, profiles, conditions=CONDITIONS, seed=20261102):
    """One block per (model, task, profile); all conditions run adjacently."""
    keys = [(m, t, p) for m in models for t in tasks for p in profiles]
    if len({(m, t['task_id'], p) for m, t, p in keys}) != len(keys):
        raise ValueError('duplicate model/task/profile')
    import itertools
    perms = list(itertools.permutations(conditions))
    rng = __import__('random').Random(seed)
    rng.shuffle(keys)
    result = []
    for i, (model, task, profile) in enumerate(keys):
        if i % len(perms) == 0:
            rng.shuffle(perms)
        order = perms[i % len(perms)]
        block_id = digest({'model_id': model, 'task_id': task['task_id'], 'profile': profile})[:16]
        for position, condition in enumerate(order):
            entry = {'model_id': model, 'task_id': task['task_id'],
                     'task_family': task['task_family'], 'template_id': task['template_id'],
                     'data_seed': task['data_seed'], 'profile': profile,
                     'condition': condition, 'block_id': block_id, 'position': position}
            entry['run_id'] = digest(entry)[:24]
            result.append(entry)
    return result


async def measure_delay(target_s, repeats=3):
    """Measure the host's own injection path outside any task budget."""
    if repeats < 3 or target_s < 0:
        raise ValueError('invalid calibration settings')
    async def sample():
        clock = EpisodeClock()
        await clock.wait(asyncio.sleep(max(0, target_s - clock.elapsed())), clock.start + target_s + 5)
        clock.check()
        return clock.elapsed()
    return list(await asyncio.gather(*(sample() for _ in range(repeats))))


async def prepare(stage, *, budget=None, shift=None, fast=None, slow=None, seed=None,
                  reason='', tasks_limit=None, budget_by_model=None, profiles=None):
    if stage not in ('pilot', 'formal'):
        raise ValueError('stage must be pilot or formal')
    cfg = dict(DEFAULTS)
    if budget is not None: cfg['budget_s'] = float(budget)
    if shift is not None: cfg['shift_fraction'] = float(shift)
    if fast is not None: cfg['fast_s'] = float(fast)
    if slow is not None: cfg['slow_s'] = float(slow)
    if seed is not None: cfg['manifest_seed'] = int(seed)
    if not 0 < cfg['shift_fraction'] < 1:
        raise ValueError('shift_fraction must be in (0,1)')
    all_tasks = tasks_for(stage)
    tasks = all_tasks[:tasks_limit] if tasks_limit else all_tasks
    use_profiles = tuple(profiles or PROFILES)
    if any(p not in PROFILES for p in use_profiles):
        raise ValueError('unknown profile')
    manifest = build_manifest2(tasks, list(MODELS), use_profiles, CONDITIONS, cfg['manifest_seed'])
    budgets = dict(budget_by_model or {})
    for model in MODELS:
        budgets.setdefault(model, cfg['budget_s'])
    fast_samples = await measure_delay(cfg['fast_s'])
    slow_samples = await measure_delay(cfg['slow_s'])
    config = {
        'study': 'S2-deadline-partial-credit',
        'stage': stage,
        'models': list(MODELS),
        'item_count': data_v6.ITEM_COUNT,
        'budget_s': cfg['budget_s'], 'budget_by_model': budgets,
        'shift_fraction': cfg['shift_fraction'],
        'fast_s': cfg['fast_s'], 'slow_s': cfg['slow_s'], 'window': cfg['window'],
        'max_steps': cfg['max_steps'], 'max_tokens': cfg['max_tokens'],
        'streaming': cfg['streaming'], 'profiles': list(use_profiles),
        'conditions': list(CONDITIONS),
        'concurrency': {'global': 3 * cfg['concurrency_per_model'],
                        'per_model': cfg['concurrency_per_model']},
        'manifest_seed': cfg['manifest_seed'],
        'calibration': {'fast': {'fetch': fast_samples}, 'slow': {'fetch': slow_samples}},
        'calibration_method': 'host injection path measured outside episodes, three samples per phase',
        'task_hash': digest(all_tasks), 'tasks_in_manifest': len(tasks),
        'manifest_hash': digest(manifest), 'code_hash': code_hash(CODE_PATHS),
        'tool_schemas': data_v6.tool_schemas(), 'prompt': PROMPT_ITEMS, 'base_url': BASE_URL,
        'model_settings': {'temperature': 'provider default; not set', 'max_tokens': cfg['max_tokens'],
                           'reasoning': 'provider default; not set', 'stream': cfg['streaming']},
        'protocol': 'one text JSON action; no native/external tool execution; partial-credit submission',
        'scoring': {'per_correct_item': 1, 'unsubmitted': 0, 'wrong': 0, 'no_submission': 0},
        'limits': {'max_requests_per_model': 12000 if stage == 'formal' else 1200,
                   'max_reported_allowance_per_model': 8.0 if stage == 'formal' else 2.0},
        'clock': clock_metadata(),
        'change_reason': reason,
        'purpose': ('frozen formal S2 experiment' if stage == 'formal'
                    else 'pilot only; parameter calibration, no effect inference'),
        'analysis': {
            'primary': 'fast_to_slow score difference C-B, equal weight over the three models',
            'secondary': ['B-A', 'C-A', 'O-A', 'O-B', 'C-B per other profile'],
            'bootstrap': '10000 task-cluster paired draws, stratified by profile',
            'seed': 911, 'individual_intervals': 'exploratory, uncorrected'},
    }
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    batch = ROOT / 'runs' / f's2-{stage}-{stamp}'
    batch.mkdir(parents=True, exist_ok=False)
    write_new(batch / 'config.json', config)
    write_new(batch / 'config_hash.json', {'sha256': digest(config)})
    write_new(batch / 'manifest.json', manifest)
    archived = {}
    for source in CODE_PATHS:
        target = batch / 'source_snapshot' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as f:
            f.write(source.read_bytes())
        archived[str(source.as_posix())] = hashlib.sha256(target.read_bytes()).hexdigest()
    write_new(batch / 'source_snapshot_hashes.json', archived)
    return batch


def load_batch(batch):
    batch = Path(batch).resolve()
    if batch.parent != (ROOT / 'runs').resolve() or not batch.name.startswith('s2-'):
        raise ValueError('expected s2-* batch under project runs')
    config = json.loads((batch / 'config.json').read_text())
    manifest = json.loads((batch / 'manifest.json').read_text())
    if (digest(config) != json.loads((batch / 'config_hash.json').read_text())['sha256']
            or digest(manifest) != config['manifest_hash']
            or code_hash(CODE_PATHS) != config['code_hash']
            or digest(tasks_for(config['stage'])) != config['task_hash']):
        raise ValueError('batch code/config/manifest/task changed; use a new versioned batch')
    return batch, config, manifest


def block_queues(manifest):
    """Keep every condition of one (model, task, profile) block on one worker."""
    groups = {m: collections.OrderedDict() for m in MODELS}
    for entry in manifest:
        groups[entry['model_id']].setdefault(entry['block_id'], []).append(entry)
    return {m: collections.deque(v.values()) for m, v in groups.items()}


def analyze(batch, *, verify=True):
    if verify:
        batch, config, manifest = load_batch(batch)
    else:
        batch = Path(batch)
        config = json.loads((batch / 'config.json').read_text())
        manifest = json.loads((batch / 'manifest.json').read_text())
    rows, missing, interrupted = [], [], []
    for e in manifest:
        p = batch / 'episodes' / (e['run_id'] + '.json')
        if not p.exists():
            if (batch / 'started' / (e['run_id'] + '.json')).exists():
                # A host suspend killed the process mid-episode. The episode is
                # never re-run: it is archived as an environment failure and
                # scores zero, exactly as an end-to-end timeout would.
                interrupted.append(e['run_id'])
                rows.append({'manifest': e, 'result': {
                    'score': 0, 'total_items': None, 'deadline_success': False,
                    'termination_reason': 'environment_interruption',
                    'elapsed_s': None, 'budget_s': config['budget_by_model'][e['model_id']],
                    'events': [], 'final_answer': None,
                    'infrastructure_error_flags': [{'type': 'host_suspend', 'offset_s': None}],
                    'archived_interruption': True}})
            else:
                missing.append(e['run_id'])
            continue
        rows.append(json.loads(p.read_text()))
    cells = []
    for key in sorted({(r['manifest']['model_id'], r['manifest']['profile'], r['manifest']['condition'])
                       for r in rows}):
        z = [r['result'] for r in rows
             if (r['manifest']['model_id'], r['manifest']['profile'], r['manifest']['condition']) == key]
        cells.append({'model': key[0], 'profile': key[1], 'condition': key[2], 'n': len(z),
                      'mean_score': statistics.mean(r['score'] for r in z),
                      'perfect': sum(r['deadline_success'] for r in z),
                      'no_submission': sum(r['termination_reason'] != 'submitted' for r in z),
                      'termination': dict(collections.Counter(r['termination_reason'] for r in z))})
    failures = sum(r['result']['termination_reason'] in
                   ('service_error', 'protocol_violation', 'environment_interruption') for r in rows)
    return {'batch': str(batch), 'stage': config['stage'], 'planned': len(manifest),
            'completed': len(rows), 'missing': missing, 'interrupted': interrupted,
            'cells': cells, 'failures': failures,
            'all_planned_results_present': not missing}


async def execute(batch, *, max_blocks=None, resume=False):
    batch, config, manifest = load_batch(batch)
    task_map = {t['task_id']: t for t in tasks_for(config['stage'])}
    if (batch / 'stop_requested.json').exists():
        raise ValueError('operator stop request present')
    archived = set()
    for entry in manifest:
        if (batch / 'started' / (entry['run_id'] + '.json')).exists() and \
                not (batch / 'episodes' / (entry['run_id'] + '.json')).exists():
            if not resume:
                raise ValueError('interrupted episode requires review before any new calls')
            archived.add(entry['run_id'])
    if archived:
        write_new(batch / ('resume-' + datetime.datetime.now(datetime.timezone.utc)
                           .strftime('%Y%m%dT%H%M%S%fZ') + '.json'),
                  {'archived_environment_failures': sorted(archived),
                   'policy': 'never rerun a started episode; score it zero and keep it in the matrix'})
    write_new(batch / 'run_lock.json', {'pid': os.getpid(), 'config_hash': digest(config)})
    queues = block_queues(manifest)
    halt = asyncio.Event()

    def runtime(state):
        data = {'pid': os.getpid(), 'state': state, 'config_hash': digest(config),
                'updated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'completed': len(list((batch / 'episodes').glob('*.json')))}
        temp = batch / 'runtime_state.tmp'
        temp.write_text(json.dumps(data) + '\n')
        temp.replace(batch / 'runtime_state.json')

    runtime('running')
    totals = {m: {'requests': 0, 'allowance': 0.0} for m in MODELS}
    for entry in manifest:
        p = batch / 'episodes' / (entry['run_id'] + '.json')
        if p.exists():
            r = json.loads(p.read_text())['result']
            if r['termination_reason'] in ('service_error', 'protocol_violation', 'environment_interruption'):
                raise ValueError('batch has unresolved error; inspect it and create a new version')
            for e in r['events']:
                for a in e.get('attempts', []):
                    totals[entry['model_id']]['requests'] += 1
                    totals[entry['model_id']]['allowance'] += \
                        a.get('adapter_diagnostics', {}).get('usage', {}).get('allowance', 0)

    async def run_one(entry, client):
        ident = entry['run_id']
        result_path = batch / 'episodes' / (ident + '.json')
        started = batch / 'started' / (ident + '.json')
        if result_path.exists():
            return
        if started.exists():
            return  # archived environment failure, accounted in analyze()
        if code_hash(CODE_PATHS) != config['code_hash']:
            raise ValueError('source changed during batch')
        write_new(started, entry)
        journal = EpisodeJournal(batch / 'journals' / (ident + '.jsonl'))
        task = task_map[entry['task_id']]
        base = GoItems(entry['model_id'], client=client,
                       session_id='ses_s2_' + batch.name + '_' + ident,
                       max_tokens=config['max_tokens'], stream=config.get('streaming', False))
        total = totals[entry['model_id']]

        class BoundedModel:
            @property
            def last_diagnostics(self):
                return base.last_diagnostics

            async def decide(self, observation, history):
                if total['requests'] >= config['limits']['max_requests_per_model'] or \
                        total['allowance'] >= config['limits']['max_reported_allowance_per_model']:
                    raise RuntimeError('local_resource_limit')
                total['requests'] += 1
                try:
                    return await base.decide(observation, history)
                finally:
                    usage = (base.last_diagnostics or {}).get('usage', {})
                    total['allowance'] += usage.get('allowance', 0)

        phase = 'slow' if entry['profile'] == 'slow_to_fast' else 'fast'
        collected = {}

        def call_tool(name, args):
            result = data_v6.call_tool(task['public'], name, args)
            if isinstance(result, dict) and 'item_id' in result:
                collected.setdefault(result['item_id'], result['value'])
            return result

        try:
            result = await run_episode(
                BoundedModel(), question=data_v6.public_view(task)['question'],
                tool_schemas=config['tool_schemas'],
                calibration={k: config['calibration'][phase][k] for k in config['tool_schemas']},
                call_tool=call_tool,
                verify=lambda _answer: data_v6.verify(task['private'], collected),
                state_provider=lambda: {'collected_items': data_v6.collected_state(collected)},
                validate_submission=data_v6.validate_submission,
                condition=entry['condition'], profile=entry['profile'],
                budget_s=config['budget_by_model'][entry['model_id']],
                shift_fraction=config['shift_fraction'],
                fast_s=config['fast_s'], slow_s=config['slow_s'], window=config['window'],
                max_steps=config['max_steps'], event_sink=journal.emit,
                metadata={**entry, 'config_hash': digest(config),
                          'access': 'OpenCode Go HTTP; no CLI', 'phase': config['stage']})
            write_new(result_path, {'manifest': entry, 'result': result})
            runtime('running')
            print(json.dumps({'model': entry['model_id'], 'task': entry['task_id'],
                              'profile': entry['profile'], 'condition': entry['condition'],
                              'score': result['score'], 'termination': result['termination_reason'],
                              'elapsed_s': round(result['elapsed_s'], 1)}, ensure_ascii=False), flush=True)
            if result['termination_reason'] in ('service_error', 'protocol_violation',
                                                'environment_interruption'):
                halt.set()
        except BaseException as exc:
            journal.emit({'kind': 'episode_interrupted', 'exception_type': type(exc).__name__})
            halt.set()
            raise
        finally:
            journal.close()

    async def worker(model_id):
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20), follow_redirects=False) as client:
            done_blocks = 0
            while queues[model_id]:
                if halt.is_set() or (batch / 'stop_requested.json').exists():
                    break
                if max_blocks is not None and done_blocks >= max_blocks:
                    break
                block = queues[model_id].popleft()
                for entry in block:
                    if halt.is_set():
                        break
                    await run_one(entry, client)
                done_blocks += 1

    try:
        await asyncio.gather(*(worker(m) for m in MODELS for _ in range(config['concurrency']['per_model'])))
    except BaseException:
        runtime('interrupted')
        raise
    finally:
        (batch / 'run_lock.json').unlink(missing_ok=True)
    report = analyze(batch)
    runtime('completed' if not report['missing'] else 'halted')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    write_new(batch / ('analysis-' + stamp + '.json'), report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('cells', 'missing')},
                     ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('stage', choices=('pilot', 'formal'))
    p.add_argument('--budget', type=float)
    p.add_argument('--shift', type=float)
    p.add_argument('--fast', type=float)
    p.add_argument('--slow', type=float)
    p.add_argument('--seed', type=int)
    p.add_argument('--reason', default='initial registered S2 candidate')
    p.add_argument('--tasks-limit', type=int)
    p.add_argument('--budget-by-model', default=None,
                   help='comma separated model=seconds overrides')
    p.add_argument('--profiles', default=None, help='comma separated latency profiles')
    p = sub.add_parser('run')
    p.add_argument('batch')
    p.add_argument('--max-blocks', type=int)
    p.add_argument('--resume', action='store_true',
                   help='skip episodes already started before a host suspend')
    p = sub.add_parser('analyze')
    p.add_argument('batch')
    args = parser.parse_args()
    if args.command == 'prepare':
        overrides = {}
        if args.budget_by_model:
            for part in args.budget_by_model.split(','):
                model, _, value = part.partition('=')
                overrides[model.strip()] = float(value)
        print(asyncio.run(prepare(args.stage, budget=args.budget, shift=args.shift, fast=args.fast,
                                  slow=args.slow, seed=args.seed, reason=args.reason,
                                  tasks_limit=args.tasks_limit, budget_by_model=overrides,
                                  profiles=(args.profiles.split(',') if args.profiles else None))))
    elif args.command == 'run':
        asyncio.run(execute(args.batch, max_blocks=args.max_blocks, resume=args.resume))
    else:
        print(json.dumps(analyze(args.batch), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Study 3 driver: information, commitment and enforcement under a hard deadline.

Four models, two task families, three stochastic latency regimes and five arms.
Every arm runs the same episode code; only the policy object differs (see
src/time_policies.py). Command surface mirrors the earlier studies:

  prepare <part>   freeze a batch ('A' or 'B')
  run <batch>      execute never-started manifest entries
  analyze <batch>  structural summary
"""
import argparse
import asyncio
import collections
import datetime
import hashlib
import itertools
import json
import math
import os
import random
import statistics
from pathlib import Path

import httpx

from scripts.matrix import EpisodeJournal, code_hash, digest, write_new
from src.adapters.go_items_v2 import MODELS, PROMPT_ITEMS, GoItemsV2
from src.adapters.opencode_go import BASE_URL
from src.elapsed_clock import EpisodeClock, clock_metadata
from src.runner_v4 import run_episode
from src.time_policies import ARMS, make_policy
from tasks import data_v7

ROOT = Path(__file__).resolve().parent.parent
FAMILIES = ('uniform', 'hetero')
REGIMES = ('light_tail', 'fast_heavy', 'slow_heavy', 'drift_heavy')
CONDITIONS = ('I0', 'I1', 'C', 'E', 'O')
TASKS_PER_FAMILY = 16
CONCURRENCY_PER_MODEL = 2
MANIFEST_SEED = 20261103
REPEATS = {'glm-5.3-flash': 3, 'deepseek-v4.1-flash': 3, 'mimo-v2.6-flash': 3,
           'qwen3.8-flash': 2}

CODE_PATHS = tuple(ROOT / p for p in (
    'src/adapters/opencode_go.py', 'src/adapters/sse.py', 'src/adapters/go_items_v2.py',
    'src/runner_v4.py', 'src/time_policies.py', 'src/elapsed_clock.py', 'src/protocol.py',
    'tasks/data_v7.py', 'scripts/matrix.py', 'scripts/study3.py', 'requirements.txt'))


def regime_multiplier(regime, elapsed, budget):
    if regime == 'light_tail':
        return 1.0
    if regime == 'fast_heavy':
        return 1.0
    if regime == 'slow_heavy':
        return 3.0
    return 1.0 + 2.0 * min(1.0, max(0.0, elapsed / budget))


def regime_sigma(regime, base):
    """The light-tail regime makes call durations nearly deterministic."""
    return 0.15 if regime == 'light_tail' else base


class DurationSampler:
    """One draw per call, at the moment the call starts. Seeded per episode."""

    def __init__(self, task, regime, seed):
        self.rng = random.Random(seed)
        self.means = task['private']['size_means']
        self.size_of = task['private']['size_of']
        self.sigma = regime_sigma(regime, task['private']['sigma'])
        self.regime = regime
        self.budget = task['public']['budget_s']
        self.draws = []

    def __call__(self, item_id, elapsed):
        mu = self.means[self.size_of[item_id]] * regime_multiplier(self.regime, elapsed, self.budget)
        value = math.exp(self.rng.gauss(math.log(mu) - self.sigma ** 2 / 2.0, self.sigma))
        self.draws.append({'item_id': item_id, 'mu': round(mu, 3), 'draw': round(value, 3)})
        return value


def tasks_for(part, per_family=None):
    if part not in ('A', 'B'):
        raise ValueError("part must be 'A' or 'B'")
    per_family = TASKS_PER_FAMILY if per_family is None else per_family
    tasks = data_v7.generate('test')
    index = {'A': 0, 'B': per_family}[part]
    keep = {f'test-{family}-{i:02d}' for family in FAMILIES for i in range(index, index + per_family)}
    selected = [task for task in tasks if task['task_id'] in keep]
    if len(selected) != 2 * per_family:
        raise ValueError('task selection mismatch')
    return selected


def build_manifest(tasks, models, seed=MANIFEST_SEED):
    keys = [(model, task, regime) for model in models for task in tasks for regime in REGIMES]
    rng = random.Random(seed)
    rng.shuffle(keys)
    orders = list(itertools.permutations(CONDITIONS))
    entries = []
    for i, (model, task, regime) in enumerate(keys):
        if i % len(orders) == 0:
            rng.shuffle(orders)
        order = orders[i % len(orders)]
        block_id = digest({'model_id': model, 'task_id': task['task_id'], 'regime': regime})[:16]
        for repeat in range(REPEATS[model]):
            for position, condition in enumerate(order):
                entry = {'model_id': model, 'task_id': task['task_id'],
                         'task_family': task['task_family'], 'template_id': task['template_id'],
                         'regime': regime, 'condition': condition, 'repeat': repeat,
                         'position': position, 'block_id': block_id,
                         'budget_s': task['public']['budget_s']}
                entry['run_id'] = digest(entry)[:24]
                entries.append(entry)
    return entries


def block_queues(manifest):
    """All five arms of one (model, task, regime) block stay on a single worker."""
    groups = {model: collections.OrderedDict() for model in MODELS}
    for entry in manifest:
        groups[entry['model_id']].setdefault(entry['block_id'], []).append(entry)
    return {model: collections.deque(value.values()) for model, value in groups.items()}


def seed_for(run_id):
    return int(hashlib.sha256(run_id.encode()).hexdigest()[:12], 16)


async def prepare(part, *, reason='', seed=MANIFEST_SEED, tasks_per_family=TASKS_PER_FAMILY):
    tasks = tasks_for(part, tasks_per_family)
    manifest = build_manifest(tasks, list(MODELS), seed)
    config = {
        'study': 'S3-information-commitment-enforcement',
        'part': part,
        'models': list(MODELS),
        'families': list(FAMILIES),
        'regimes': list(REGIMES),
        'conditions': list(CONDITIONS),
        'repeats_per_model': dict(REPEATS),
        'tasks_per_family': tasks_per_family,
        'manifest_seed': seed,
        'budgets': {task['task_id']: task['public']['budget_s'] for task in tasks},
        'sigma': data_v7.SIGMA,
        'regime_rule': {'light_tail': 'multiplier 1.0, sigma 0.15 (nearly deterministic)',
                        'fast_heavy': 'multiplier 1.0, sigma 1.0',
                        'slow_heavy': 'multiplier 3.0, sigma 1.0',
                        'drift_heavy': 'multiplier grows 1 to 3 across the episode, sigma 1.0'},
        'concurrency': {'global': len(MODELS) * CONCURRENCY_PER_MODEL,
                        'per_model': CONCURRENCY_PER_MODEL},
        'task_hash': digest(tasks), 'manifest_hash': digest(manifest),
        'code_hash': code_hash(CODE_PATHS),
        'tool_schemas': data_v7.tool_schemas(), 'prompt': PROMPT_ITEMS, 'base_url': BASE_URL,
        'model_settings': {'temperature': 'provider default; not set', 'max_tokens': 2048,
                           'reasoning': 'provider default; not set', 'stream': True},
        'protocol': 'one text JSON action; host-scored submission; harness may deny or force',
        'clock': clock_metadata(),
        'change_reason': reason,
        'analysis': {
            'primary': 'hetero family, arms E minus I0, equal weight over the four models',
            'secondary': ['E-O', 'C-I0', 'C-E', 'I1-I0', 'per family',
                          'per regime, in particular light_tail as the negative control'],
            'bootstrap': '10000 block-cluster paired draws, seed 911',
            'interim': 'two-look Pocock boundary, one-sided z >= 1.875 at each look'},
    }
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    batch = ROOT / 'runs' / f's3-{part}-{stamp}'
    batch.mkdir(parents=True, exist_ok=False)
    write_new(batch / 'config.json', config)
    write_new(batch / 'config_hash.json', {'sha256': digest(config)})
    write_new(batch / 'manifest.json', manifest)
    archived = {}
    for source in CODE_PATHS:
        target = batch / 'source_snapshot' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            handle.write(source.read_bytes())
        archived[str(source.as_posix())] = hashlib.sha256(target.read_bytes()).hexdigest()
    write_new(batch / 'source_snapshot_hashes.json', archived)
    return batch


def load_batch(batch):
    batch = Path(batch).resolve()
    if batch.parent != (ROOT / 'runs').resolve() or not batch.name.startswith('s3-'):
        raise ValueError('expected s3-* batch under project runs')
    config = json.loads((batch / 'config.json').read_text())
    manifest = json.loads((batch / 'manifest.json').read_text())
    if (digest(config) != json.loads((batch / 'config_hash.json').read_text())['sha256']
            or digest(manifest) != config['manifest_hash']
            or code_hash(CODE_PATHS) != config['code_hash']
            or digest(tasks_for(config['part'], config['tasks_per_family'])) != config['task_hash']):
        raise ValueError('batch code/config/manifest/task changed; use a new versioned batch')
    return batch, config, manifest


def analyze(batch, *, verify=True):
    if verify:
        batch, config, manifest = load_batch(batch)
    else:
        batch = Path(batch)
        config = json.loads((batch / 'config.json').read_text())
        manifest = json.loads((batch / 'manifest.json').read_text())
    rows, missing, interrupted = [], [], []
    for entry in manifest:
        path = batch / 'episodes' / (entry['run_id'] + '.json')
        if not path.exists():
            if (batch / 'started' / (entry['run_id'] + '.json')).exists():
                interrupted.append(entry['run_id'])
                rows.append({'manifest': entry, 'result': {
                    'score': 0, 'deadline_success': False, 'forced_submit': False,
                    'termination_reason': 'environment_interruption', 'events': [],
                    'elapsed_s': None, 'budget_s': entry['budget_s'],
                    'archived_interruption': True}})
            else:
                missing.append(entry['run_id'])
            continue
        rows.append(json.loads(path.read_text()))
    cells = []
    for key in sorted({(r['manifest']['model_id'], r['manifest']['task_family'],
                        r['manifest']['regime'], r['manifest']['condition']) for r in rows}):
        z = [r['result'] for r in rows
             if (r['manifest']['model_id'], r['manifest']['task_family'],
                 r['manifest']['regime'], r['manifest']['condition']) == key]
        cells.append({'model': key[0], 'family': key[1], 'regime': key[2], 'condition': key[3],
                      'n': len(z), 'mean_score': statistics.mean(r['score'] for r in z),
                      'deadline_success': sum(r['deadline_success'] for r in z),
                      'forced_submit': sum(1 for r in z if r.get('forced_submit')),
                      'denied': sum(r.get('denied_fetches', 0) for r in z),
                      'termination': dict(collections.Counter(r['termination_reason'] for r in z))})
    failures = sum(r['result']['termination_reason'] in
                   ('service_error', 'protocol_violation', 'environment_interruption') for r in rows)
    return {'batch': str(batch), 'part': config['part'], 'planned': len(manifest),
            'completed': len(rows), 'missing': missing, 'interrupted': interrupted,
            'cells': cells, 'failures': failures,
            'all_planned_results_present': not missing}


async def execute(batch, *, resume=False):
    batch, config, manifest = load_batch(batch)
    task_map = {task['task_id']: task for task in tasks_for(config['part'], config['tasks_per_family'])}
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
                   'policy': 'never rerun a started episode; count it zero and keep it in the matrix'})
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

    async def run_one(entry, client):
        ident = entry['run_id']
        result_path = batch / 'episodes' / (ident + '.json')
        started = batch / 'started' / (ident + '.json')
        if result_path.exists() or started.exists():
            return
        if code_hash(CODE_PATHS) != config['code_hash']:
            raise ValueError('source changed during batch')
        write_new(started, entry)
        task = task_map[entry['task_id']]
        journal = EpisodeJournal(batch / 'journals' / (ident + '.jsonl'))
        base = GoItemsV2(entry['model_id'], client=client,
                         session_id='ses_s3_' + batch.name + '_' + ident,
                         max_tokens=config['model_settings']['max_tokens'], stream=True)

        class BoundedModel:
            @property
            def last_diagnostics(self):
                return base.last_diagnostics

            async def decide(self, observation, history):
                return await base.decide(observation, history)

        collected, durations = {}, []
        policy = make_policy(entry['condition'], task, collected, durations)
        sampler = DurationSampler(task, entry['regime'], seed_for(ident))
        item_ids = [item['id'] for item in task['public']['items']]

        def call_tool(name, args):
            return data_v7.call_tool(task['public'], name, args)

        try:
            result = await run_episode(
                BoundedModel(), question=data_v7.public_view(task)['question'],
                tool_schemas=config['tool_schemas'], call_tool=call_tool,
                verify=lambda _answer: data_v7.verify(task['private'], collected),
                delay_sampler=sampler, item_ids=item_ids,
                budget_s=task['public']['budget_s'], policy=policy,
                state_provider=lambda: {'collected_items': data_v7.collected_state(collected, len(item_ids))},
                event_sink=journal.emit,
                metadata={**entry, 'config_hash': digest(config), 'sampler_seed': seed_for(ident),
                          'access': 'OpenCode Go HTTP; no CLI', 'part': config['part']})
            result['sampler_draws'] = sampler.draws
            write_new(result_path, {'manifest': entry, 'result': result})
            runtime('running')
            print(json.dumps({'model': entry['model_id'][:8], 'task': entry['task_id'][-2:],
                              'family': entry['task_family'][:3], 'regime': entry['regime'][:4],
                              'arm': entry['condition'], 'score': result['score'],
                              'term': result['termination_reason'][:12],
                              'forced': result['forced_submit'], 'denied': result['denied_fetches'],
                              'elapsed': round(result['elapsed_s'] or 0, 1)}, ensure_ascii=False),
                  flush=True)
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
            while queues[model_id]:
                if halt.is_set() or (batch / 'stop_requested.json').exists():
                    break
                block = queues[model_id].popleft()
                for entry in block:
                    if halt.is_set():
                        break
                    await run_one(entry, client)

    try:
        await asyncio.gather(*(worker(model) for model in MODELS for _ in range(CONCURRENCY_PER_MODEL)))
    except BaseException:
        runtime('interrupted')
        raise
    finally:
        (batch / 'run_lock.json').unlink(missing_ok=True)
    report = analyze(batch)
    runtime('completed' if not report['missing'] else 'halted')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    write_new(batch / ('analysis-' + stamp + '.json'), report)
    print(json.dumps({k: v for k, v in report.items() if k != 'cells'}, ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('part', choices=('A', 'B'))
    p.add_argument('--reason', default='initial registered S3 candidate')
    p.add_argument('--seed', type=int, default=MANIFEST_SEED)
    p.add_argument('--tasks-per-family', type=int, default=TASKS_PER_FAMILY)
    p = sub.add_parser('run')
    p.add_argument('batch')
    p.add_argument('--resume', action='store_true')
    p = sub.add_parser('analyze')
    p.add_argument('batch')
    args = parser.parse_args()
    if args.command == 'prepare':
        print(asyncio.run(prepare(args.part, reason=args.reason, seed=args.seed,
                                  tasks_per_family=args.tasks_per_family)))
    elif args.command == 'run':
        asyncio.run(execute(args.batch, resume=args.resume))
    else:
        print(json.dumps(analyze(args.batch), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

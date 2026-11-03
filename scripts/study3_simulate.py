"""Offline design check for Study 3: run the real runner and policies with a
scripted, clock-driven agent. No API calls.

The scripted agent is a competent but myopic one: it estimates per-size costs
from the durations it has seen, always picks the remaining item with the best
value per expected second, and stops when one more call would leave no room to
submit. That is the behaviour the real models showed in S2, so the simulation
tells us whether the five arms can separate *for an agent that already reads its
clock*.
"""
import argparse
import asyncio
import collections
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import study3                                   # noqa: E402
from src.runner_v4 import run_episode                        # noqa: E402
from src.time_policies import make_policy                    # noqa: E402
from tasks import data_v7                                    # noqa: E402


class ClockDrivenAgent:
    """A model stand-in that only ever sees the observation it is given."""

    def __init__(self, task, caution=1.0):
        self.values = task['private']['values']
        self.size_of = task['private']['size_of']
        self.by_size = collections.defaultdict(list)
        self.request_times = []
        self.last_elapsed = 0.0
        self.committed = None
        self.caution = caution
        self.denied = set()

    def _estimate(self, size):
        seen = self.by_size[size]
        return statistics.mean(seen) if seen else 8.0

    async def decide(self, observation, history):
        remaining = observation['time_status']['remaining_s']
        elapsed = observation['time_status']['elapsed_s']
        if self.last_elapsed:
            self.request_times.append(max(0.0, elapsed - self.last_elapsed))
        for entry in history:
            result = entry.get('tool_result') or {}
            if 'item_id' in result and 'duration_s' in entry:
                self.by_size[self.size_of[result['item_id']]].append(entry['duration_s'])
        request_est = statistics.median(self.request_times[-5:]) if self.request_times else 6.0
        banked = set((observation.get('collected_items') or {}).get('items', {}))
        for entry in history:
            if entry.get('error') and isinstance(entry.get('action'), dict):
                item = (entry['action'].get('arguments') or {}).get('item_id')
                if item:
                    self.denied.add(item)
        candidates = [item for item in self.values
                      if item not in banked and item not in self.denied]
        if not candidates:
            self.last_elapsed = elapsed
            return {'type': 'submit'}
        if self.committed is None and 'harness_policy' in observation:
            self.committed = request_est + 3.0
            self.last_elapsed = elapsed
            return {'type': 'commit', 'reserve_s': round(self.committed, 1)}
        best = min(candidates, key=lambda item: -self.values[item] / max(self._estimate(self.size_of[item]), .1))
        cost = self._estimate(self.size_of[best])
        if remaining - cost - request_est > self.caution * cost:
            self.last_elapsed = elapsed
            return {'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': best}}
        self.last_elapsed = elapsed
        return {'type': 'submit'}


class VirtualClock:
    """Episode clock that advances instantly, so a design check costs no wall time."""

    def __init__(self):
        self.t = 0.0
        self.start = 0.0

    def time(self):
        return self.t

    def elapsed(self):
        return self.t

    def check(self, stamp=None):
        return None

    def suspend_gap(self, stamp=None):
        return 0.0

    async def wait(self, awaitable, deadline):
        return await awaitable


def virtual_sleep(clock):
    async def sleeper(seconds):
        if seconds > 0:
            clock.t += seconds
    return sleeper


async def one_episode(task, regime, arm, seed, caution=1.0):
    collected, durations = {}, []
    policy = make_policy(arm, task, collected, durations)
    sampler = study3.DurationSampler(task, regime, seed)
    items = [item['id'] for item in task['public']['items']]
    agent = ClockDrivenAgent(task, caution=caution)
    clock = VirtualClock()
    result = await run_episode(
        agent, question=data_v7.public_view(task)['question'],
        tool_schemas=data_v7.tool_schemas(),
        call_tool=lambda name, args: data_v7.call_tool(task['public'], name, args),
        verify=lambda _a: data_v7.verify(task['private'], collected),
        delay_sampler=sampler, item_ids=items,
        budget_s=task['public']['budget_s'], policy=policy,
        state_provider=lambda: {'collected_items': data_v7.collected_state(collected, len(items))},
        max_steps=60, clock=clock, sleep_fn=virtual_sleep(clock))
    return result


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks', type=int, default=6)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--caution', type=float, default=1.0)
    parser.add_argument('--budget-mult', type=float, default=1.0)
    parser.add_argument('--sigma', type=float, default=None)
    parser.add_argument('--sweep', action='store_true')
    parser.add_argument('--out', default=str(ROOT / 'reports' / 's3_design_check.json'))
    args = parser.parse_args()
    tasks = [t for t in study3.tasks_for('A') if t['task_id'].endswith(('00', '01', '02', '03', '04', '05'))][:args.tasks * 2]
    tasks = [t for t in study3.tasks_for('A')][:args.tasks * 2]
    if args.budget_mult != 1.0 or args.sigma is not None:
        import copy as _copy
        scaled = []
        for task in tasks:
            t2 = _copy.deepcopy(task)
            t2['public']['budget_s'] = round(task['public']['budget_s'] * args.budget_mult, 1)
            t2['private']['budget_s'] = t2['public']['budget_s']
            if args.sigma is not None:
                t2['private']['sigma'] = args.sigma
            scaled.append(t2)
        tasks = scaled
    if args.sweep:
        print('caution  family  regime        I0     I1      C      E      O   (forced E)')
        for caution in (0.0, 0.25, 0.5, 1.0):
            for family in study3.FAMILIES:
                for regime in study3.REGIMES:
                    cells = {}
                    forced = 0
                    total = 0
                    for task in [t for t in tasks if t['task_family'] == family]:
                        for arm in study3.CONDITIONS:
                            scores = []
                            for repeat in range(args.repeats):
                                seed = hash((task['task_id'], regime, arm, repeat)) & 0xFFFFFFFF
                                result = await one_episode(task, regime, arm, seed, caution)
                                scores.append(result['score'])
                                if arm == 'E':
                                    total += 1
                                    forced += 1 if result['forced_submit'] else 0
                            cells.setdefault(arm, []).extend(scores)
                    means = {arm: round(statistics.mean(values), 1) for arm, values in cells.items()}
                    print(f'{caution:5.2f}  {family:7s} {regime:13s} ' +
                          '  '.join(f'{means[arm]:5.1f}' for arm in study3.CONDITIONS) +
                          f'   {forced / max(1, total):.2f}')
        return
    rows = []
    for task in tasks:
        for regime in study3.REGIMES:
            for arm in study3.CONDITIONS:
                for repeat in range(args.repeats):
                    seed = hash((task['task_id'], regime, arm, repeat)) & 0xFFFFFFFF
                    result = await one_episode(task, regime, arm, seed, args.caution)
                    rows.append({'task': task['task_id'], 'family': task['task_family'],
                                 'regime': regime, 'arm': arm, 'repeat': repeat,
                                 'score': result['score'], 'term': result['termination_reason'],
                                 'forced': result['forced_submit']})
    summary = collections.OrderedDict()
    for family in study3.FAMILIES:
        for regime in study3.REGIMES:
            key = f'{family}|{regime}'
            entry = {}
            for arm in study3.CONDITIONS:
                values = [r['score'] for r in rows if r['family'] == family
                          and r['regime'] == regime and r['arm'] == arm]
                entry[arm] = round(statistics.mean(values), 2) if values else None
            summary[key] = entry
    for family in study3.FAMILIES:
        pooled = {}
        for arm in study3.CONDITIONS:
            values = [r['score'] for r in rows if r['family'] == family and r['arm'] == arm]
            pooled[arm] = round(statistics.mean(values), 2)
        summary[f'{family}|all'] = pooled
    payload = {'n_episodes': len(rows), 'summary': summary,
               'forced_rate': {arm: round(sum(1 for r in rows if r['arm'] == arm and r['forced']) /
                                          max(1, sum(1 for r in rows if r['arm'] == arm)), 3)
                               for arm in study3.CONDITIONS}}
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(__import__('json').dumps(payload, ensure_ascii=False, indent=2) + '\n')
    for key, value in summary.items():
        print(f'{key:22s} ' + '  '.join(f'{arm}={value[arm]:5.2f}' for arm in study3.CONDITIONS))
    print('forced rate', payload['forced_rate'], 'episodes', payload['n_episodes'])


if __name__ == '__main__':
    asyncio.run(main())

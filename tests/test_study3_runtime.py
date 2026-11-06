"""Offline tests for the S3 environment, runner, arms and policies."""
import asyncio
import json
import random
import unittest

from scripts import study3
from src.runner_v4 import run_episode
from src.time_policies import DENY_NO_COMMIT, DENY_NO_TIME, make_policy
from tasks import data_v7

TASK = next(t for t in data_v7.generate('dev') if t['task_family'] == 'hetero')
ITEMS = [item['id'] for item in TASK['public']['items']]


class ScriptedModel:
    def __init__(self, script, delay=0.0):
        self.script = list(script)
        self.delay = delay
        self.observations = []

    async def decide(self, observation, history):
        self.observations.append(observation)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.script:
            return self.script.pop(0)
        return {'type': 'submit'}


def episode(model, arm='I0', *, budget=30.0, regime='light_tail', max_steps=40, draws=None):
    collected, durations = {}, []
    policy = make_policy(arm, TASK, collected, durations)
    queue = list(draws or [0.02])

    def sampler(item_id, elapsed):
        return queue.pop(0) if queue else 0.02

    result = run_episode(
        model, question=data_v7.public_view(TASK)['question'],
        tool_schemas=data_v7.tool_schemas(),
        call_tool=lambda name, args: data_v7.call_tool(TASK['public'], name, args),
        verify=lambda _a: data_v7.verify(TASK['private'], collected),
        delay_sampler=sampler, item_ids=ITEMS, budget_s=budget, policy=policy,
        state_provider=lambda: {'collected_items': data_v7.collected_state(collected, len(ITEMS))},
        max_steps=max_steps)
    return result


class EnvironmentTests(unittest.TestCase):
    def test_two_families_and_public_metadata(self):
        tasks = data_v7.generate('dev')
        families = {t['task_family'] for t in tasks}
        self.assertEqual(families, {'uniform', 'hetero'})
        hetero = [t for t in tasks if t['task_family'] == 'hetero'][0]
        for item in hetero['public']['items']:
            self.assertIn(item['value'], (1, 3, 5))
            self.assertIn(item['size'], 'SML')
        self.assertNotIn('size_means', hetero['public'])
        self.assertNotIn('size_means', hetero['public']['question'])

    def test_sampler_is_heavy_tailed_and_seeded(self):
        task = [t for t in data_v7.generate('dev') if t['task_family'] == 'hetero'][0]
        sampler = study3.DurationSampler(task, 'fast_heavy', 7)
        draws = [sampler('K01', 0.0) for _ in range(200)]
        self.assertGreater(max(draws) / sorted(draws)[len(draws) // 2], 3.0)
        again = [study3.DurationSampler(task, 'fast_heavy', 7)('K01', 0.0) for _ in range(200)]
        self.assertNotEqual([round(x, 6) for x in draws[:3]], [round(x, 6) for x in again[:3]])
        repeat = study3.DurationSampler(task, 'fast_heavy', 7)
        self.assertEqual([round(repeat('K01', 0.0), 6) for _ in range(5)],
                         [round(s, 6) for s in draws[:5]])

    def test_light_tail_is_nearly_deterministic(self):
        task = [t for t in data_v7.generate('dev') if t['task_family'] == 'hetero'][0]
        draws = [study3.DurationSampler(task, 'light_tail', 3)('K01', 0.0) for _ in range(200)]
        self.assertLess(max(draws) / sorted(draws)[len(draws) // 2], 1.5)

    def test_drift_multiplier_grows(self):
        self.assertLess(study3.regime_multiplier('drift_heavy', 0, 100),
                        study3.regime_multiplier('drift_heavy', 100, 100))
        self.assertEqual(study3.regime_multiplier('slow_heavy', 50, 100), 3.0)

    def test_score_is_sum_of_banked_points(self):
        values = TASK['private']['values']
        collected = dict(list(values.items())[:3])
        details = data_v7.verify(TASK['private'], collected)
        self.assertEqual(details['score'], sum(list(values.values())[:3]))
        self.assertEqual(details['banked'], 3)


class PolicyTests(unittest.TestCase):
    def test_only_enforcing_arms_deny(self):
        collected, durations = {}, []
        context = {'remaining': 5.0, 'elapsed': 100.0, 'budget_s': 105.0,
                   'request_estimate_s': 6.0, 'history': [], 'item_ids': ITEMS}
        for arm in ('I0', 'I1'):
            allowed, _ = make_policy(arm, TASK, collected, durations).admit(context, 'K01', 9.0)
            self.assertTrue(allowed)
        for arm in ('E', 'O'):
            allowed, reason = make_policy(arm, TASK, collected, durations).admit(context, 'K01', 9.0)
            self.assertFalse(allowed)
            self.assertEqual(reason, DENY_NO_TIME)

    def test_commit_arm_requires_a_declaration(self):
        policy = make_policy('C', TASK, {}, [])
        context = {'remaining': 100.0, 'elapsed': 0.0, 'budget_s': 100.0,
                   'request_estimate_s': 6.0, 'history': [], 'item_ids': ITEMS}
        allowed, reason = policy.admit(context, 'K01', 9.0)
        self.assertFalse(allowed)
        self.assertEqual(reason, DENY_NO_COMMIT)
        policy.record_commit(20.0)
        allowed, _ = policy.admit(context, 'K01', 9.0)
        self.assertTrue(allowed)

    def test_forced_submit_only_for_enforcing_arms(self):
        context = {'remaining': 1.0, 'elapsed': 0.0, 'budget_s': 30.0, 'request_estimate_s': 6.0,
                   'history': [], 'item_ids': ITEMS}
        for arm in ('I0', 'I1'):
            self.assertFalse(make_policy(arm, TASK, {}, []).force_submit(context))
        self.assertTrue(make_policy('E', TASK, {}, []).force_submit(context))
        policy_c = make_policy('C', TASK, {}, [])
        self.assertFalse(policy_c.force_submit(context))
        policy_c.record_commit(10.0)
        self.assertTrue(policy_c.force_submit(context))

    def test_information_arm_exposes_per_size_estimates(self):
        policy = make_policy('I1', TASK, {}, [('S', 4.0), ('S', 6.0), ('L', 30.0)])
        extra = policy.observe({'remaining': 100, 'request_estimate_s': 6.0})
        self.assertEqual(extra['cost_estimates_by_size']['S']['mean_s'], 5.0)
        self.assertEqual(extra['cost_estimates_by_size']['L']['p90_s'], 30.0)
        self.assertEqual(len(extra['most_efficient_remaining']), 3)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_banking_happens_only_after_a_completed_call(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K01'}},
                               {'type': 'submit'}])
        result = await episode(model)
        self.assertEqual(result['termination_reason'], 'submitted')
        self.assertEqual(result['score'], TASK['private']['values']['K01'])

    async def test_censored_call_scores_zero(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K02'}}] * 6)
        result = await episode(model, budget=0.12, draws=[0.5] * 6, max_steps=6)
        self.assertNotEqual(result['termination_reason'], 'submitted')
        self.assertEqual(result['score'], 0)

    async def test_enforcing_arm_forces_a_submission(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch',
                                'arguments': {'item_id': ITEMS[i % len(ITEMS)]}} for i in range(60)])
        result = await episode(model, arm='E', budget=60.0, draws=[2.0] * 60)
        self.assertTrue(result['forced_submit'])
        self.assertEqual(result['termination_reason'], 'forced_submit')
        self.assertGreater(result['score'], 0)

    async def test_denied_fetch_does_not_consume_time(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K01'}},
                               {'type': 'submit'}])
        result = await episode(model, arm='E', budget=60.0, draws=[0.05, 0.05])
        self.assertEqual(result['denied_fetches'], 0)  # plenty of time at the start
        self.assertEqual(result['termination_reason'], 'submitted')

    async def test_commit_is_recorded_in_arm_c(self):
        model = ScriptedModel([{'type': 'commit', 'reserve_s': 5},
                               {'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K01'}},
                               {'type': 'submit'}])
        result = await episode(model, arm='C', budget=60.0, draws=[0.05] * 3)
        self.assertEqual(result['commit'], 5.0)
        self.assertEqual(result['termination_reason'], 'submitted')

    async def test_observation_carries_collected_state_in_every_arm(self):
        for arm in ('I0', 'I1', 'C', 'E', 'O'):
            model = ScriptedModel([{'type': 'submit'}])
            await episode(model, arm=arm)
            self.assertIn('collected_items', model.observations[0])
            self.assertIn('remaining_s', model.observations[0]['time_status'])


class ManifestTests(unittest.TestCase):
    def test_balanced_arms_and_blocks(self):
        tasks = study3.tasks_for('A')
        manifest = study3.build_manifest(tasks, list(study3.MODELS))
        self.assertEqual(len(manifest), 7040)
        blocks = {}
        for entry in manifest:
            blocks.setdefault((entry['model_id'], entry['block_id']), []).append(entry)
        self.assertEqual(len(blocks), len(study3.MODELS) * len(tasks) * len(study3.REGIMES))
        for entries in blocks.values():
            model = entries[0]['model_id']
            self.assertEqual(len(entries), 5 * study3.REPEATS[model])
        positions = {arm: set() for arm in study3.CONDITIONS}
        for entries in blocks.values():
            for entry in entries:
                positions[entry['condition']].add(entry['position'])
        self.assertTrue(all(values == {0, 1, 2, 3, 4} for values in positions.values()))


if __name__ == '__main__':
    unittest.main()

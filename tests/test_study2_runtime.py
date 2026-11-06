"""Offline tests for the S2 environment, runner and condition ladder.

These tests use scripted fake models and very short budgets, so they cost no API
calls. They pin the properties the design depends on: host-scored partial credit,
zero for a missed deadline, one and only one information difference between
conditions, and an oracle that equals the delay actually applied.
"""
import asyncio
import unittest

from src.conditions_v3 import duration_references, target_delay
from src.runner_v3 import run_episode
from tasks import data_v6

TASK = data_v6.generate('dev')[0]
SCHEMAS = data_v6.tool_schemas()
CAL = {'fetch': [0.02, 0.02, 0.02]}


class ScriptedModel:
    """Emits a fixed action list, then submits."""

    def __init__(self, script, *, submit_after=None, delay=0.0):
        self.script = list(script)
        self.submit_after = submit_after
        self.delay = delay
        self.observations = []

    async def decide(self, observation, history):
        self.observations.append(observation)
        if self.delay:
            await asyncio.sleep(self.delay)
        state = observation.get('collected_items') or {}
        if self.submit_after is not None and state.get('count', 0) >= self.submit_after:
            return {'type': 'submit'}
        if self.script:
            return self.script.pop(0)
        return {'type': 'submit'}


def make_episode(model, **kwargs):
    collected = {}

    def call_tool(name, args):
        result = data_v6.call_tool(TASK['public'], name, args)
        if isinstance(result, dict) and 'item_id' in result:
            collected.setdefault(result['item_id'], result['value'])
        return result

    options = dict(question=data_v6.public_view(TASK)['question'], tool_schemas=SCHEMAS,
                   calibration=CAL, call_tool=call_tool,
                   verify=lambda _answer: data_v6.verify(TASK['private'], collected),
                   validate_submission=data_v6.validate_submission,
                   state_provider=lambda: {'collected_items': data_v6.collected_state(collected)},
                   condition='A', profile='stable_fast', budget_s=0.9,
                   shift_fraction=.4, fast_s=.02, slow_s=.05, max_steps=30)
    options.update(kwargs)
    return run_episode(model, **options)


class EnvironmentTests(unittest.TestCase):
    def test_values_are_opaque_and_tool_is_single_item(self):
        self.assertEqual(len(TASK['public']['item_ids']), data_v6.ITEM_COUNT)
        result = data_v6.call_tool(TASK['public'], 'fetch', {'item_id': 'K01'})
        self.assertEqual(set(result), {'item_id', 'value'})
        self.assertNotIn('values', data_v6.public_view(TASK))
        self.assertNotIn('values', TASK['public']['question'])

    def test_tool_rejects_unknown_and_malformed(self):
        def call(args, name='fetch'):
            return data_v6.call_tool(TASK['public'], name, args)
        self.assertIn('error', call({'item_id': 'K99'}))
        self.assertIn('error', call({'item_id': 3}))
        self.assertIn('error', call({'item_id': 'K01'}, name='other'))

    def test_host_side_score_counts_distinct_correct_items(self):
        values = TASK['private']['values']
        collected = {'K01': values['K01'], 'K02': values['K02'], 'K03': 1}
        details = data_v6.verify(TASK['private'], collected)
        self.assertEqual((details['score'], details['total'], details['wrong']), (2, 20, 1))
        self.assertFalse(details['correct'])
        self.assertEqual(data_v6.verify(TASK['private'], {})['score'], 0)

    def test_question_states_the_zero_for_missing_deadline_rule(self):
        question = TASK['public']['question']
        self.assertIn('0 分', question)
        self.assertIn('submit', question)

    def test_collected_state_is_bounded(self):
        state = data_v6.collected_state({'K02': 5, 'K01': 4})
        self.assertEqual(state['count'], 2)
        self.assertEqual(state['remaining_items'], data_v6.ITEM_COUNT - 2)
        self.assertEqual(list(state['items']), ['K01', 'K02'])


class ConditionTests(unittest.TestCase):
    def test_ladder_differs_only_in_the_reference(self):
        completed = {'fetch': [5.0, 6.0, 7.0]}
        self.assertEqual(duration_references('A', CAL, completed), (None, {}))
        self.assertEqual(duration_references('B', CAL, completed)[0]['fetch'], 0.02)
        self.assertEqual(duration_references('C', CAL, completed)[0]['fetch'], 7.0)
        self.assertEqual(duration_references('C', CAL, completed, window=3)[0]['fetch'], 6.0)
        self.assertEqual(duration_references('O', CAL, completed, oracle={'fetch': 9.0})[0]['fetch'], 9.0)
        self.assertEqual(duration_references('C', CAL, {})[0]['fetch'], 0.02)
        with self.assertRaises(ValueError):
            duration_references('O', CAL, completed, oracle=None)

    def test_profiles(self):
        self.assertEqual(target_delay('stable_fast', 0, 100, .4, 1.5, 12), 1.5)
        self.assertEqual(target_delay('fast_to_slow', 10, 100, .4, 1.5, 12), 1.5)
        self.assertEqual(target_delay('fast_to_slow', 50, 100, .4, 1.5, 12), 12)
        self.assertEqual(target_delay('slow_to_fast', 10, 100, .4, 1.5, 12), 12)
        self.assertEqual(target_delay('slow_to_fast', 50, 100, .4, 1.5, 12), 1.5)


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_scored_partial_credit_on_timely_submission(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': f'K0{i}'}}
                               for i in (1, 2, 3)], submit_after=3)
        result = await make_episode(model)
        self.assertEqual(result['termination_reason'], 'submitted')
        self.assertEqual(result['score'], 3)
        self.assertTrue(result['valid_submission'])
        self.assertFalse(result['deadline_success'])
        self.assertLess(result['elapsed_s'], 0.9)

    async def test_a_late_submission_does_not_score(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K01'}}] * 8,
                              submit_after=99)
        result = await make_episode(model, budget_s=0.3, fast_s=.05, slow_s=.05)
        self.assertNotEqual(result['termination_reason'], 'submitted')
        self.assertEqual(result['score'], 0)

    async def test_oracle_equals_applied_delay(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K01'}},
                               {'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K02'}}])
        result = await make_episode(model, condition='O', profile='fast_to_slow',
                                    budget_s=1.2, shift_fraction=.4, fast_s=.02, slow_s=.08)
        tools = [e for e in result['events'] if e.get('event_type') == 'tool']
        self.assertTrue(tools)
        self.assertAlmostEqual(tools[0]['injected_target_s'], .02, places=6)
        self.assertEqual(tools[0]['reference_at_request_s'], .02)
        oracle_values = {e['observation']['duration_reference_s']['fetch']
                         for e in result['events'] if e.get('event_type') == 'model_request'}
        self.assertTrue(oracle_values <= {.02, .08})

    async def test_condition_a_hides_the_reference(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K01'}}])
        result = await make_episode(model, condition='A')
        for event in result['events']:
            if event.get('event_type') == 'model_request':
                self.assertNotIn('duration_reference_s', event['observation'])
                self.assertIn('remaining_s', event['observation']['time_status'])
                self.assertIn('collected_items', event['observation'])

    async def test_b_and_c_show_different_numbers_after_a_shift(self):
        script = [{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': f'K0{i}'}} for i in (1, 2)]
        seen = {}
        for condition in ('B', 'C'):
            # A 30 ms thinking delay keeps the third request after the phase shift,
            # so the adaptive estimate has one slow call to average over.
            model = ScriptedModel(list(script), submit_after=2, delay=0.03)
            result = await make_episode(model, condition=condition, profile='fast_to_slow',
                                        budget_s=1.0, shift_fraction=.05, fast_s=.02, slow_s=.2)
            seen[condition] = [e['observation'].get('duration_reference_s', {}).get('fetch')
                               for e in result['events'] if e.get('event_type') == 'model_request']
        self.assertTrue(all(v == .02 for v in seen['B']))
        self.assertTrue(any(v > .02 for v in seen['C']))

    async def test_collected_state_grows_with_each_fetch(self):
        model = ScriptedModel([{'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K01'}},
                               {'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': 'K01'}}],
                              submit_after=9)
        result = await make_episode(model, budget_s=0.6)
        counts = [e['observation']['collected_items']['count']
                  for e in result['events'] if e.get('event_type') == 'model_request']
        self.assertEqual(counts[:3], [0, 1, 1])  # a repeated fetch earns nothing new
        self.assertEqual(result['score'], 1)


if __name__ == '__main__':
    unittest.main()

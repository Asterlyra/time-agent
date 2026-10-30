import asyncio
import time
import unittest
from src.conditions import duration_references, target_delay
from src.runner import run_episode
from src.protocol import ProtocolViolation


class ScriptModel:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.seen = []
    async def decide(self, observation, history):
        self.seen.append((observation, history))
        action = next(self.actions)
        if action == 'sleep':
            await asyncio.sleep(1)
        return action


class Tests(unittest.IsolatedAsyncioTestCase):
    def test_references_and_shift(self):
        c = {'search': [1, 2, 3]}
        completed = {'search': [4, 5, 6, 7]}
        self.assertIsNone(duration_references('A', c, completed)[0])
        self.assertEqual(duration_references('B', c, completed)[0]['search'], 2)
        self.assertEqual(duration_references('C', c, completed)[0]['search'], 6)
        self.assertEqual(duration_references('C', c, {})[0]['search'], 2)
        self.assertEqual(target_delay('fast_to_slow', 49, 100, .5, 2, 15), 2)
        self.assertEqual(target_delay('fast_to_slow', 50, 100, .5, 2, 15), 15)
        self.assertEqual(target_delay('slow_to_fast', 50, 100, .5, 2, 15), 2)

    async def run_case(self, model, **kwargs):
        opts = dict(question='Q', tool_schemas={'search': {'description': 'query'}},
                    calibration={'search': [.01, .01, .01]},
                    call_tool=lambda name, args: {'text': 'fact'},
                    verify=lambda answer: {'correct': answer['value'] == 1},
                    budget_s=.2, fast_s=.01, slow_s=.03)
        opts.update(kwargs)
        return await run_episode(model, **opts)

    async def test_success_and_dynamic_feedback(self):
        m = ScriptModel([{'type':'tool','name':'search','arguments':{}},
                         {'type':'submit','answer':{'value':1,'evidence_ids':['d1']}}])
        result = await self.run_case(m, condition='C')
        self.assertTrue(result['deadline_success'])
        self.assertGreaterEqual(m.seen[1][0]['duration_reference_s']['search'], .009)
        self.assertEqual(len(m.seen[1][1]), 1)

    async def test_wrong_and_invalid_submission(self):
        m = ScriptModel([{'type':'submit','answer':{}},
                         {'type':'submit','answer':{'value':2,'evidence_ids':[]}}])
        r = await self.run_case(m)
        self.assertFalse(r['deadline_success'])
        self.assertTrue(r['valid_submission'])
        self.assertEqual(r['termination_reason'], 'submitted')
        self.assertEqual(r['events'][1]['event_type'], 'invalid_action')

    async def test_timeout_and_censored_tool(self):
        r = await self.run_case(ScriptModel(['sleep']), budget_s=.02)
        self.assertEqual(r['termination_reason'], 'timeout_model')
        r = await self.run_case(ScriptModel([{'type':'tool','name':'search','arguments':{}}]),
                                budget_s=.02, fast_s=.1)
        self.assertEqual(r['termination_reason'], 'timeout_tool')
        self.assertTrue(r['events'][-1]['is_censored'])
        self.assertNotIn('observed_duration_s', r['events'][-1])

    async def test_invalid_tool_excluded(self):
        m = ScriptModel([{'type':'tool','name':'search','arguments':{}},
                         {'type':'submit','answer':{'value':1,'evidence_ids':[]}}])
        await self.run_case(m, condition='C', call_tool=lambda n,a: {'error':'bad'})
        self.assertEqual(m.seen[1][0]['duration_reference_s']['search'], .01)

    async def test_protocol_violation_is_not_service_error(self):
        class ViolatingModel:
            async def decide(self, observation, history):
                raise ProtocolViolation('forbidden tool')
        result = await self.run_case(ViolatingModel())
        self.assertEqual(result['termination_reason'], 'protocol_violation')
        self.assertEqual(result['service_error_flags'], [])

    async def test_malformed_text_is_fed_back_as_invalid_action(self):
        m = ScriptModel(['not JSON', {'type':'submit','answer':{'value':1,'evidence_ids':[]}}])
        result = await self.run_case(m)
        self.assertTrue(result['deadline_success'])
        self.assertEqual(m.seen[1][1][0]['error'], 'Invalid action or tool arguments.')

    async def test_event_sink_retains_started_and_finished_steps(self):
        journal = []
        m = ScriptModel([{'type':'tool','name':'search','arguments':{}},
                         {'type':'submit','answer':{'value':1,'evidence_ids':[]}}])
        await self.run_case(m, event_sink=journal.append)
        kinds = [x['kind'] for x in journal]
        self.assertEqual(kinds.count('model_request_started'), 2)
        self.assertIn('tool_started', kinds)
        self.assertIn('tool_ended', kinds)
        self.assertEqual(kinds[-1], 'episode_finished')
        self.assertTrue(journal[-1]['data']['deadline_success'])

    async def test_submission_arrival_precedes_slow_logging(self):
        def sink(event):
            if event['kind'] == 'model_request_ended': time.sleep(.04)
        result = await self.run_case(ScriptModel([{'type':'submit','answer':{'value':1,'evidence_ids':[]}}]),
                                     budget_s=.02, event_sink=sink)
        self.assertTrue(result['deadline_success'])

    async def test_tool_phase_sampled_after_start_logging(self):
        def sink(event):
            if event['kind'] == 'tool_started': time.sleep(.11)
        m = ScriptModel([{'type':'tool','name':'search','arguments':{}},
                         {'type':'submit','answer':{'value':1,'evidence_ids':[]}}])
        result = await self.run_case(m, budget_s=.2, fast_s=.001, slow_s=.01,
                                     profile='fast_to_slow', event_sink=sink)
        tool = next(x for x in result['events'] if x['event_type'] == 'tool')
        self.assertEqual(tool['injected_target_s'], .01)

if __name__ == '__main__':
    unittest.main()

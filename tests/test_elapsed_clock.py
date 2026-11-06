import asyncio
import time
import unittest
from unittest.mock import patch

from src import elapsed_clock
from src.runner_v2 import run_episode


SUBMIT = {'type': 'submit', 'answer': {'value': 1, 'evidence_ids': []}}
TOOL = {'type': 'tool', 'name': 'search', 'arguments': {}}


class ClockTests(unittest.IsolatedAsyncioTestCase):
    async def episode(self, decide, **options):
        class Model:
            async def decide(self, observation, history):
                return await decide()
        settings = dict(question='q', tool_schemas={'search': {}},
                        calibration={'search': [.01]*3}, call_tool=lambda n,a: {},
                        verify=lambda a: True, budget_s=30)
        settings.update(options)
        return await run_episode(Model(), **settings)

    def test_real_clock_and_fail_closed_platform(self):
        meta = elapsed_clock.clock_metadata()
        self.assertTrue(meta['includes_suspend'])
        self.assertGreater(meta['resolution_s'], 0)
        self.assertGreaterEqual(elapsed_clock.elapsed_time(), 0)
        with self.assertRaises(RuntimeError):
            elapsed_clock.clock_id('unsupported')

    async def test_sleep_gap_rejects_even_with_budget_remaining(self):
        offset = [0]
        async def decide():
            await asyncio.sleep(.002)
            offset[0] += 10
            return SUBMIT
        with patch.object(elapsed_clock, 'elapsed_time', lambda: time.monotonic()+offset[0]):
            result = await self.episode(decide)
        self.assertEqual(result['termination_reason'], 'environment_interruption')
        self.assertFalse(result['valid_submission'])
        self.assertEqual(result['service_error_flags'], [])
        self.assertEqual(result['infrastructure_error_flags'][0]['type'], 'host_suspend')
        self.assertGreater(result['suspend_gap_s'], 9)

    async def test_hanging_call_cancelled_after_continuous_clock_jump(self):
        offset = [0]
        cancelled = []
        async def decide():
            asyncio.get_running_loop().call_later(.005, lambda: offset.__setitem__(0, 100))
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        start = time.monotonic()
        with patch.object(elapsed_clock, 'elapsed_time', lambda: time.monotonic()+offset[0]):
            result = await self.episode(decide)
        self.assertLess(time.monotonic()-start, 1)
        self.assertEqual(result['termination_reason'], 'environment_interruption')
        self.assertEqual(cancelled, [True])

    async def test_late_completion_is_not_accepted_when_loop_timer_was_blocked(self):
        async def decide():
            time.sleep(.025)
            return SUBMIT
        result = await self.episode(decide, budget_s=.01)
        self.assertEqual(result['termination_reason'], 'timeout_model')
        self.assertFalse(result['deadline_success'])

    async def test_post_arrival_logging_does_not_invalidate_timely_submission(self):
        async def decide():
            return SUBMIT
        def sink(event):
            if event['kind'] == 'model_request_ended':
                time.sleep(.04)
        result = await self.episode(decide, budget_s=.02, event_sink=sink)
        self.assertTrue(result['deadline_success'])
        self.assertEqual(result['termination_reason'], 'submitted')
        self.assertGreater(result['elapsed_s'], result['budget_s'])

    async def test_no_tool_started_after_sleep_during_journaling(self):
        offset = [0]; calls = []
        async def decide():
            return TOOL
        def sink(event):
            if event['kind'] == 'tool_started':
                offset[0] += 10
        with patch.object(elapsed_clock, 'elapsed_time', lambda: time.monotonic()+offset[0]):
            result = await self.episode(decide, event_sink=sink, call_tool=lambda n,a: calls.append(n))
        self.assertEqual(calls, [])
        self.assertEqual(result['termination_reason'], 'environment_interruption')

    async def test_sleep_during_tool_does_not_become_a_duration_sample(self):
        offset = [0]
        async def decide():
            return TOOL
        def call_tool(name, arguments):
            offset[0] += 10
            return {'results': []}
        with patch.object(elapsed_clock, 'elapsed_time', lambda: time.monotonic()+offset[0]):
            result = await self.episode(decide, call_tool=call_tool)
        self.assertEqual(result['termination_reason'], 'environment_interruption')
        tool = next(e for e in result['events'] if e['event_type'] == 'tool')
        self.assertTrue(tool['is_censored'])
        self.assertNotIn('observed_duration_s', tool)

    async def test_calibration_rejects_suspend(self):
        from src.calibration import calibrate
        offset = [0]
        def call_tool(*args):
            offset[0] += 10
            return {}
        with patch.object(elapsed_clock, 'elapsed_time', lambda: time.monotonic()+offset[0]):
            with self.assertRaises(elapsed_clock.EnvironmentInterruption):
                await calibrate(['search'], .01, tool_call=call_tool)


if __name__ == '__main__':
    unittest.main()

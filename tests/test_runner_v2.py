import asyncio
import unittest
from src.runner_v2 import run_episode


class RunnerDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def run_mode(self, mode):
        class FakeModel:
            last_event_types = ['error']
            last_diagnostics = None
            async def decide(self, observation, history):
                try:
                    if mode == 'timeout': await asyncio.sleep(1)
                    if mode == 'error': raise RuntimeError('private')
                    return {'type': 'submit', 'answer': {'value': 1, 'evidence_ids': []}}
                finally:
                    self.last_diagnostics = {'event_types': ['error'], 'error_count': 1,
                        'message_offset_s': .001, 'request_started_monotonic': 123,
                        'secret': 'not allowed'}
        journal = []
        result = await run_episode(FakeModel(), question='q', tool_schemas={'search': {}},
            calibration={'search': [.01]*3}, call_tool=lambda n,a: {}, verify=lambda a: True,
            budget_s=.04, event_sink=journal.append)
        event = result['events'][0]['attempts'][0]
        diag = event['adapter_diagnostics']
        self.assertEqual(diag['error_count'], 1)
        self.assertNotIn('secret', diag)
        self.assertNotIn('request_started_monotonic', diag)
        persisted = next(e for e in journal if e['kind'] == 'model_request_ended')
        self.assertEqual(persisted['data']['attempts'][0]['adapter_diagnostics'], diag)
        return result

    async def test_success(self):
        self.assertTrue((await self.run_mode('success'))['deadline_success'])

    async def test_error(self):
        self.assertEqual((await self.run_mode('error'))['termination_reason'], 'service_error')

    async def test_timeout(self):
        self.assertEqual((await self.run_mode('timeout'))['termination_reason'], 'timeout_model')

if __name__ == '__main__': unittest.main()

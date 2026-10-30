import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from src.adapters.codex_events_v2 import CLIServiceError
from src.adapters.codex_mxc_v2 import CodexMXCV2, minimal_environment
from src.protocol import ProtocolViolation


class FakeInput:
    def write(self, value): self.value = value
    async def drain(self): pass
    def close(self): pass


class FakeOutput:
    def __init__(self, events, delay=False): self.events, self.delay = events, delay
    async def __aiter__(self):
        for e in self.events:
            yield (json.dumps(e) + '\n').encode()
        if self.delay: await asyncio.sleep(1)


class FakeProcess:
    def __init__(self, events, delay=False):
        self.stdin, self.stdout = FakeInput(), FakeOutput(events, delay)
        self.returncode = None
    async def wait(self):
        self.returncode = 0
        return 0


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self, process):
        async def factory(*args, **kwargs): return process
        return CodexMXCV2(executable='fake', denied_roots=[str(Path.cwd())], process_factory=factory)

    def test_environment_does_not_pass_secrets(self):
        env = minimal_environment({'SystemRoot': 'sys', 'SystemDrive': 'drive', 'OPENAI_API_KEY': 'secret',
                                   'CODEX_APP_TOOLS_PIPE_PATH': 'pipe', 'PATH': 'bin'})
        self.assertEqual(env, {'SystemRoot': 'sys', 'SystemDrive': 'drive', 'PATH': 'bin'})

    async def test_waits_for_audited_eof_and_cleanup(self):
        proc = FakeProcess([{'type':'item.completed', 'item':{'type':'agent_message','text':'{"type":"submit"}'}},
                            {'type':'turn.completed'}])
        m = self.adapter(proc)
        stopped = []
        async def stop(p):
            await asyncio.sleep(.05)
            stopped.append(p)
        with patch('src.adapters.codex_mxc_v2._stop_process', stop):
            result = await asyncio.wait_for(m.decide({}, []), .3)
            self.assertEqual(result, {'type':'submit'})
            self.assertTrue(m.last_diagnostics['tail_events_audited'])
            self.assertIsNotNone(m.last_diagnostics['turn_completed_offset_s'])
        self.assertEqual(stopped, [proc])

    async def test_terminal_error_saved_as_service_error(self):
        proc = FakeProcess([{'type':'item.completed','item':{'type':'error','status_code':503,'message':'secret'}}])
        m = self.adapter(proc)
        async def stop(p): pass
        with patch('src.adapters.codex_mxc_v2._stop_process', stop):
            with self.assertRaises(CLIServiceError): await m.decide({}, [])
            await m.close()
        self.assertEqual(m.last_diagnostics['status_codes'], [503])
        self.assertNotIn('secret', repr(m.last_diagnostics))

    async def test_timeout_retains_partial_diagnostics(self):
        proc = FakeProcess([{'type':'error','error':{'status_code':429}}], delay=True)
        m = self.adapter(proc)
        async def stop(p): pass
        with patch('src.adapters.codex_mxc_v2._stop_process', stop):
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(m.decide({}, []), .01)
            await m.close()
        self.assertEqual(m.last_diagnostics['status_codes'], [429])
        self.assertIsNone(m.last_diagnostics['turn_completed_offset_s'])

    async def test_post_terminal_tool_attempt_is_rejected(self):
        proc = FakeProcess([{'type':'item.completed','item':{'type':'agent_message','text':'{}'}},
                            {'type':'turn.completed'},
                            {'type':'item.started','item':{'type':'mcp_tool_call'}}])
        m = self.adapter(proc)
        stopped = []
        async def stop(p): stopped.append(p)
        with patch('src.adapters.codex_mxc_v2._stop_process', stop):
            with self.assertRaises(ProtocolViolation): await m.decide({}, [])
        self.assertFalse(m.last_diagnostics['tail_events_audited'])
        self.assertEqual(stopped, [proc])

    async def test_terminal_before_deadline_but_eof_late_is_ambiguous(self):
        proc = FakeProcess([{'type':'item.completed','item':{'type':'agent_message','text':'{}'}},
                            {'type':'turn.completed'}], delay=True)
        m = self.adapter(proc)
        stopped = []
        async def stop(p):
            await asyncio.sleep(.02)
            stopped.append(p)
        with patch('src.adapters.codex_mxc_v2._stop_process', stop):
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(m.decide({}, []), .01)
        self.assertIsNotNone(m.last_diagnostics['message_offset_s'])
        self.assertIsNotNone(m.last_diagnostics['turn_completed_offset_s'])
        self.assertFalse(m.last_diagnostics['tail_events_audited'])
        self.assertEqual(stopped, [proc])

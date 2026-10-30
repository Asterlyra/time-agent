import asyncio
import json
import unittest
from src.adapters.codex_events_v2 import EventTracker, CLIServiceError, consume_events
from src.protocol import ProtocolViolation


class EventTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_turn_stops_before_delayed_eof(self):
        times = iter([101.0, 102.0])
        tracker = EventTracker(request_started=100, clock=lambda: next(times))
        async def stream():
            yield json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'{"type":"submit"}'}})
            yield json.dumps({'type':'turn.completed'})
            await asyncio.sleep(1)
        action = await asyncio.wait_for(consume_events(stream(), tracker), .1)
        self.assertEqual(action, {'type':'submit'})
        self.assertEqual(tracker.message_offset_s, 1)
        self.assertEqual(tracker.turn_completed_offset_s, 2)

    async def test_intermediate_error_diagnostic_and_success(self):
        tracker = EventTracker()
        tracker.feed({'type':'error','error':{'status_code':429,'message':'secret'}})
        tracker.feed({'type':'item.completed','item':{'type':'agent_message','text':'{}'}})
        self.assertEqual(tracker.feed({'type':'turn.completed'}), {})
        self.assertEqual(tracker.metadata()['status_codes'], [429])
        self.assertNotIn('secret', repr(tracker.metadata()))

    async def test_terminal_error_is_service_not_tool_breach(self):
        tracker = EventTracker()
        with self.assertRaises(CLIServiceError) as cm:
            tracker.feed({'type':'item.completed','item':{'type':'error','status_code':503,'message':'secret'}})
        self.assertEqual(cm.exception.status_code, 503)
        self.assertNotIn('secret', repr(tracker.metadata()))

    async def test_tool_breach_and_unknown_item_are_rejected(self):
        for item in ('mcp_tool_call', 'command_execution', 'future_tool'):
            with self.subTest(item=item), self.assertRaises(ProtocolViolation):
                EventTracker().feed({'type':'item.started','item':{'type':item}})

    async def test_candidate_is_not_a_completed_decision(self):
        tracker = EventTracker()
        tracker.feed({'type':'item.completed','item':{'type':'agent_message','text':'{}'}})
        self.assertFalse(tracker.completed)
        self.assertIsNone(tracker.turn_completed_offset_s)

    async def test_eof_without_turn_is_service_error(self):
        async def stream():
            yield '{"type":"turn.started"}'
        with self.assertRaises(CLIServiceError):
            await consume_events(stream(), EventTracker())

    async def test_cancel_keeps_error_and_candidate_timing(self):
        tracker = EventTracker()
        async def stream():
            yield '{"type":"error","error":{"status_code":429}}'
            yield '{"type":"item.completed","item":{"type":"agent_message","text":"{}"}}'
            await asyncio.sleep(1)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(consume_events(stream(), tracker), .01)
        self.assertEqual(tracker.metadata()['status_codes'], [429])
        self.assertIsNotNone(tracker.message_offset_s)
        self.assertIsNone(tracker.turn_completed_offset_s)

if __name__ == '__main__': unittest.main()

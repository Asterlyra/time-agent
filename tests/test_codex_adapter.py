import unittest
from unittest.mock import patch
from src.adapters.codex_cli import _check_event, _child_environment, ProtocolViolation
from src.adapters.codex_mxc import CodexMXC
from pathlib import Path
import os


class CodexEventTests(unittest.TestCase):
    def test_message_only_on_completion(self):
        item = {"type": "agent_message", "text": "{}"}
        self.assertIsNone(_check_event({"type": "item.started", "item": item}))
        self.assertEqual(_check_event({"type": "item.completed", "item": item}), "{}")

    def test_tool_events_are_rejected(self):
        for kind in ("command_execution", "mcp_tool_call", "file_change", "web_search", "future_unknown"):
            with self.subTest(kind=kind), self.assertRaises(ProtocolViolation):
                _check_event({"type": "item.started", "item": {"type": kind}})

    def test_reasoning_not_saved(self):
        self.assertIsNone(_check_event({"type": "item.completed", "item": {"type": "reasoning", "text": "private"}}))

    def test_desktop_tool_pipe_not_inherited(self):
        with patch.dict('os.environ', {'CODEX_APP_TOOLS_PIPE_PATH': 'dummy', 'CODEX_THREAD_ID': 'dummy'}):
            env = _child_environment()
            self.assertNotIn('CODEX_APP_TOOLS_PIPE_PATH', env)
            self.assertNotIn('CODEX_THREAD_ID', env)

    @unittest.skipUnless(os.name == 'nt', 'MXC is Windows-only')
    def test_mxc_profile_and_rejected_working_root(self):
        denied = str(Path.cwd())
        model = CodexMXC(executable='dummy', denied_roots=[denied])
        with self.assertRaisesRegex(Exception, 'inside a denied root'):
            model._sandbox_args(denied)
        args = model._sandbox_args(str(Path(denied).anchor))
        self.assertIn('windows.sandbox="mxc"', args)
        self.assertIn('default_permissions="experiment"', args)
        self.assertIn('"deny"', args[-1])


if __name__ == "__main__":
    unittest.main()

"""Candidate CLI adapter requiring a terminal event and audited EOF.

Not approved for formal experiments: turn.completed semantics, tail-event audit,
end-to-end filesystem/network isolation require validation.
"""
import asyncio
import json
import os
import tempfile
import time

from src.adapters.codex_events_v2 import EventTracker, CLIServiceError, consume_audited_events
from src.adapters.codex_mxc import CodexMXC, _DISABLED_FEATURES, _stop_process


def minimal_environment(source=None):
    """Pass only OS paths required to launch a process; never pass API key variables."""
    source = os.environ if source is None else source
    permitted = {'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'PATH',
                 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA'}
    return {k: v for k, v in source.items() if k.upper() in permitted}


class CodexMXCV2(CodexMXC):
    """Compatible async decide(); diagnostics must be saved even on timeout.

    Completion requires turn.completed, audited EOF and a successful CLI exit.
    A candidate message arriving before a deadline without these confirmations
    is ambiguous; diagnostics retain timestamps and do not count it as success.
    """
    def __init__(self, *args, process_factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.process_factory = process_factory or asyncio.create_subprocess_exec
        self.last_diagnostics = None
    async def close(self):
        pass  # Each decision waits for its own process tree to be reaped.

    async def decide(self, observation, history):
        prompt = (
            'You are participating in a local decision experiment. Return exactly one '
            'JSON object as your final response. Do not use any Codex tools, shell, '
            'files, network, or other resources. Choose either '
            '{"type":"tool","name":"...","arguments":{...}} or '
            '{"type":"submit","answer":{...}}. '
            'Only the experiment tools described in the observation may be requested '
            'through the JSON action; never execute them yourself.\n'
            + json.dumps({'observation': observation, 'history': history}, ensure_ascii=False)
        )
        self.last_event_types = []
        self.last_diagnostics = None
        temporary = tempfile.TemporaryDirectory(prefix='codex-time-pilot-')
        root = temporary.name
        try:
            proc = await self.process_factory(
                self.executable, 'exec', '--model', self.model, *self._sandbox_args(root),
                '--skip-git-repo-check', '--ephemeral', '--ignore-user-config',
                *[arg for feature in _DISABLED_FEATURES for arg in ('--disable', feature)],
                '-c', 'web_search="disabled"', '--json', '--cd', root, '-',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=minimal_environment(),
                start_new_session=(os.name != 'nt'))
        except BaseException:
            temporary.cleanup()
            raise
        tracker = EventTracker(request_started=time.monotonic())
        audited = False
        try:
            proc.stdin.write(prompt.encode('utf-8'))
            await proc.stdin.drain()
            proc.stdin.close()
            action = await consume_audited_events(proc.stdout, tracker)
            audited = True
            code = await proc.wait()
            if code != 0:
                raise CLIServiceError()
            return action
        finally:
            self.last_diagnostics = tracker.metadata()
            self.last_event_types = list(tracker.event_types)
            self.last_diagnostics['request_started_monotonic'] = tracker.request_started
            self.last_diagnostics['tail_events_audited'] = audited
            self.last_diagnostics['completion_semantics'] = 'terminal_turn_audited_eof_and_successful_cli_exit'
            async def cleanup_process():
                try:
                    await _stop_process(proc)
                finally:
                    temporary.cleanup()
            cleanup = asyncio.create_task(cleanup_process())
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                # A repeated cancellation must not abandon the process tree.
                await asyncio.shield(cleanup)
                raise

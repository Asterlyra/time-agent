"""Codex CLI action adapter for *development pilots*, not an isolated model API.

Codex is an agent harness, not a bare model. The read-only sandbox does not
prevent reads outside the empty working directory. A tool attempt invalidates
the decision, but detection is not preventive. Do not use this adapter for a
formal run until an independently enforced filesystem/network isolation exists.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import tempfile
from pathlib import Path
from src.protocol import ProtocolViolation


class CodexError(RuntimeError):
    """CLI failed; stderr is deliberately not copied into logs."""


# Only these item types are accepted. Do not silently trust newly added CLI tools.
_ALLOWED_ITEMS = {"agent_message", "reasoning"}

# Reduce available CLI tools, but this is not an OS isolation guarantee.
_DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "plugins", "apps", "browser_use",
    "browser_use_external", "computer_use", "in_app_browser",
    "image_generation", "multi_agent", "tool_search", "hooks", "plugin_hooks",
)


def _child_environment():
    # The desktop can inject its own MCP tools via this inherited pipe. Do not
    # forward the calling task's control channel into the experiment process.
    return {k: v for k, v in os.environ.items()
            if k.upper() not in {"CODEX_APP_TOOLS_PIPE_PATH", "CODEX_THREAD_ID",
                                 "CODEX_TOOL_CALL_ID", "CODEX_SESSION_ID"}}


def _check_event(event: dict) -> str | None:
    item = event.get("item")
    if isinstance(item, dict):
        kind = item.get("type")
        if kind not in _ALLOWED_ITEMS:
            raise ProtocolViolation(f"Forbidden Codex item type: {kind!r}")
        if kind == "agent_message" and event.get("type") == "item.completed":
            return item.get("text")
    return None


async def _stop_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if os.name == "nt":
        # codex may have spawned descendants. taskkill is invoked without shell.
        killer = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(proc.pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await killer.wait()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=2)
    except TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()


class CodexCLI:
    def __init__(self, model: str = "gpt-6-luna", executable: str | None = None):
        self.model = model
        self.executable = executable or (shutil.which("codex.exe") if os.name == "nt" else shutil.which("codex"))
        if not self.executable:
            raise CodexError("Codex executable not found in PATH")
        self.last_event_types: list[str] = []

    async def decide(self, observation: dict, history: list) -> dict:
        # Fresh process and empty directory each decision; the explicit history is
        # the only intended continuity. No private answer is passed in the prompt.
        prompt = (
            "You are participating in a local decision experiment. Return exactly one "
            "JSON object as your final response. Do not use any Codex tools, shell, "
            "files, network, or other resources. Choose either "
            '{"type":"tool","name":"...","arguments":{...}} or '
            '{"type":"submit","answer":{...}}. '
            "Only the experiment tools described in the observation may be requested "
            "through the JSON action; never execute them yourself.\n"
            + json.dumps({"observation": observation, "history": history}, ensure_ascii=False)
        )
        self.last_event_types = []
        with tempfile.TemporaryDirectory(prefix="codex-time-pilot-") as root:
            proc = await asyncio.create_subprocess_exec(
                self.executable, "exec", "--model", self.model, "--sandbox", "read-only",
                "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
                *[arg for feature in _DISABLED_FEATURES for arg in ("--disable", feature)],
                "-c", 'web_search="disabled"',
                "--json", "--cd", root, "-",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=_child_environment(),
                start_new_session=(os.name != "nt"),
            )
            try:
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(prompt.encode("utf-8"))
                await proc.stdin.drain()
                proc.stdin.close()
                message = None
                while line := await proc.stdout.readline():
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError) as exc:
                        raise CodexError("Malformed CLI event") from exc
                    # Do not retain reasoning, tool output, request headers or stderr.
                    event_name = str(event.get("type", "unknown"))
                    item = event.get("item")
                    item_name = str(item.get("type", "unknown")) if isinstance(item, dict) else ""
                    self.last_event_types.append(event_name + (":" + item_name if item_name else ""))
                    candidate = _check_event(event)
                    if candidate is not None:
                        message = candidate
                code = await proc.wait()
                if code != 0:
                    raise CodexError(f"Codex CLI exited with code {code}; stderr suppressed")
                try:
                    action = json.loads(message)
                except (TypeError, ValueError):
                    # A malformed response is an invalid action, not a tool breach.
                    # The runner gives the same feedback and consumes a decision.
                    return message if isinstance(message, str) else None
                return action
            finally:
                await _stop_process(proc)

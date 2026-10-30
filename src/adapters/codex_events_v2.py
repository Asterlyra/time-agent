"""Candidate event decoder; not integrated with the running experiment.

Times are offsets measured on receipt by the client, not provider timestamps.
An agent_message is only a candidate until turn.completed arrives. A deadline
falling between those events is intrinsically ambiguous with this interface;
this module does not retroactively count the candidate as a timely answer.
No event body, error text, reasoning, request headers, or credentials are kept.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from src.protocol import ProtocolViolation


class CLIServiceError(RuntimeError):
    """CLI reported a terminal error. Message contents are never included."""
    def __init__(self, status_code=None):
        super().__init__('CLI reported a terminal error')
        self.status_code = status_code


def _status(obj):
    """Accept only explicit HTTP status numbers; never parse raw error text."""
    if not isinstance(obj, dict):
        return None
    value = obj.get('status_code')
    return value if type(value) is int and 100 <= value <= 599 else None


@dataclass
class EventTracker:
    """Consumes parsed JSONL events and retains only bounded diagnostic metadata."""
    request_started: float = field(default_factory=time.monotonic)
    clock: object = time.monotonic
    event_types: list[str] = field(default_factory=list)
    error_count: int = 0
    status_codes: list[int] = field(default_factory=list)
    message_offset_s: float | None = None
    turn_completed_offset_s: float | None = None
    _message: str | None = field(default=None, repr=False)
    completed: bool = False

    def feed(self, event):
        if self.completed:
            raise ProtocolViolation('event observed after terminal turn')
        if not isinstance(event, dict):
            raise CLIServiceError()
        event_type = event.get('type')
        item = event.get('item')
        item_type = item.get('type') if isinstance(item, dict) else None
        if not isinstance(event_type, str) or (item_type is not None and not isinstance(item_type, str)):
            raise CLIServiceError()
        known_events = {'thread.started', 'turn.started', 'turn.completed', 'turn.failed',
                        'item.started', 'item.updated', 'item.completed', 'error'}
        known_items = {'agent_message', 'reasoning', 'error', 'command_execution',
                       'mcp_tool_call', 'file_change', 'web_search'}
        label = event_type if event_type in known_events else 'other_event'
        if item_type:
            label += ':' + (item_type if item_type in known_items else 'other_item')
        if len(self.event_types) >= 10000:
            raise CLIServiceError()
        self.event_types.append(label)
        if event_type in ('error', 'turn.failed') or item_type == 'error':
            self.error_count += 1
            for obj in (event, event.get('error'), item):
                status = _status(obj)
                if status is not None:
                    self.status_codes.append(status)
                    break
            if event_type == 'turn.failed' or item_type == 'error':
                raise CLIServiceError(self.status_codes[-1] if self.status_codes else None)
            return None  # CLI may report a recoverable error before success.
        if item_type is not None and item_type not in ('agent_message', 'reasoning'):
            raise ProtocolViolation('forbidden CLI item')
        if event_type == 'item.completed' and item_type == 'agent_message':
            self._message = item.get('text') if isinstance(item.get('text'), str) else None
            self.message_offset_s = self.clock() - self.request_started
        if event_type == 'turn.completed':
            self.turn_completed_offset_s = self.clock() - self.request_started
            self.completed = True
            if self._message is None:
                raise CLIServiceError()
            try:
                return json.loads(self._message)
            except ValueError:
                return self._message  # Runner handles malformed output as an invalid action.
        return None

    def metadata(self):
        return {'event_types': list(self.event_types), 'error_count': self.error_count,
                'status_codes': list(self.status_codes), 'message_offset_s': self.message_offset_s,
                'turn_completed_offset_s': self.turn_completed_offset_s,
                'timing_semantics': 'client_observed_terminal_turn'}


async def consume_events(lines, tracker):
    """Return at terminal turn, not EOF; caller must cancel/reap the CLI process.

    The caller owns hard deadline enforcement and process-tree cleanup. It must
    persist tracker.metadata() on success, error AND cancellation. Returning on
    turn.completed means trailing process output is not audited; do not use this
    in a formal experiment until terminal event semantics and isolation are verified.
    """
    async for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError, TypeError) as exc:
            raise CLIServiceError() from exc
        result = tracker.feed(event)
        if tracker.completed:
            return result
    raise CLIServiceError()


async def consume_audited_events(lines, tracker):
    """Require terminal turn plus EOF and reject unexpected subsequent events.

    Receipt of a candidate message is not proof that it was the final message;
    EOF is part of conservative protocol completion. The caller enforces deadline.
    """
    action = None
    async for line in lines:
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError, TypeError) as exc:
            raise CLIServiceError() from exc
        if not tracker.completed:
            value = tracker.feed(event)
            if tracker.completed:
                action = value
            continue
        # Post-terminal events are never silently ignored. Even benign events
        # must be specifically understood before they can be accepted.
        if isinstance(event, dict) and event.get('type') == 'thread.completed' and 'item' not in event:
            tracker.event_types.append('thread.completed')
            continue
        if isinstance(event, dict) and (event.get('type') in ('error', 'turn.failed') or
                isinstance(event.get('item'), dict) and event['item'].get('type') == 'error'):
            tracker.event_types.append('post_terminal_error')
            tracker.error_count += 1
            raise CLIServiceError(_status(event.get('error')))
        tracker.event_types.append('post_terminal_unexpected')
        raise ProtocolViolation('unexpected event after terminal turn')
    if not tracker.completed:
        raise CLIServiceError()
    return action

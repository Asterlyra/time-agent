"""Wall-clock episode runner. The model sees public data only."""
import asyncio
import copy
import datetime
import time
from .conditions import duration_references, target_delay
from .protocol import ProtocolViolation


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _retryable(exc):
    code = getattr(exc, 'status_code', None)
    return code == 429 or (isinstance(code, int) and 500 <= code <= 599) or isinstance(exc, (ConnectionError, OSError))


async def run_episode(model, *, question, tool_schemas, calibration, call_tool, verify,
                      condition='A', profile='stable_fast', budget_s=120.0,
                      shift_fraction=0.5, fast_s=2.0, slow_s=15.0, window=3,
                      max_steps=20, retry_delay_s=0.25, metadata=None,
                      validate_submission=None, event_sink=None):
    """Run episode with one model decision at a time; tools execute synchronously.

    call_tool(name, arguments) -> JSON-serializable result, raising ValueError for
    invalid calls; verify(answer) -> bool or dictionary with 'correct' boolean.
    The caller must supply only public task data in question, schemas and call_tool.
    """
    if budget_s <= 0 or not 0 < shift_fraction < 1 or min(fast_s, slow_s) < 0:
        raise ValueError('invalid timing configuration')
    if set(tool_schemas) != set(calibration) or any(len(v) < 3 for v in calibration.values()):
        raise ValueError('each tool requires at least three initial calibration samples')
    if validate_submission is None:
        validate_submission = lambda a: (isinstance(a, dict) and
            isinstance(a.get('value'), (int, float)) and not isinstance(a.get('value'), bool) and
            isinstance(a.get('evidence_ids'), list) and
            all(isinstance(x, str) for x in a['evidence_ids']))
    # Validate condition and profile before starting the clock.
    duration_references(condition, calibration, {}, window)
    target_delay(profile, 0, budget_s, shift_fraction, fast_s, slow_s)
    start_utc = _utc()
    start = time.monotonic()
    deadline = start + budget_s
    now = lambda: time.monotonic() - start
    history, events, completed = [], [], {name: [] for name in tool_schemas}
    result = {'metadata': copy.deepcopy(metadata or {}), 'start_utc': start_utc,
              'condition': condition, 'latency_profile': profile, 'budget_s': budget_s,
              'shift_fraction': shift_fraction, 'events': events, 'valid_submission': False,
              'deadline_success': False, 'termination_reason': None, 'verifier_details': None,
              'final_answer': None, 'service_error_flags': []}
    def emit(kind, payload):
        if event_sink is not None:
            event_sink({'kind': kind, 'offset_s': now(), 'data': copy.deepcopy(payload)})

    def record_adapter_diagnostics(attempt_event):
        diagnostics = getattr(model, 'last_diagnostics', None)
        if isinstance(diagnostics, dict):
            # Only public, bounded metadata is retained; never trust arbitrary
            # exception strings, event payloads, absolute monotonic timestamps.
            allowed = ('event_types', 'error_count', 'status_codes', 'message_offset_s',
                       'turn_completed_offset_s', 'timing_semantics', 'tail_events_audited',
                       'cleanup_async', 'eof_offset_s', 'cleanup_status')
            allowed += ('usage', 'finish_reason')
            allowed += ('streaming','transport_error_type','error_category','response_bytes',
                        'first_response_byte_offset_s','stream_event_count')
            attempt_event['adapter_diagnostics'] = {k: copy.deepcopy(diagnostics[k])
                                                    for k in allowed if k in diagnostics}

    emit('episode_start', {'metadata': result['metadata'], 'start_utc': start_utc,
                           'condition': condition, 'profile': profile, 'budget_s': budget_s})

    async def bounded(awaitable):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if hasattr(awaitable, 'close'):
                awaitable.close()
            raise asyncio.TimeoutError()
        return await asyncio.wait_for(awaitable, timeout=remaining)

    for step in range(max_steps):
        if time.monotonic() >= deadline:
            result['termination_reason'] = 'timeout_before_request'
            break
        # Persist intent before sampling time; synchronous journaling must not
        # make the time shown to the model stale before the request starts.
        emit('model_request_started', {'step_index': step})
        if time.monotonic() >= deadline:
            result['termination_reason'] = 'timeout_before_request'
            break
        refs, counts = duration_references(condition, calibration, completed, window)
        sampled = now()
        observation = {'question': copy.deepcopy(question), 'tools': copy.deepcopy(tool_schemas),
                       'calibration_samples_s': copy.deepcopy(calibration),
                       'time_status': {'budget_s': budget_s, 'elapsed_s': sampled,
                                       'remaining_s': max(0, budget_s - sampled)}}
        if refs is not None:
            observation['duration_reference_s'] = refs
            observation['duration_reference_description'] = '基于历史观察的参考值，不保证未来调用耗时。'
        event = {'step_index': step, 'event_type': 'model_request',
                 'time_feedback_sample_offset_s': sampled, 'remaining_at_request_s': max(0, budget_s-sampled),
                 'request_start_offset_s': now(), 'observation': copy.deepcopy(observation),
                 'visible_history': copy.deepcopy(history), 'reference_sample_counts': counts,
                 'retry_count': 0}
        events.append(event)
        action = None
        event['attempts'] = []
        for attempt in range(2):
            event['retry_count'] = attempt
            if attempt:
                resampled = now()
                observation['time_status'].update({'elapsed_s': resampled, 'remaining_s': max(0, budget_s-resampled)})
            attempt_event = {'request_start_offset_s': now(), 'time_feedback_sample_offset_s': observation['time_status']['elapsed_s'],
                             'observation': copy.deepcopy(observation)}
            event['attempts'].append(attempt_event)
            try:
                action = await bounded(model.decide(copy.deepcopy(observation), copy.deepcopy(history)))
                event['response_end_offset_s'] = now()
                attempt_event['response_end_offset_s'] = event['response_end_offset_s']
                if hasattr(model, 'last_event_types'):
                    attempt_event['harness_event_types'] = copy.deepcopy(model.last_event_types)
                record_adapter_diagnostics(attempt_event)
                event['action'] = copy.deepcopy(action)
                break
            except asyncio.TimeoutError:
                event['response_end_offset_s'] = now()
                attempt_event['response_end_offset_s'] = event['response_end_offset_s']
                record_adapter_diagnostics(attempt_event)
                event['is_censored'] = True
                result['termination_reason'] = 'timeout_model'
                break
            except Exception as exc:
                # Never log exception text: it may contain credentials or request content.
                attempt_event['response_end_offset_s'] = now()
                if hasattr(model, 'last_event_types'):
                    attempt_event['harness_event_types'] = copy.deepcopy(model.last_event_types)
                record_adapter_diagnostics(attempt_event)
                error = {'type': type(exc).__name__, 'status_code': getattr(exc, 'status_code', None)}
                event['error'] = error
                if isinstance(exc, ProtocolViolation):
                    result['termination_reason'] = 'protocol_violation'
                    break
                result['service_error_flags'].append(error)
                if attempt == 0 and _retryable(exc):
                    try:
                        await bounded(asyncio.sleep(retry_delay_s))
                    except asyncio.TimeoutError:
                        result['termination_reason'] = 'timeout_model_retry'
                        break
                    continue
                result['termination_reason'] = 'service_error'
                break
        if result['termination_reason']:
            emit('model_request_ended', event)
            break
        emit('model_request_ended', event)
        if event['response_end_offset_s'] >= budget_s:
            result['termination_reason'] = 'timeout_model'
            break
        if isinstance(action, dict) and action.get('type') == 'submit' and validate_submission(action.get('answer')):
            result['valid_submission'] = True
            result['final_answer'] = action['answer']
            details = verify(action['answer'])
            result['verifier_details'] = details
            result['deadline_success'] = bool(details.get('correct')) if isinstance(details, dict) else bool(details)
            result['termination_reason'] = 'submitted'
            break
        name = action.get('name') if isinstance(action, dict) else None
        args = action.get('arguments') if isinstance(action, dict) else None
        if not isinstance(action, dict) or action.get('type') != 'tool' or name not in tool_schemas or not isinstance(args, dict):
            history.append({'action': action, 'error': 'Invalid action or tool arguments.'})
            events.append({'step_index': step, 'event_type': 'invalid_action', 'offset_s': now()})
            emit('invalid_action', events[-1])
            continue
        # Record intent first; start phase and duration are sampled after disk I/O.
        emit('tool_started', {'step_index': step, 'tool_name': name, 'tool_arguments': args})
        tool_start = now()
        if tool_start >= budget_s:
            result['termination_reason'] = 'timeout_before_tool'
            break
        target = target_delay(profile, tool_start, budget_s, shift_fraction, fast_s, slow_s)
        tool_event = {'step_index': step, 'event_type': 'tool', 'tool_name': name,
                      'tool_arguments': copy.deepcopy(args), 'tool_start_offset_s': tool_start,
                      'injected_target_s': target, 'is_censored': False}
        events.append(tool_event)
        try:
            tool_result = call_tool(name, args)
        except (ValueError, KeyError, TypeError) as exc:
            tool_event.update({'tool_end_offset_s': now(), 'invalid': True})
            history.append({'action': action, 'error': 'Invalid tool call.'})
            emit('tool_ended', tool_event)
            continue
        if isinstance(tool_result, dict) and 'error' in tool_result:
            tool_event.update({'tool_end_offset_s': now(), 'invalid': True})
            history.append({'action': action, 'error': 'Invalid tool call.'})
            emit('tool_ended', tool_event)
            continue
        # Include local computation in total duration. No busy waiting.
        try:
            await bounded(asyncio.sleep(max(0.0, target - (now() - tool_start))))
        except asyncio.TimeoutError:
            tool_event.update({'tool_end_offset_s': now(), 'is_censored': True})
            result['termination_reason'] = 'timeout_tool'
            emit('tool_ended', tool_event)
            break
        tool_end = now()
        if time.monotonic() >= deadline:
            tool_event.update({'tool_end_offset_s': tool_end, 'is_censored': True})
            result['termination_reason'] = 'timeout_tool'
            emit('tool_ended', tool_event)
            break
        duration = tool_end - tool_start
        completed[name].append(duration)
        tool_event.update({'tool_end_offset_s': tool_end, 'observed_duration_s': duration,
                           'tool_result': copy.deepcopy(tool_result)})
        emit('tool_ended', tool_event)
        history.append({'action': action, 'tool_result': tool_result, 'duration_s': duration})
    else:
        result['termination_reason'] = 'step_limit'
    result['elapsed_s'] = now()
    emit('episode_finished', {'termination_reason': result['termination_reason'],
                              'deadline_success': result['deadline_success'],
                              'valid_submission': result['valid_submission'],
                              'final_answer': result['final_answer'],
                              'verifier_details': result['verifier_details']})
    return result

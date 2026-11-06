"""Study 2 wall-clock episode runner (partial credit, four-condition ladder).

Same wall-clock discipline as runner_v2: the model sees only public task data,
one JSON action per request, tools execute synchronously with an injected
duration, and a submission is timely only if it arrives before the deadline.
Differences: (1) conditions A/B/C/O, (2) graded score carried out of the verifier,
(3) a submission may cover any non-empty subset of items.
"""
import asyncio
import copy
import datetime

from src.conditions_v3 import DESCRIPTIONS, duration_references, target_delay
from src.elapsed_clock import EpisodeClock, EnvironmentInterruption, clock_metadata
from src.protocol import ProtocolViolation


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _retryable(exc):
    code = getattr(exc, 'status_code', None)
    return code == 429 or (isinstance(code, int) and 500 <= code <= 599) or isinstance(exc, (ConnectionError, OSError))


async def run_episode(model, *, question, tool_schemas, calibration, call_tool, verify,
                      condition='A', profile='stable_fast', budget_s=100.0,
                      shift_fraction=0.4, fast_s=1.5, slow_s=12.0, window=3,
                      max_steps=32, retry_delay_s=0.25, metadata=None,
                      validate_submission=None, event_sink=None, state_provider=None):
    """Run one episode. verify(answer) returns a dict with 'correct' and 'score'."""
    if budget_s <= 0 or not 0 < shift_fraction < 1 or min(fast_s, slow_s) < 0:
        raise ValueError('invalid timing configuration')
    if set(tool_schemas) != set(calibration) or any(len(v) < 3 for v in calibration.values()):
        raise ValueError('each tool requires at least three initial calibration samples')
    if validate_submission is None:
        raise ValueError('study 2 requires an explicit submission shape')
    duration_references(condition, calibration, {}, window,
                        {name: float(fast_s) for name in tool_schemas} if condition == 'O' else None)
    target_delay(profile, 0, budget_s, shift_fraction, fast_s, slow_s)
    start_utc = _utc()
    clock = EpisodeClock()
    start = clock.start
    deadline = start + budget_s
    now = clock.elapsed
    history, events, completed = [], [], {name: [] for name in tool_schemas}
    result = {'metadata': copy.deepcopy(metadata or {}), 'start_utc': start_utc,
              'condition': condition, 'latency_profile': profile, 'budget_s': budget_s,
              'shift_fraction': shift_fraction, 'events': events, 'valid_submission': False,
              'deadline_success': False, 'score': 0, 'total_items': None,
              'termination_reason': None, 'verifier_details': None,
              'final_answer': None, 'service_error_flags': [], 'infrastructure_error_flags': [],
              'clock': clock_metadata()}

    def emit(kind, payload):
        if event_sink is not None:
            event_sink({'kind': kind, 'offset_s': now(), 'data': copy.deepcopy(payload)})

    def record_adapter_diagnostics(attempt_event):
        diagnostics = getattr(model, 'last_diagnostics', None)
        if isinstance(diagnostics, dict):
            allowed = ('event_types', 'error_count', 'status_codes', 'message_offset_s',
                       'turn_completed_offset_s', 'timing_semantics', 'tail_events_audited',
                       'cleanup_async', 'eof_offset_s', 'cleanup_status')
            allowed += ('usage', 'finish_reason')
            allowed += ('streaming', 'transport_error_type', 'error_category', 'response_bytes',
                        'first_response_byte_offset_s', 'stream_event_count')
            attempt_event['adapter_diagnostics'] = {k: copy.deepcopy(diagnostics[k])
                                                    for k in allowed if k in diagnostics}

    emit('episode_start', {'metadata': result['metadata'], 'start_utc': start_utc,
                           'condition': condition, 'profile': profile, 'budget_s': budget_s})

    def check_environment():
        try:
            clock.check()
        except EnvironmentInterruption:
            result['termination_reason'] = 'environment_interruption'
            result['infrastructure_error_flags'].append({'type': 'host_suspend', 'offset_s': now()})
            raise

    async def bounded(awaitable):
        try:
            return await clock.wait(awaitable, deadline)
        except EnvironmentInterruption:
            result['termination_reason'] = 'environment_interruption'
            result['infrastructure_error_flags'].append({'type': 'host_suspend', 'offset_s': now()})
            raise

    for step in range(max_steps):
        try:
            check_environment()
        except EnvironmentInterruption:
            break
        if clock.time() >= deadline:
            result['termination_reason'] = 'timeout_before_request'
            break
        emit('model_request_started', {'step_index': step})
        try:
            check_environment()
        except EnvironmentInterruption:
            break
        if clock.time() >= deadline:
            result['termination_reason'] = 'timeout_before_request'
            break
        oracle = None
        if condition == 'O':
            started_at = now()
            oracle = {name: target_delay(profile, started_at, budget_s, shift_fraction, fast_s, slow_s)
                      for name in tool_schemas}
        refs, counts = duration_references(condition, calibration, completed, window, oracle)
        sampled = now()
        observation = {'question': copy.deepcopy(question), 'tools': copy.deepcopy(tool_schemas),
                       'calibration_samples_s': copy.deepcopy(calibration),
                       'time_status': {'budget_s': budget_s, 'elapsed_s': round(sampled, 2),
                                       'remaining_s': round(max(0, budget_s - sampled), 2)}}
        if refs is not None:
            observation['duration_reference_s'] = {k: round(v, 2) for k, v in refs.items()}
            observation['duration_reference_description'] = DESCRIPTIONS[condition]
        if state_provider is not None:
            # Host-maintained episode state (e.g. items already earned). Identical
            # in every condition; it removes memory load from the stopping decision.
            observation.update(state_provider())
        event = {'step_index': step, 'event_type': 'model_request',
                 'time_feedback_sample_offset_s': sampled, 'remaining_at_request_s': max(0, budget_s - sampled),
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
                observation['time_status'].update({'elapsed_s': resampled,
                                                   'remaining_s': max(0, budget_s - resampled)})
            attempt_event = {'request_start_offset_s': now(),
                             'time_feedback_sample_offset_s': observation['time_status']['elapsed_s'],
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
                result['termination_reason'] = result['termination_reason'] or 'timeout_model'
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
                        result['termination_reason'] = result['termination_reason'] or 'timeout_model_retry'
                        break
                    continue
                result['termination_reason'] = 'service_error'
                break
        if result['termination_reason']:
            emit('model_request_ended', event)
            break
        emit('model_request_ended', event)
        if event['response_end_offset_s'] >= budget_s:
            result['termination_reason'] = result['termination_reason'] or 'timeout_model'
            break
        if isinstance(action, dict) and action.get('type') == 'submit' and validate_submission(action.get('answer')):
            result['valid_submission'] = True
            result['final_answer'] = action.get('answer')
            details = verify(action.get('answer'))
            result['verifier_details'] = details
            result['score'] = int(details.get('score', 0)) if isinstance(details, dict) else 0
            result['total_items'] = details.get('total') if isinstance(details, dict) else None
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
        emit('tool_started', {'step_index': step, 'tool_name': name, 'tool_arguments': args})
        try:
            check_environment()
        except EnvironmentInterruption:
            break
        tool_start = now()
        if tool_start >= budget_s:
            result['termination_reason'] = 'timeout_before_tool'
            break
        target = target_delay(profile, tool_start, budget_s, shift_fraction, fast_s, slow_s)
        tool_event = {'step_index': step, 'event_type': 'tool', 'tool_name': name,
                      'tool_arguments': copy.deepcopy(args), 'tool_start_offset_s': tool_start,
                      'injected_target_s': target, 'is_censored': False,
                      'reference_at_request_s': (refs or {}).get(name)}
        events.append(tool_event)
        try:
            tool_result = call_tool(name, args)
        except (ValueError, KeyError, TypeError):
            tool_event.update({'tool_end_offset_s': now(), 'invalid': True})
            history.append({'action': action, 'error': 'Invalid tool call.'})
            emit('tool_ended', tool_event)
            continue
        if isinstance(tool_result, dict) and 'error' in tool_result:
            tool_event.update({'tool_end_offset_s': now(), 'invalid': True})
            history.append({'action': action, 'error': 'Invalid tool call.'})
            emit('tool_ended', tool_event)
            continue
        try:
            await bounded(asyncio.sleep(max(0.0, target - (now() - tool_start))))
        except asyncio.TimeoutError:
            tool_event.update({'tool_end_offset_s': now(), 'is_censored': True})
            result['termination_reason'] = result['termination_reason'] or 'timeout_tool'
            emit('tool_ended', tool_event)
            break
        tool_end = now()
        if clock.time() >= deadline:
            tool_event.update({'tool_end_offset_s': tool_end, 'is_censored': True})
            result['termination_reason'] = result['termination_reason'] or 'timeout_tool'
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
    result['end_utc'] = _utc()
    result['suspend_gap_s'] = clock.suspend_gap()
    emit('episode_finished', {'termination_reason': result['termination_reason'],
                              'deadline_success': result['deadline_success'],
                              'score': result['score'],
                              'valid_submission': result['valid_submission'],
                              'final_answer': result['final_answer'],
                              'verifier_details': result['verifier_details']})
    return result

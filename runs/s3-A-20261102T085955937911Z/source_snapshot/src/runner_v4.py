"""Study 3 runner: stochastic call durations plus harness-held time policies.

Differences from runner_v3:
  * the duration of a call is drawn by the driver at the moment the call starts
    (`delay_sampler`), so latency is stochastic and heavy-tailed;
  * a `policy` object supplied by the driver owns every harness-side decision:
    what extra fields the observation carries, whether a fetch is admitted,
    whether the episode is forced to submit, and whether a `commit` action is
    expected;
  * a refused fetch costs a request but not a tool duration, and is answered with
    a fixed, identical message in every arm.
The runner itself never decides anything about time; it only enforces what the
policy says, which keeps the five arms a single implementation.
"""
import asyncio
import copy
import datetime
import statistics

from src.elapsed_clock import EpisodeClock, EnvironmentInterruption, clock_metadata
from src.protocol import ProtocolViolation


def _utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _retryable(exc):
    code = getattr(exc, 'status_code', None)
    return code == 429 or (isinstance(code, int) and 500 <= code <= 599) or isinstance(exc, (ConnectionError, OSError))


class NullPolicy:
    """Baseline: no extra fields, admit everything, never force a submission."""

    allow_commit = False

    def observe(self, context):
        return {}

    def admit(self, context, item_id, duration_s):
        return True, ''

    def force_submit(self, context):
        return False

    def record_commit(self, value):
        pass


async def run_episode(model, *, question, tool_schemas, call_tool, verify,
                      delay_sampler, item_ids, budget_s, policy=None,
                      max_steps=40, retry_delay_s=0.25, metadata=None,
                      validate_submission=None, event_sink=None, state_provider=None,
                      clock=None, sleep_fn=None):
    policy = policy or NullPolicy()
    if budget_s <= 0:
        raise ValueError('budget must be positive')
    if not item_ids:
        raise ValueError('item ids required')
    start_utc = _utc()
    clock = clock or EpisodeClock()
    sleep_fn = sleep_fn or asyncio.sleep
    start = clock.start
    deadline = start + budget_s
    now = clock.elapsed
    history, events, request_durations = [], [], []
    result = {'metadata': copy.deepcopy(metadata or {}), 'start_utc': start_utc,
              'budget_s': budget_s, 'events': events, 'valid_submission': False,
              'deadline_success': False, 'score': 0, 'total_points': None,
              'termination_reason': None, 'verifier_details': None,
              'final_answer': None, 'commit': None, 'forced_submit': False,
              'denied_fetches': 0, 'service_error_flags': [],
              'infrastructure_error_flags': [], 'clock': clock_metadata()}

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

    def context():
        durations = request_durations[-5:]
        return {'elapsed': now(), 'remaining': max(0.0, budget_s - now()),
                'budget_s': budget_s,
                'request_estimate_s': statistics.median(durations) if durations else 8.0,
                'history': history, 'item_ids': item_ids}

    def finish(reason, *, submitted=False):
        details = verify(None)
        result['verifier_details'] = details
        result['score'] = int(details.get('score', 0)) if isinstance(details, dict) else 0
        result['total_points'] = details.get('total') if isinstance(details, dict) else None
        result['valid_submission'] = submitted
        result['deadline_success'] = submitted
        result['termination_reason'] = reason
        return True

    emit('episode_start', {'metadata': result['metadata'], 'start_utc': start_utc,
                           'budget_s': budget_s})

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
        if policy.force_submit(context()):
            # The harness ends the episode on the agent's behalf. The score is the
            # same host-side sum a model-issued submission would produce.
            result['forced_submit'] = True
            events.append({'step_index': step, 'event_type': 'forced_submit',
                           'offset_s': now(), 'remaining_s': max(0.0, budget_s - now())})
            emit('forced_submit', events[-1])
            finish('forced_submit', submitted=True)
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
        ctx = context()
        sampled = now()
        observation = {'question': copy.deepcopy(question), 'tools': copy.deepcopy(tool_schemas),
                       'time_status': {'budget_s': budget_s, 'elapsed_s': round(sampled, 2),
                                       'remaining_s': round(max(0.0, budget_s - sampled), 2)}}
        if state_provider is not None:
            observation.update(state_provider())
        observation.update(policy.observe(ctx))
        event = {'step_index': step, 'event_type': 'model_request',
                 'time_feedback_sample_offset_s': sampled,
                 'remaining_at_request_s': max(0.0, budget_s - sampled),
                 'request_start_offset_s': now(), 'observation': copy.deepcopy(observation),
                 'visible_history': copy.deepcopy(history), 'retry_count': 0}
        events.append(event)
        action = None
        event['attempts'] = []
        attempt_started = now()
        for attempt in range(2):
            event['retry_count'] = attempt
            if attempt:
                resampled = now()
                observation['time_status'].update({'elapsed_s': round(resampled, 2),
                                                   'remaining_s': round(max(0.0, budget_s - resampled), 2)})
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
                attempt_event['response_end_offset_s'] = now()
                record_adapter_diagnostics(attempt_event)
                error = {'type': type(exc).__name__, 'status_code': getattr(exc, 'status_code', None)}
                event['error'] = error
                if isinstance(exc, ProtocolViolation):
                    result['termination_reason'] = 'protocol_violation'
                    break
                result['service_error_flags'].append(error)
                if attempt == 0 and _retryable(exc):
                    try:
                        await bounded(sleep_fn(retry_delay_s))
                    except asyncio.TimeoutError:
                        result['termination_reason'] = result['termination_reason'] or 'timeout_model_retry'
                        break
                    continue
                result['termination_reason'] = 'service_error'
                break
        request_durations.append(now() - attempt_started)
        if result['termination_reason']:
            emit('model_request_ended', event)
            break
        emit('model_request_ended', event)
        if event['response_end_offset_s'] >= budget_s:
            result['termination_reason'] = result['termination_reason'] or 'timeout_model'
            break
        if isinstance(action, dict) and action.get('type') == 'submit':
            if validate_submission is None or validate_submission(action.get('answer')):
                result['final_answer'] = action.get('answer')
                finish('submitted', submitted=True)
                break
        if isinstance(action, dict) and action.get('type') == 'commit' and policy.allow_commit:
            value = action.get('reserve_s')
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= budget_s:
                policy.record_commit(float(value))
                result['commit'] = float(value)
                history.append({'action': copy.deepcopy(action), 'accepted': True})
                events.append({'step_index': step, 'event_type': 'commit_accepted',
                               'offset_s': now(), 'reserve_s': float(value)})
                emit('commit_accepted', events[-1])
            else:
                history.append({'action': copy.deepcopy(action),
                                'error': 'reserve_s must be a number between 0 and the budget.'})
            continue
        name = action.get('name') if isinstance(action, dict) else None
        args = action.get('arguments') if isinstance(action, dict) else None
        if not isinstance(action, dict) or action.get('type') != 'tool' or name not in tool_schemas \
                or not isinstance(args, dict):
            history.append({'action': action, 'error': 'Invalid action or tool arguments.'})
            events.append({'step_index': step, 'event_type': 'invalid_action', 'offset_s': now()})
            emit('invalid_action', events[-1])
            continue
        item_id = args.get('item_id')
        if not isinstance(item_id, str) or item_id not in item_ids:
            history.append({'action': action, 'error': 'Invalid tool call.'})
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
        duration = delay_sampler(item_id, tool_start)
        allowed, reason = policy.admit(context(), item_id, duration)
        tool_event = {'step_index': step, 'event_type': 'tool', 'tool_name': name,
                      'tool_arguments': copy.deepcopy(args), 'tool_start_offset_s': tool_start,
                      'sampled_duration_s': duration, 'admitted': allowed, 'is_censored': False}
        if not allowed:
            result['denied_fetches'] += 1
            tool_event['denial_reason'] = reason
            events.append(tool_event)
            history.append({'action': copy.deepcopy(action), 'error': reason})
            emit('tool_denied', tool_event)
            continue
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
            await bounded(sleep_fn(max(0.0, duration - (now() - tool_start))))
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
        tool_event.update({'tool_end_offset_s': tool_end, 'observed_duration_s': tool_end - tool_start,
                           'tool_result': copy.deepcopy(tool_result)})
        if hasattr(policy, 'record_call'):
            policy.record_call(item_id, tool_end - tool_start)
        emit('tool_ended', tool_event)
        history.append({'action': action, 'tool_result': tool_result,
                        'duration_s': tool_end - tool_start})
    else:
        result['termination_reason'] = 'step_limit'
    result['elapsed_s'] = now()
    result['end_utc'] = _utc()
    result['suspend_gap_s'] = clock.suspend_gap()
    if result['termination_reason'] is None:
        result['termination_reason'] = 'unknown'
    emit('episode_finished', {'termination_reason': result['termination_reason'],
                              'score': result['score'],
                              'deadline_success': result['deadline_success'],
                              'forced_submit': result['forced_submit']})
    return result

"""Independent record-level acceptance audit; no sampling or model calls."""
import argparse
import collections
import copy
import datetime
import hashlib
import json
import math
from pathlib import Path

from scripts.go_study import ROOT, tasks_for, make_manifest
from scripts.matrix import digest, write_new
from src.conditions import duration_references, target_delay
from src.adapters.opencode_go import MODELS
from tasks import data_v4


def audit(batch, require_complete=True):
    batch = Path(batch).resolve()
    config = json.loads((batch/'config.json').read_text())
    manifest = json.loads((batch/'manifest.json').read_text())
    tasks = {t['task_id']: t for t in tasks_for(config['stage'])}
    failures = []; warnings = []; rows = []
    def check(ok, code, ident=None):
        if not ok:
            failures.append({'check': code, 'run_id': ident})
    check(digest(config) == json.loads((batch/'config_hash.json').read_text())['sha256'], 'config_hash')
    check(digest(manifest) == config['manifest_hash'], 'manifest_hash')
    check(digest(list(tasks.values())) == config['task_hash'], 'task_hash')
    check(len({e['run_id'] for e in manifest}) == len(manifest), 'unique_runs')
    check(manifest == make_manifest(list(tasks.values()), config['stage'], config['manifest_seed']), 'registered_matrix')
    check(config['models'] == list(MODELS), 'three_fixed_models')
    hashes = json.loads((batch/'source_snapshot_hashes.json').read_text())
    check(digest(hashes) == config['code_hash'], 'source_map_hash')
    for source, expected in hashes.items():
        path = batch/'source_snapshot'/Path(source).relative_to(ROOT)
        check(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'source_snapshot')
    missing = []
    for entry in manifest:
        ident = entry['run_id']; path = batch/'episodes'/(ident+'.json')
        if not path.exists():
            missing.append(ident)
            continue
        row = json.loads(path.read_text()); result = row['result']; rows.append(row)
        started = batch/'started'/(ident+'.json')
        check(started.exists() and json.loads(started.read_text()) == entry, 'started_identity', ident)
        check(row['manifest'] == entry, 'manifest_identity', ident)
        check(result['metadata']['config_hash'] == digest(config), 'result_config', ident)
        check(result['budget_s'] == config['budget_s'], 'result_budget', ident)
        check(result['condition'] == entry['condition'] and result['latency_profile'] == entry['profile'], 'result_condition', ident)
        task = tasks[entry['task_id']]
        schemas = config['tool_schemas'][entry['task_family']]
        phase = 'slow' if entry['profile'] == 'slow_to_fast' else 'fast'
        calibration = {name: config['calibration'][phase][name] for name in schemas}
        completed = {name: [] for name in schemas}; history = []; last_end = 0
        requests = [e for e in result['events'] if e.get('event_type') == 'model_request']
        actions = {e['step_index']: e.get('action') for e in requests}
        check(len(actions) == len(requests), 'unique_request_steps', ident)
        for event in result['events']:
            kind = event.get('event_type')
            if kind == 'model_request':
                refs, counts = duration_references(entry['condition'], calibration, completed, config['window'])
                obs = event['observation']
                check(event['visible_history'] == history, 'visible_history_exact', ident)
                check(obs['question'] == task['public']['question'] and obs['tools'] == schemas, 'public_inputs', ident)
                check(obs['calibration_samples_s'] == calibration, 'calibration', ident)
                check(obs.get('duration_reference_s') == refs and event['reference_sample_counts'] == counts, 'condition_reference', ident)
                check(event['request_start_offset_s'] >= last_end, 'sequential_request', ident)
                for attempt in event['attempts']:
                    a = attempt['observation']; status = a['time_status']
                    check(status['budget_s'] == config['budget_s'] and math.isclose(status['remaining_s'], max(0, config['budget_s']-status['elapsed_s']), abs_tol=1e-7), 'remaining_time', ident)
                    check(attempt['request_start_offset_s'] >= status['elapsed_s'], 'feedback_before_request', ident)
                    check(a.get('duration_reference_s') == refs and a['question'] == task['public']['question'], 'retry_public_inputs', ident)
                last_end = event.get('response_end_offset_s', event['request_start_offset_s'])
            elif kind == 'tool':
                start = event['tool_start_offset_s']
                check(start >= last_end and start < config['budget_s'], 'tool_start_before_deadline', ident)
                check(event['injected_target_s'] == target_delay(entry['profile'], start, config['budget_s'], config['shift_fraction'], config['fast_s'], config['slow_s']), 'tool_phase', ident)
                last_end = event['tool_end_offset_s']
                # The runner preserves the complete returned action in history,
                # including ignored top-level fields. Never normalize these
                # away when independently rebuilding the visible transcript.
                action = copy.deepcopy(actions.get(event['step_index']))
                matches = (isinstance(action,dict) and action.get('type') == 'tool'
                           and action.get('name') == event['tool_name']
                           and action.get('arguments') == event['tool_arguments'])
                check(matches, 'tool_matches_model_request', ident)
                if not event.get('invalid') and not event.get('is_censored'):
                    duration = event['observed_duration_s']
                    check(last_end < config['budget_s'] and math.isclose(duration, last_end-start, abs_tol=1e-7), 'completed_tool_timing', ident)
                    expected_output = data_v4.call_tool(task['public'], event['tool_name'], event['tool_arguments'])
                    check(expected_output == event['tool_result'], 'tool_public_output', ident)
                    completed[event['tool_name']].append(duration)
                    history.append({'action': action, 'tool_result': event['tool_result'], 'duration_s': duration})
                elif event.get('invalid'):
                    history.append({'action': action, 'error': 'Invalid tool call.'})
            elif kind == 'invalid_action':
                previous = next(e for e in reversed(result['events'][:result['events'].index(event)]) if e.get('event_type') == 'model_request')
                history.append({'action': previous.get('action'), 'error': 'Invalid action or tool arguments.'})
        if result['valid_submission']:
            detail = data_v4.verify(task['private'], result['final_answer'])
            check(detail == result['verifier_details'], 'independent_regrade', ident)
            submitted = [e for e in result['events'] if e.get('event_type') == 'model_request' and isinstance(e.get('action'), dict) and e['action'].get('type') == 'submit']
            check(bool(submitted) and submitted[-1]['response_end_offset_s'] < config['budget_s'], 'submission_arrival', ident)
            check(result['deadline_success'] == bool(detail['correct']), 'deadline_score', ident)
        else:
            check(not result['deadline_success'], 'no_submission_no_success', ident)
        if config.get('clock'):
            check(result.get('clock') == config['clock'], 'continuous_clock_identity', ident)
            check(not result.get('infrastructure_error_flags') and result['termination_reason'] != 'environment_interruption', 'no_environment_interruption', ident)
            calendar = (datetime.datetime.fromisoformat(result['end_utc'])-datetime.datetime.fromisoformat(result['start_utc'])).total_seconds()
            if abs(calendar-result['elapsed_s']) > 1 or result.get('suspend_gap_s', 0) > 1:
                warnings.append({'run_id': ident, 'check': 'calendar_or_postarrival_suspend_requires_review'})
        journal = [json.loads(line) for line in (batch/'journals'/(ident+'.jsonl')).read_text().splitlines()]
        # Journal records wrap emitted payloads; inspect the actual envelope.
        kinds = [e.get('kind', e.get('event', {}).get('kind')) for e in journal]
        check('episode_start' in kinds and 'episode_finished' in kinds and 'episode_interrupted' not in kinds, 'complete_journal', ident)
    if require_complete:
        check(not missing, 'complete_manifest')
    return {'batch': str(batch), 'planned': len(manifest), 'completed': len(rows), 'missing': missing,
            'pass': not failures, 'failures': failures, 'warnings': warnings,
            'termination': dict(collections.Counter(r['result']['termination_reason'] for r in rows)),
            'auditor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope': 'all present records, frozen source/config identity, references/history, public tools, independent deterministic regrade, deadlines, journals; no provider-internal verification'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('batch'); parser.add_argument('--output', required=True)
    parser.add_argument('--allow-incomplete', action='store_true'); args = parser.parse_args()
    result = audit(args.batch, not args.allow_incomplete)
    write_new(Path(args.output), result)
    print(json.dumps({k: v for k,v in result.items() if k not in ('missing','failures','warnings')}, ensure_ascii=False))
    print(json.dumps({'failures': result['failures'][:10], 'warning_count': len(result['warnings'])}, ensure_ascii=False))
    raise SystemExit(0 if result['pass'] else 1)

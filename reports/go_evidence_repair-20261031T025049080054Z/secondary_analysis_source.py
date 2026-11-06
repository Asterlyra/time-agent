"""Descriptive secondary analysis from complete frozen matrices only.

Never imported by the execution/calibration controller. No model calls, no
parameter choice, no conditional-success filtering of endpoint contrasts.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path

from scripts.go_study import observations
from scripts.matrix import write_new
from scripts.publish_study_report import load_complete
from tasks import data_v4


def distribution(values):
    values = sorted(v for v in values if isinstance(v, (int,float)) and math.isfinite(v))
    if not values:
        return {'n': 0, 'mean': None, 'p50': None, 'p90': None, 'p95': None}
    def quantile(p):
        position = p*(len(values)-1); lo = int(position); hi = min(lo+1,len(values)-1)
        return values[lo]+(values[hi]-values[lo])*(position-lo)
    return {'n': len(values), 'mean': sum(values)/len(values),
            'p50': quantile(.5), 'p90': quantile(.9), 'p95': quantile(.95)}


def error_class(result):
    if result['deadline_success']:
        return 'correct'
    if result['termination_reason'] == 'submitted':
        detail = result['verifier_details']
        if detail['value_correct'] and not detail['evidence_correct']:
            return 'evidence_only_error'
        if detail['evidence_correct'] and not detail['value_correct']:
            return 'value_only_error'
        return 'value_and_evidence_error'
    return result['termination_reason']


def inspected_full_source_ids(history):
    """Summary search IDs alone do not count as having read document facts."""
    ids = set()
    for event in history:
        value = event.get('tool_result', {})
        if not isinstance(value, dict):
            continue
        document = value.get('document')
        if isinstance(document, dict) and isinstance(document.get('id'), str):
            ids.add(document['id'])
        for row in value.get('rows', []):
            if isinstance(row, dict) and isinstance(row.get('id'), str):
                ids.add(row['id'])
    return ids


def next_action(event, required_ids):
    action = event.get('action'); history = event.get('visible_history', [])
    seen = inspected_full_source_ids(history)
    category = 'no_complete_action'
    if isinstance(action,dict):
        if action.get('type') == 'submit':
            category = 'submit'
        elif action.get('type') == 'tool':
            repeated = any(e.get('action') == action and 'tool_result' in e for e in history)
            category = 'repeat_tool' if repeated else 'new_tool'
        else:
            category = 'invalid_action'
    elif action is not None:
        category = 'invalid_action'
    arguments = action.get('arguments', {}) if isinstance(action,dict) else {}
    return {'category': category, 'tool': action.get('name') if isinstance(action,dict) else None,
            'nonempty_lookup_filter': bool(isinstance(action,dict) and action.get('name') == 'lookup_rows'
                and isinstance(arguments,dict) and arguments.get('filters')),
            'required_sources_read': len(set(required_ids)&seen), 'required_sources_total': len(set(required_ids)),
            'all_required_sources_read': set(required_ids) <= seen}


def collect(rows, tasks):
    episode_metrics = []; prediction_errors = []; after_feedback = []; examples = {}
    for row in rows:
        entry = row['manifest']; result = row['result']; events = result['events']
        requests = [e for e in events if e.get('event_type') == 'model_request']
        tools = [e for e in events if e.get('event_type') == 'tool']
        model_times = [e['response_end_offset_s']-e['request_start_offset_s'] for e in requests if 'response_end_offset_s' in e]
        tool_times = [e['tool_end_offset_s']-e['tool_start_offset_s'] for e in tools if 'tool_end_offset_s' in e]
        attempts = [a for e in requests for a in e.get('attempts',[])]
        usage = [a.get('adapter_diagnostics',{}).get('usage',{}) for a in attempts]
        exposed, both, decision = observations(result)
        key = {k: entry[k] for k in ('run_id','model_id','task_id','task_family','profile','condition','repeat')}
        code = error_class(result)
        if code != 'correct':
            rank = (entry['task_id'],entry['model_id'],entry['condition'],entry['profile'],entry['repeat'])
            if code not in examples or rank < examples[code]['rank']:
                examples[code] = {'rank': rank, 'run_id': entry['run_id'], 'error': code}
        values = {**key, 'success': result['deadline_success'], 'error_class': code,
            'model_requests': len(requests), 'attempts': len(attempts), 'tools': len(tools),
            'completed_tools': sum('observed_duration_s' in e for e in tools),
            'censored_model_requests': sum(bool(e.get('is_censored')) for e in requests),
            'censored_tools': sum(bool(e.get('is_censored')) for e in tools),
            'invalid_tools': sum(bool(e.get('invalid')) for e in tools),
            'elapsed_s': result['elapsed_s'], 'model_request_span_s': sum(model_times),
            'tool_span_s': sum(tool_times),
            'loop_and_logging_s': result['elapsed_s']-sum(model_times)-sum(tool_times),
            'completed_request_s': [t for e,t in zip([e for e in requests if 'response_end_offset_s' in e],model_times) if not e.get('is_censored')],
            'usage': usage, 'new_phase_feedback_then_request': exposed,
            'same_tool_both_phases': both, 'valid_action_after_feedback': decision,
            'service_flagged': bool(result.get('service_error_flags'))}
        episode_metrics.append(values)
        invalid_steps = {e['step_index'] for e in events if e.get('event_type') == 'invalid_action' or e.get('invalid')}
        boundary = result['budget_s']*result['shift_fraction']
        shifted = [e for e in tools if e['tool_start_offset_s'] >= boundary
                   and 'observed_duration_s' in e and not e.get('invalid') and not e.get('is_censored')]
        if result['latency_profile'] != 'stable_fast' and shifted:
            first_end = min(e['tool_end_offset_s'] for e in shifted)
            following = [e for e in requests if e['request_start_offset_s'] >= first_end]
            for index,event in enumerate(following):
                description = next_action(event,tasks[entry['task_id']]['private']['evidence_ids'])
                if event['step_index'] in invalid_steps:
                    description['category'] = 'invalid_action'
                after_feedback.append({**key,'decision_index_after_feedback':index,'step_index':event['step_index'],**description})
        for event in requests:
            action = event.get('action')
            if not isinstance(action,dict) or action.get('type') != 'tool':
                continue
            name = action.get('name'); reference = event['observation'].get('duration_reference_s',{}).get(name)
            tool = next((e for e in tools if e['step_index'] == event['step_index']),None)
            if reference is None or tool is None or tool.get('invalid'):
                continue
            complete = 'observed_duration_s' in tool and not tool.get('is_censored')
            duration = tool.get('observed_duration_s') if complete else None
            prediction_errors.append({**key, 'step_index':event['step_index'],'tool':name,
                'new_phase': tool['tool_start_offset_s'] >= boundary, 'reference_s':reference,
                'complete':complete, 'duration_s':duration,
                'signed_error_s':duration-reference if complete else None,
                'absolute_error_s':abs(duration-reference) if complete else None})
    return episode_metrics,prediction_errors,after_feedback,[v for _,v in sorted(examples.items())]


def summarize(episodes, predictions, after_feedback):
    groups = []; contrasts = []; reference_groups = []
    for model in sorted({e['model_id'] for e in episodes}):
        for profile in ('stable_fast','fast_to_slow','slow_to_fast'):
            cells = {}
            for condition in 'ABC':
                selected = [e for e in episodes if (e['model_id'],e['profile'],e['condition']) == (model,profile,condition)]
                if not selected:
                    continue
                cells[condition] = sum(e['success'] for e in selected)/len(selected)
                use = [u for e in selected for u in e['usage']]
                known = lambda field: {'reported_n':sum(field in u for u in use),
                    'reported_sum':sum(u[field] for u in use if field in u)}
                token_keys = ('input','output','reasoning','cache_read','cache_write_5m','cache_write_1h')
                tokens = {k:{'reported_n':sum(k in u.get('billed_tokens',{}) for u in use),
                    'reported_sum':sum(u.get('billed_tokens',{}).get(k,0) for u in use)} for k in token_keys}
                groups.append({'model':model,'profile':profile,'condition':condition,'n':len(selected),
                    'success':sum(e['success'] for e in selected),
                    'errors':dict(collections.Counter(e['error_class'] for e in selected)),
                    'time_s':{k:distribution([e[k] for e in selected]) for k in ('elapsed_s','model_request_span_s','tool_span_s','loop_and_logging_s')},
                    'completed_request_s':distribution([t for e in selected for t in e['completed_request_s']]),
                    'censored_model_requests':sum(e['censored_model_requests'] for e in selected),
                    'censored_tools':sum(e['censored_tools'] for e in selected),
                    'request_attempts':len(use), 'attempts_without_reported_usage':sum(not u for u in use),
                    'billing_sources':dict(collections.Counter(u.get('billing_source','unreported') for u in use)),
                    'allowance':known('allowance'),'cash_cost':known('cost'),'billed_tokens':tokens,
                    'exposed':sum(e['new_phase_feedback_then_request'] for e in selected),
                    'same_tool_both_phases':sum(e['same_tool_both_phases'] for e in selected),
                    'valid_action_after_feedback':sum(e['valid_action_after_feedback'] for e in selected)})
            if set(cells) == set('ABC'):
                contrasts.append({'model':model,'profile':profile,'C-B':cells['C']-cells['B'],
                                  'C-A':cells['C']-cells['A'],'B-A':cells['B']-cells['A']})
            for condition in 'BC':
                for new_phase in (False,True):
                    z = [e for e in predictions if (e['model_id'],e['profile'],e['condition'],e['new_phase']) == (model,profile,condition,new_phase)]
                    reference_groups.append({'model':model,'profile':profile,'condition':condition,'new_phase':new_phase,
                        'eligible_predictions':len(z),'censored':sum(not e['complete'] for e in z),
                        'absolute_error_s':distribution([e['absolute_error_s'] for e in z if e['complete']]),
                        'signed_error_s':distribution([e['signed_error_s'] for e in z if e['complete']])})
    action_groups = []
    keys = sorted({(e['model_id'],e['profile'],e['condition']) for e in after_feedback})
    for key in keys:
        z = [e for e in after_feedback if (e['model_id'],e['profile'],e['condition']) == key]
        first = [e for e in z if e['decision_index_after_feedback'] == 0]
        action_groups.append({'model':key[0],'profile':key[1],'condition':key[2],
            'first_decisions':len(first),'first_categories':dict(collections.Counter(e['category'] for e in first)),
            'all_decisions':len(z),'all_categories':dict(collections.Counter(e['category'] for e in z)),
            'nonempty_filtered_lookups':sum(e['nonempty_lookup_filter'] for e in z),
            'submit_after_all_required_sources_read':sum(e['category']=='submit' and e['all_required_sources_read'] for e in z),
            'submit_before_all_required_sources_read':sum(e['category']=='submit' and not e['all_required_sources_read'] for e in z)})
    return {'cells':groups,'descriptive_contrasts':contrasts,'reference_errors':reference_groups,'post_feedback_actions':action_groups}


def publish(batch,output,preview=False):
    batch,config,manifest,rows = load_complete(batch,preview)
    tasks = {t['task_id']:t for t in data_v4.generate('dev' if preview else 'test')}
    metrics,predictions,actions,examples = collect(rows,tasks)
    output = Path(output).resolve(); output.mkdir(parents=True,exist_ok=False)
    summary = summarize(metrics,predictions,actions)
    summary.update({'batch':str(batch),'stage':config['stage'],'n':len(rows),'development_preview':preview,
        'scope':'secondary descriptive analysis only; never used by parameter adaptation or formal entry',
        'limits':['No secondary confidence intervals or multiplicity-adjusted claims.',
            'Post-feedback subsets and completed-duration subsets are behavior-dependent descriptive samples.',
            'Full source IDs read is a necessary evidence-availability proxy, not proof of reasoning or sufficiency.',
            'Request spans include retry/backoff and network/provider/client time; censored spans are separate.',
            'Reported token/cost counters are not filled as actual zero where missing.'],
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    write_new(output/'summary.json',summary); write_new(output/'episode_metrics.json',metrics)
    write_new(output/'reference_errors.json',predictions);write_new(output/'post_feedback_actions.json',actions)
    write_new(output/'error_examples.json',examples);(output/'analysis_source.py').write_bytes(Path(__file__).read_bytes())
    lines = ['# 次要指标与轨迹分析','', '开发描述性预览。' if preview else '完整冻结正式矩阵的次要描述性分析。',
        '',f'批次 `{batch.name}`，完整 {len(rows)} 次。主比较及其区间另见主报告。此处不作额外显著性宣称。',
        '', '| 模型 | 模式 | C−B | C−A | B−A |','|---|---|---:|---:|---:|']
    for c in summary['descriptive_contrasts']:
        lines.append(f'| {c["model"]} | {c["profile"]} | {c["C-B"]*100:+.2f} | {c["C-A"]*100:+.2f} | {c["B-A"]*100:+.2f} |')
    lines += ['', '差值单位为百分点；所有 endpoint 差值包含完整清单，不只选已暴露或成功的任务。',
        '', '## 错误、时间与暴露','', '| 模型 | 模式 | 条件 | 错误分类 | 请求中位耗时 | 工具中位耗时 | 暴露/有效后续动作 |',
        '|---|---|---|---|---:|---:|---:|']
    for c in summary['cells']:
        lines.append(f'| {c["model"]} | {c["profile"]} | {c["condition"]} | {c["errors"]} | {c["time_s"]["model_request_span_s"]["p50"]:.2f} | {c["time_s"]["tool_span_s"]["p50"]:.2f} | {c["exposed"]}/{c["valid_action_after_feedback"]} |')
    lines += ['', '时间单位为每 episode 秒数，请求跨度含重试等待；详细分位数、删失、token、缓存和已知额度见 summary.json。',
        '', '## 参考误差与后续动作','', '参考误差仅使用下一次同类完整工具耗时；删失数单列。它反映摘要统计器的滞后，不能解释为模型预测能力。变化反馈后的动作与证据可用性只作条件性描述，不能替代全样本主结果。',
        '', '[参考误差](reference_errors.json) · [后续动作与来源覆盖](post_feedback_actions.json) · [各类错误的排序首例](error_examples.json)',
        '', '## 限制','']+[f'- {limit}' for limit in summary['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    print(output/'report.md')
    return summary


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch');parser.add_argument('--output',required=True)
    parser.add_argument('--development-preview',action='store_true');args=parser.parse_args()
    publish(args.batch,args.output,args.development_preview)

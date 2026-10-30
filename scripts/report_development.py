"""Write an exploratory Chinese report from a completed/partial development batch.

Usage: python -m scripts.report_development BATCH OUTPUT.md
Never overwrites OUTPUT. This is not confirmatory or formal analysis.
"""
import argparse
import collections
import datetime
import importlib.util
import json
from pathlib import Path
from scripts.analyze_development import summarize


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _event_timeline(result):
    bits = []
    for event in result.get('events', []):
        kind = event.get('event_type')
        if kind == 'tool':
            offset = event.get('tool_start_offset_s', 0)
            status = '删失' if event.get('is_censored') else '完成' if 'observed_duration_s' in event else '无效'
            bits.append(f"{offset:.1f}s {event.get('tool_name', '?')}({status})")
        elif kind == 'model_request' and isinstance(event.get('action'), dict) and event['action'].get('type') == 'submit':
            action = event['action']
            valid = result.get('valid_submission') and action.get('answer') == result.get('final_answer')
            bits.append(f"{event.get('response_end_offset_s', 0):.1f}s {'有效提交' if valid else '无效提交尝试'}")
    return '；'.join(bits) or '无已记录工具或提交'


def render(batch):
    path = Path(batch)
    manifest = _read(path / 'manifest.json')
    summary = summarize(path)
    # A running batch may change while a report snapshot is being read.
    started = {p.stem for p in (path / 'started').glob('*.json')}
    rows = {}
    for entry in manifest:
        file = path / 'episodes' / (entry['run_id'] + '.json')
        if file.exists():
            value = _read(file)
            if value['manifest'] != entry:
                raise ValueError('episode does not match manifest')
            rows[entry['run_id']] = (entry, value['result'])
    if len(rows) != summary['completed']:
        raise RuntimeError('批次正在写入且快照不一致，请稍后重试')
    config = _read(path / 'config.json')
    group_planned, group_started = collections.Counter(), collections.Counter()
    for e in manifest:
        key = (e['profile'], e['condition'], e['task_family'])
        group_planned[key] += 1
        if e['run_id'] in started: group_started[key] += 1
    # Include completed entries in started count even if an external producer omitted a marker.
    started |= set(rows)
    missing_marker = sum(1 for rid in rows if not (path / 'started' / f'{rid}.json').exists())
    term = collections.Counter(r.get('termination_reason', 'unknown') for _, r in rows.values())
    model = config.get('model', 'unknown')
    lines = [
        '# Luna 开发批次描述性报告', '',
        f"生成时间（UTC）：{datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        f'批次：`{path.as_posix()}`；模型：`{model}`。', '',
        '**仅为探索性开发数据，不是冻结后的正式实验，也不能用于推断条件效果。**', '',
        f"计划 {len(manifest)} 条，已启动 {len(started)} 条，已有结果 {len(rows)} 条，已启动未完成 {len(started - set(rows))} 条，尚未启动 {len(manifest)-len(started)} 条。",
        f'有结果但缺少启动标记：{missing_marker} 条。分析脚本的未完成数 {summary["uncompleted"]} 包含已启动未完成和未启动。', '',
        '每行成功率的分母是该行**已有结果**的 episode，未启动或尚未结束的不在该分母中。未完成批次的不同条件分母和任务可能不平衡。', '',
        '| 延迟模式 | 条件 | 任务类 | 计划 | 已启动 | 已有结果 | 截止前正确 |',
        '|---|---|---|---:|---:|---:|---:|',
    ]
    groups = {(g['profile'], g['condition'], g['family']): g for g in summary['groups']}
    for key in sorted(group_planned):
        g = groups.get(key, {'n': 0, 'success': 0})
        n, s = g['n'], g['success']
        pct = f'{100*s/n:.1f}%' if n else '—'
        lines.append(f'| {key[0]} | {key[1]} | {key[2]} | {group_planned[key]} | {group_started[key]} | {n} | {s}/{n} ({pct}) |')
    lines += ['', '## 终止原因', '', '| 原因 | 数量 | 分母 |', '|---|---:|---:|']
    for reason, n in sorted(term.items()):
        lines.append(f'| {reason} | {n} | {len(rows)} |')
    if not term: lines.append('| 暂无结果 | 0 | 0 |')
    lines += ['', '## 延迟变化可观察性', '',
              '“观察变化”表示在变化点后开始的一次工具调用已完成并返回；“之后有决策”要求随后发出过模型请求。稳定快模式没有变化，记为不适用。该子集由模型行为决定，仅供描述。', '',
              '| 延迟模式 | 条件 | 任务类 | 已有结果 | 观察变化 | 观察后有决策 |', '|---|---|---|---:|---:|---:|']
    for key in sorted(group_planned):
        g = groups.get(key, {'n': 0, 'shift_observed': 0, 'post_shift_decision': 0})
        shift = '—' if key[0] == 'stable_fast' else str(g['shift_observed'])
        decision = '—' if key[0] == 'stable_fast' else str(g['post_shift_decision'])
        lines.append(f'| {key[0]} | {key[1]} | {key[2]} | {g["n"]} | {shift} | {decision} |')
    blocks = collections.defaultdict(dict)
    for entry, result in rows.values():
        key = (entry['model_id'], entry['task_id'], entry['profile'], entry['repeat'])
        blocks[key][entry['condition']] = (entry, result)
    examples = collections.defaultdict(list)
    for key in sorted(blocks):
        block = blocks[key]
        if 'B' in block and 'C' in block:
            b, c = block['B'], block['C']
            category = ('成功' if c[1]['deadline_success'] else '失败') + '/' + ('成功' if b[1]['deadline_success'] else '失败')
            examples[category].append((key, b, c))
    lines += ['', '## 代表轨迹', '',
              '本报告使用的选择规则（未在运行前预注册）：在相同模型、任务、延迟模式及重复编号的完整 B/C 配对中，按任务及配对键排序；每种 C/B 成败组合取第一组。不存在时明确标注。失败包含所有非成功终止，不能推断其原因相同。', '']
    for category in ('成功/失败', '失败/成功', '失败/失败', '成功/成功'):
        lines.append(f'### C/B {category}')
        lines.append('')
        if not examples[category]:
            lines.append('当前快照没有符合条件的完整配对。')
        else:
            key, b, c = examples[category][0]
            lines.append(f'任务 `{key[1]}`；模式 `{key[2]}`；重复 `{key[3]}`。')
            for label, (e, r) in [('B', b), ('C', c)]:
                ref = (path / 'episodes' / (e['run_id'] + '.json')).resolve().as_posix()
                lines.append(f'- {label}：`{e["run_id"]}`，终止 `{r["termination_reason"]}`，耗时 {r["elapsed_s"]:.1f} 秒；{_event_timeline(r)}。 [完整轨迹]({ref})')
        lines.append('')
    lines += ['## 局限', '',
              '- 单一模型、开发集、小样本及可能尚未完成的批次；结果不能推广或作为 C 对 B 的正式比较。',
              '- CLI 自带指令及工具与其他模型接口不同；当前措施不足以证明操作系统级文件/网络隔离。',
              '- 每次决策启动 CLI 进程，启动及推理时间计入预算；token 和费用字段若未知为 null。',
              '- 任务模板的信息结构与行、证据 ID 规律存在局限，变化点前完成的任务不应排除。',
              '- 并发预校准样本可能相关，人工复核与冻结配置尚未完成。',
              '- 无正式配对 bootstrap、假设检验或效果结论。']
    if importlib.util.find_spec('matplotlib') is None:
        lines += ['', '本环境未检测到 matplotlib；本报告不生成图。上述表格保留原始分母。']
    else:
        lines += ['', '检测到 matplotlib；本报告生成器目前不绘图，表格保留原始分母。']
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('batch')
    p.add_argument('output')
    args = p.parse_args()
    report = render(args.batch)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('x', encoding='utf-8', newline='\n') as f:
        f.write(report)
    print(dest)

if __name__ == '__main__': main()

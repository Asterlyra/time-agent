"""Two-task diagnostic only; never use results as the frozen experiment."""
import asyncio
import datetime
import json
from pathlib import Path
from tasks.data_v2 import generate, call_tool, verify
from src.runner import run_episode
from src.adapters.codex_cli import CodexCLI
from src.calibration import calibrate

SCHEMAS = {
    'evidence': {
        'search': {'description': '搜索文档摘要', 'arguments': {'query': '文档文本中的字符串'}},
        'read_document': {'description': '读取文档全文', 'arguments': {'id': '文档ID'}},
    },
    'table': {
        'lookup_rows': {'description': '查询表格行，最多10行；空 filters 可返回全部行。products 字段为 id, product, unit_cost, category；batches 字段为 id, product, quantity, status, discount, freight。', 'arguments': {'table': 'products 或 batches', 'filters': '字段与值组成的对象'}},
        'calculate': {'description': '计算仅含数字和 + - * / 的表达式', 'arguments': {'expression': '算式字符串'}},
    },
}

async def main():
    batch = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    dest = Path('runs') / ('diagnostic-' + batch)
    dest.mkdir(parents=True, exist_ok=False)
    model = CodexCLI()
    samples = await calibrate(['search', 'read_document', 'lookup_rows', 'calculate'], 2, tool_call=call_tool)
    for family in ('evidence', 'table'):
        task = next(t for t in generate('dev') if t['task_family'] == family)
        schemas = SCHEMAS[family]
        calibration = {name: samples[name] for name in schemas}
        result = await run_episode(
            model, question=task['public']['question'], tool_schemas=schemas,
            calibration=calibration,
            call_tool=lambda name, args: call_tool(task['public'], name, args),
            verify=lambda answer: verify(task['private'], answer),
            condition='C', profile='stable_fast', budget_s=120,
            metadata={'task_id': task['task_id'], 'task_family': family,
                      'model_id': model.model, 'task_generator': 'v2-candidate', 'purpose': 'development diagnostic, not formal data',
                      'calibration_method': 'three concurrently measured tool and injected wait samples per tool outside the episode',
                      'cli_isolation': 'not guaranteed', 'token_usage': None, 'estimated_cost': None})
        result['codex_last_event_types'] = model.last_event_types
        (dest / (task['task_id'] + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'task_id': task['task_id'], 'termination_reason': result['termination_reason'],
                          'deadline_success': result['deadline_success'], 'elapsed_s': result['elapsed_s'],
                          'service_error_flags': result['service_error_flags'], 'run_dir': str(dest)}, ensure_ascii=False), flush=True)
        if result['termination_reason'] in ('service_error', 'protocol_violation'):
            break

if __name__ == '__main__':
    asyncio.run(main())

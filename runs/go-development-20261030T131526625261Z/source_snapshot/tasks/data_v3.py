"""Development candidate: bounded paginated table lookup; no frozen data.

Data and verifier are unchanged from v2. Only the lookup interface changes.
Use SCHEMAS when exposing the tools, and pair with the versioned pilot plan.
"""
from tasks import data_v2

PAGE_SIZE = 2


def generate(split):
    tasks = data_v2.generate(split)
    for task in tasks:
        task['generator_version'] = 'v3-pagination-candidate'
    return tasks


def call_tool(public, name, args):
    if name != 'lookup_rows':
        return data_v2.call_tool(public, name, args)
    if not isinstance(args, dict):
        return {'error': 'arguments must be an object'}
    cursor = args.get('cursor', 0)
    if type(cursor) is not int or cursor < 0 or cursor % PAGE_SIZE:
        return {'error': 'cursor must be a nonnegative multiple of two'}
    result = data_v2.call_tool(public, name, {k: v for k, v in args.items() if k != 'cursor'})
    if 'error' in result:
        return result
    rows = result['rows']
    if cursor > len(rows) or (cursor and cursor >= len(rows)):
        return {'error': 'cursor out of range'}
    end = min(cursor + PAGE_SIZE, len(rows))
    return {'rows': rows[cursor:end], 'next_cursor': end if end < len(rows) else None}


verify = data_v2.verify


def tool_schemas():
    from copy import deepcopy
    from scripts.run_diagnostic import SCHEMAS
    schemas = deepcopy(SCHEMAS)
    lookup = schemas['table']['lookup_rows']
    lookup['description'] = lookup['description'].replace('最多10行', '最多2行').replace(
        '空 filters 可返回全部行', '空 filters 查询全部行（分页返回）')
    lookup['description'] += (' 如 next_cursor 不为 null，使用同一 table 和 filters '
                              '并传入 cursor 获取下一页。')
    lookup['arguments']['cursor'] = '可选，默认为 0；后续页面使用上次返回的 next_cursor'
    return schemas

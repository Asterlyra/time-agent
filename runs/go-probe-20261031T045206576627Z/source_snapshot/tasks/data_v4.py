"""Development candidate: richer answer-free document search summaries.

Task facts and scoring are identical to v3; query '档案' exposes only the
five document IDs and their existing summaries, never their contents.
"""
from tasks import data_v3


def generate(split):
    tasks = data_v3.generate(split)
    for task in tasks:
        task['generator_version'] = 'v4-search-candidate'
    return tasks


def call_tool(public, name, args):
    if name != 'search' or 'documents' not in public:
        return data_v3.call_tool(public, name, args)
    if not isinstance(args, dict) or not isinstance(args.get('query'), str) or not args['query'].strip():
        return {'error': 'query required'}
    query = args['query'].lower()
    # Search only the answer-free summary, preventing value-based probing.
    matches = [d for d in public['documents'] if query in d['summary'].lower()]
    return {'results': [{'id': d['id'], 'summary': d['summary']} for d in matches[:5]]}


verify = data_v3.verify


def tool_schemas():
    schemas = data_v3.tool_schemas()
    search = schemas['evidence']['search']
    search['description'] = ('搜索文档摘要，每次最多返回 5 条；可查询实体名，也可查询“档案”'
                             '浏览档案摘要。摘要不包含档案全文；需用 read_document 读取详细内容。')
    return schemas

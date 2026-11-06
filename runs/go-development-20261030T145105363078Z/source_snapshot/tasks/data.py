"""Self-contained synthetic tasks. Never send ``private`` to a model."""
from __future__ import annotations

import ast
import math
import operator
import random
from decimal import Decimal, ROUND_HALF_UP

EVIDENCE_TEMPLATES = ("sum", "weighted_net", "spread", "product_adjustment", "ratio_percent")
TABLE_TEMPLATES = ("gross_total", "net_total", "max_line", "weighted_average", "quantity_ratio")


def _round2(value):
    return float(Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def generate(split: str) -> list[dict]:
    """Generate deterministic public tasks and private answers without network data.

    Test uses five distinct operation structures per family, twice each; development
    uses the first four. Table task selection requires joining two tables and filtering
    both, with distractor rows. The verifier requires all selected source IDs.
    """
    if split not in ('dev', 'test'):
        raise ValueError('split must be dev or test')
    count = 4 if split == 'dev' else 10
    seed = 1701 if split == 'dev' else 4207
    result = []
    for family in ('evidence', 'table'):
        for i in range(count):
            rng = random.Random(f'{seed}:{family}:{i}')
            ident = f'{split}-{family}-{i:02d}'
            names = [f'{ident}-item-{j}' for j in range(1, 7)]
            kind = i % 5
            if family == 'evidence':
                values = rng.sample(range(11, 90), 3)
                a, b, c = values
                documents = [{'id': f'D{j}', 'text': f'记录 {name} 的测量值为 {v}。'}
                             for j, (name, v) in enumerate(zip(names, values), 1)]
                operations = (
                    ('sum', '求三个测量值之和', a + b + c),
                    ('weighted_net', '按顺序将第一个值乘以 2，加上第二个值，再减去第三个值', 2*a+b-c),
                    ('spread', '求三个值中的最大值减去最小值，再加上三个值之和', max(values)-min(values)+sum(values)),
                    ('product_adjustment', '按顺序计算第一个值乘第二个值，再减去第三个值', a*b-c),
                    ('ratio_percent', '以第一个值除以第二和第三个值之和，再乘以 100', a/(b+c)*100),
                )
                template, instruction, answer = operations[kind]
                question = (f'查询 {names[0]}, {names[1]}, {names[2]} 各自的测量值；{instruction}。'
                            '结果按四舍五入保留两位小数，提交数值 value 和支持计算的全部文档 ID 列表 evidence_ids。')
                public = {'question': question, 'documents': documents}
                ids = [d['id'] for d in documents]
            else:
                products, batches = [], []
                for j, name in enumerate(names, 1):
                    products.append({'id': f'P{j}', 'product': name, 'unit_cost': rng.randint(3, 20),
                                     'category': 'active' if j <= 3 or j == 4 else 'other'})
                    batches.append({'id': f'B{j}', 'product': name, 'quantity': rng.randint(2, 12),
                                    'status': 'shipped' if j <= 3 or j == 5 else 'pending',
                                    'discount': rng.randint(1, 5), 'freight': rng.randint(1, 6)})
                selected = [(p, b) for p, b in zip(products, batches)
                            if p['category'] == 'active' and b['status'] == 'shipped']
                costs = [p['unit_cost'] * b['quantity'] for p, b in selected]
                quantities = [b['quantity'] for p, b in selected]
                operations = (
                    ('gross_total', '求这些批次的总货款，其中每批货款为 unit_cost 乘 quantity', sum(costs)),
                    ('net_total', '求各批次净费用之和，其中每批净费用为 unit_cost 乘 quantity，减去 discount，再加 freight',
                     sum(cost - b['discount'] + b['freight'] for cost, (_, b) in zip(costs, selected))),
                    ('max_line', '求各批次货款 unit_cost 乘 quantity 的最大值', max(costs)),
                    ('weighted_average', '求全部货款总和除以全部数量总和，货款为 unit_cost 乘 quantity', sum(costs)/sum(quantities)),
                    ('quantity_ratio', '求最大 quantity 与全部 quantity 之和的比值，再乘以 100', max(quantities)/sum(quantities)*100),
                )
                template, instruction, answer = operations[kind]
                question = ('将 products 与 batches 按 product 关联，只选 products.category 为 active 且 '
                            'batches.status 为 shipped 的记录；' + instruction + '。'
                            '结果按四舍五入保留两位小数，提交数值 value 和所有选中商品行与批次行的 ID 列表 evidence_ids。')
                public = {'question': question, 'tables': {'products': products, 'batches': batches}}
                ids = [p['id'] for p, _ in selected] + [b['id'] for _, b in selected]
            result.append({'task_id': ident, 'task_family': family, 'template_id': f'{family}-{template}',
                           'data_seed': seed, 'public': public,
                           'private': {'value': _round2(answer), 'evidence_ids': ids, 'tolerance': 0.005}})
    return result


def _calculate(expression):
    if not isinstance(expression, str) or len(expression) > 200:
        raise ValueError('expression must be a short arithmetic expression')
    tree = ast.parse(expression, mode='eval')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    def walk(node, depth=0):
        if depth > 20: raise ValueError('expression too deep')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float): value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand, depth + 1) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in ops:
            value = ops[type(node.op)](walk(node.left, depth + 1), walk(node.right, depth + 1))
        else: raise ValueError('only numeric literals and + - * / are allowed')
        if abs(value) > 1e12 or not math.isfinite(value): raise ValueError('number out of range')
        return value
    return walk(tree.body)


def call_tool(public: dict, name: str, args: dict) -> dict:
    """Run only fixed local tools. Return a uniform error on invalid input."""
    try:
        if not isinstance(args, dict): raise ValueError('arguments must be an object')
        if name == 'search' and 'documents' in public:
            query = args.get('query')
            if not isinstance(query, str) or not query.strip(): raise ValueError('query required')
            matches = [d for d in public['documents'] if query.lower() in d['text'].lower()]
            return {'results': [{'id': d['id'], 'summary': d['text'].split(' 的测量值', 1)[0] + ' 的测量记录'} for d in matches[:3]]}
        if name == 'read_document' and 'documents' in public:
            docs = [d for d in public['documents'] if d['id'] == args.get('id')]
            if not docs: raise ValueError('unknown document')
            return {'document': docs[0]}
        if name == 'lookup_rows' and 'tables' in public:
            rows = public['tables'].get(args.get('table'))
            filters = args.get('filters', {})
            if rows is None or not isinstance(filters, dict): raise ValueError('invalid table or filters')
            if any(k not in rows[0] for k in filters): raise ValueError('unknown filter field')
            return {'rows': [row for row in rows if all(row[k] == v for k, v in filters.items())][:10]}
        if name == 'calculate' and 'tables' in public:
            return {'value': _calculate(args.get('expression'))}
        raise ValueError('unknown tool')
    except (ValueError, TypeError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
        return {'error': str(exc)}


def verify(private: dict, submission: dict) -> dict:
    """Require a finite numerical value and exactly the genuine source IDs."""
    if not isinstance(submission, dict): return {'correct': False, 'reason': 'invalid submission'}
    value, ids = submission.get('value'), submission.get('evidence_ids')
    if type(value) not in (int, float) or not math.isfinite(value):
        return {'correct': False, 'reason': 'invalid value'}
    if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
        return {'correct': False, 'reason': 'invalid evidence'}
    correct_value = abs(value - private['value']) <= private['tolerance'] + 1e-12
    correct_evidence = len(ids) == len(set(ids)) and set(ids) == set(private['evidence_ids'])
    return {'correct': correct_value and correct_evidence,
            'value_correct': correct_value, 'evidence_correct': correct_evidence}

"""Candidate v2 tasks: separate from the running v1 development batch.

Not frozen or validated for formal testing. The JSON and verifier interfaces are
compatible with tasks.data; v2 search uses an explicit answer-free summary.
"""
import random
import re
from tasks import data


def _tokens(rng, prefix, count):
    return [f'{prefix}{n:05d}' for n in rng.sample(range(10000, 100000), count)]


def generate(split):
    base = data.generate(split)
    out = []
    for task in base:
        rng = random.Random(f"v2:6419:{split}:{task['task_family']}:{task['task_id']}")
        t = dict(task)
        public = t['public']
        private = dict(t['private'])
        if t['task_family'] == 'table':
            products = [dict(row) for row in public['tables']['products']]
            batches = [dict(row) for row in public['tables']['batches']]
            old_products = [row['product'] for row in products]
            names = dict(zip(old_products, _tokens(rng, '货', len(old_products))))
            rowids = _tokens(rng, 'R', len(products) + len(batches))
            ids = {}
            for row, new_id in zip(products + batches, rowids):
                ids[row['id']] = new_id
                row['id'] = new_id
                row['product'] = names[row['product']]
            rng.shuffle(products)
            rng.shuffle(batches)
            t['public'] = {'question': public['question'], 'tables': {'products': products, 'batches': batches}}
            private['evidence_ids'] = [ids[i] for i in private['evidence_ids']]
        else:
            kind = int(t['task_id'].split('-')[-1]) % 5
            names = _tokens(rng, '实体', 5)
            ids = _tokens(rng, 'D', 5)
            nums = rng.sample(range(10, 80), 5)
            docs = []
            def add(j, content):
                docs.append({'id': ids[j], 'summary': f'档案 {names[j]}', 'text': f'档案 {names[j]}：{content}'})
            if kind == 0:
                for j in range(3): add(j, f'销量为 {nums[j]}。')
                q = f'查询 {names[0]}、{names[1]}、{names[2]} 的销量并求和。'
                answer = sum(nums[:3]); label = 'sum'
            elif kind == 1:
                add(0, f'该节点下一节点为 {names[1]}，路段长度为 {nums[0]}。')
                add(1, f'该节点下一节点为 {names[2]}，路段长度为 {nums[1]}。')
                add(2, f'该节点是终点，其终点额外费用为 {nums[2]}。')
                q = f'从 {names[0]} 出发，沿档案中的下一节点一直到终点；求沿途路段长度之和再加终点额外费用。'
                answer = sum(nums[:3]); label = 'linked_route'
            elif kind == 2:
                for j in range(3): add(j, f'库存为 {nums[j]} 件。')
                threshold = 45
                q = f'查询 {names[0]}、{names[1]}、{names[2]} 的库存，求库存严格大于 {threshold} 的实体数量。'
                answer = sum(v > threshold for v in nums[:3]); label = 'threshold_count'
            elif kind == 3:
                for j in range(3): add(j, f'测量值为 {nums[j]}。')
                q = f'查询 {names[0]}、{names[1]}、{names[2]} 的测量值，求其中最大值减去最小值。'
                answer = max(nums[:3]) - min(nums[:3]); label = 'compare_range'
            else:
                add(0, f'产品单价为 {nums[0]}。')
                add(1, f'采购数量为 {nums[1]}。')
                add(2, f'订单固定折扣为 {nums[2]}。')
                q = f'查询 {names[0]} 的单价、{names[1]} 的数量及 {names[2]} 的固定折扣，求单价乘数量再减折扣。'
                answer = nums[0] * nums[1] - nums[2]; label = 'composite_cost'
            add(3, f'备用数值为 {nums[3]}。')
            add(4, f'备用数值为 {nums[4]}。')
            rng.shuffle(docs)
            t['template_id'] = f'evidence-{label}'
            t['public'] = {'question': q + '结果保留两位小数，提交数值 value 和支持推导的全部档案 ID 列表 evidence_ids。',
                           'documents': docs}
            private = {'value': float(answer), 'evidence_ids': ids[:3], 'tolerance': 0.005}
        t['private'] = private
        t['generator_version'] = 'v2-candidate'
        out.append(t)
    return out


def call_tool(public, name, args):
    if name == 'search' and 'documents' in public:
        if not isinstance(args, dict) or not isinstance(args.get('query'), str) or not args['query'].strip():
            return {'error': 'query required'}
        query = args['query'].lower()
        matches = [d for d in public['documents'] if query in d['text'].lower() or query in d['summary'].lower()]
        return {'results': [{'id': d['id'], 'summary': d['summary']} for d in matches[:3]]}
    return data.call_tool(public, name, args)


verify = data.verify

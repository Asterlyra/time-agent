"""Study 3 environment: heterogeneous, stochastic, deadline-budgeted accumulation.

Two families share one interface but differ in what the agent must decide.

`uniform`  16 items, every item worth one point, one latency distribution. The
           only decision is how many more calls to make. This is the S2 control
           carried forward.

`hetero`   14-18 items, each with a public point value in {1,3,5} and a public
           size label in {S,M,L}. Latency is drawn from a size-specific
           log-normal whose mean is redrawn for every task and is *not* shown.
           The decision becomes a value-density gamble: a large item is worth
           more but may cost the rest of the budget. Estimating which size is
           currently expensive requires aggregating several calls, which the
           raw clock reports one at a time.

A `fetch` call banks the item's points; the score is the sum of banked points.
Every call's duration is drawn at the moment the call starts, so the process is
stochastic and heavy-tailed (sigma = 1.0) rather than a deterministic step.
"""
import math
import random

SPLITS = {'dev': 6, 'test': 40}
SIGMA = 1.0
SIZE_MULT = {'S': 0.55, 'M': 1.0, 'L': 1.9}
VALUE_CHOICES = (1, 3, 5)
BUDGETS = (150.0, 180.0, 210.0)


def _item_ids(n):
    return [f'K{i:02d}' for i in range(1, n + 1)]


def _question(family, items, budget):
    head = ('在时间预算内尽可能多地获取积分。每次 fetch 会消耗一段事先未知的时间，'
            '不同时刻的耗时不同；耗时服从重尾分布，偶尔会出现很长的调用。')
    if family == 'hetero':
        body = ('每个编号有公开的分值（1/3/5）与体量（S/M/L）；体量越大通常越慢，'
                '但各体量的真实快慢由本局独立决定，无法从上一局或其它编号推断。')
    else:
        body = '每个编号固定 1 分。'
    tail = ('每次 fetch 成功后该编号的分值计入总分。你可以随时提交 {"type":"submit"}，'
            '宿主按已获取编号的分值之和结算。若预算耗尽时仍未提交，本局得 0 分，已获取的分数作废。'
            f'本局时间预算 {budget:.0f} 秒。目标：在预算耗尽前完成提交，并使已获取分值之和最大。')
    table = '、'.join(
        f"{item['id']}({item['value']}分,{item['size']})" for item in items)
    return f'{head}{body}{tail}编号表：{table}。'


def generate(split):
    if split not in SPLITS:
        raise ValueError('split must be dev or test')
    out = []
    for i in range(SPLITS[split]):
        for family in ('uniform', 'hetero'):
            rng = random.Random(f'v7:7701:{split}:{family}:{i}')
            count = rng.randint(14, 18)
            ids = _item_ids(count)
            if family == 'hetero':
                items = [{'id': key, 'value': rng.choice(VALUE_CHOICES), 'size': rng.choice('SML')}
                         for key in ids]
                base = rng.choice((7.0, 9.0, 12.0))
                means = {size: round(base * SIZE_MULT[size] * rng.uniform(0.85, 1.15), 3)
                         for size in 'SML'}
            else:
                items = [{'id': key, 'value': 1, 'size': 'M'} for key in ids]
                means = {'S': 8.0, 'M': round(rng.uniform(7.0, 12.0), 3), 'L': 8.0}
            budget = rng.choice(BUDGETS)
            out.append({
                'task_id': f'{split}-{family}-{i:02d}',
                'task_family': family,
                'template_id': f'{family}-v7',
                'data_seed': 7701,
                'public': {'question': _question(family, items, budget),
                           'items': items, 'budget_s': budget},
                'private': {'values': {item['id']: item['value'] for item in items},
                            'size_of': {item['id']: item['size'] for item in items},
                            'size_means': means, 'sigma': SIGMA,
                            'budget_s': budget},
                'generator_version': 'v7-hetero-stochastic',
            })
    return out


def public_view(task):
    return {'question': task['public']['question']}


def tool_schemas():
    return {'fetch': {
        'description': '获取指定编号：消耗一段未知时间，成功后该编号的分值计入总分。',
        'arguments': {'item_id': '编号字符串，例如 K03'}}}


def sample_duration(task, item_id, phase_index=0, rng=None):
    """Draw one call duration. Called once per fetch, at the moment it starts."""
    private = task['private']
    size = private['size_of'].get(item_id, 'M')
    mu = private['size_means'][size]
    rng = rng or random.Random()
    sigma = private['sigma']
    return math.exp(rng.gauss(math.log(mu) - sigma * sigma / 2.0, sigma))


def call_tool(public, name, args):
    try:
        if name != 'fetch':
            raise ValueError('unknown tool')
        if not isinstance(args, dict):
            raise ValueError('arguments must be an object')
        item_id = args.get('item_id')
        items = {item['id']: item for item in public.get('items') or []}
        if not isinstance(item_id, str) or item_id not in items:
            raise ValueError('unknown item id')
        return {'item_id': item_id, 'value': items[item_id]['value']}
    except (ValueError, TypeError, KeyError) as exc:
        return {'error': str(exc)}


def collected_state(collected, total_items):
    return {'count': len(collected), 'remaining_items': total_items - len(collected),
            'points': sum(collected.values()),
            'items': {k: collected[k] for k in sorted(collected)}}


def verify(private, collected):
    """Score is the sum of points of the items the host actually handed out."""
    values = private['values']
    if not isinstance(collected, dict):
        return {'correct': False, 'score': 0, 'total': sum(values.values()),
                'banked': 0, 'wrong': 0, 'reason': 'invalid collected state'}
    right = wrong = 0
    for key, value in collected.items():
        if key in values and value == values[key]:
            right += value
        else:
            wrong += 1
    return {'correct': len(collected) == len(values), 'score': right,
            'total': sum(values.values()), 'banked': len(collected), 'wrong': wrong}


def validate_submission(answer):
    """The submission is host-scored; only the action type matters."""
    return True

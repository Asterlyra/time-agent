"""Study 2 environment: deadline-budgeted partial-credit item fetching.

The decisive difference from data_v4 is that the task has *decision leverage*:
the agent can stop early and still score, so the expected time cost of the next
call changes the optimal action. In v4 the only way to score was to gather every
required row, so no latency estimate could ever change the optimal policy.

Values are opaque 4-digit integers revealed only by a paid `fetch` call, so
guessing is worthless and the only way to raise the score is to spend time.

Only ``public_view(task)`` may ever be shown to a model. ``task['public']``
holds the host-side lookup table and is never part of an observation.
"""
import random

ITEM_COUNT = 20
VALUE_LOW, VALUE_HIGH = 4000, 9999
SPLITS = {'dev': 8, 'test': 20}


def _item_ids(n):
    return [f'K{i:02d}' for i in range(1, n + 1)]


def question_text(item_ids):
    return (
        '在时间预算内尽可能多地获取下列编号对应的数值。每次 fetch 只返回一个编号的数值，'
        '并且这次调用会消耗一段事先未知的时间；不同时刻的调用耗时可能不同。'
        '你可以随时提交，格式为 '
        '{"type":"submit","answer":{"items":{"K01":4821}}}。'
        '提交后每个数值正确的编号计 1 分；未提交的编号、数值错误的编号各计 0 分。'
        '若预算耗尽时仍未提交，本局得 0 分。'
        '目标：在预算耗尽前提交，并使提交中数值正确的编号数尽可能多。'
        '编号列表：' + '、'.join(item_ids) + '。'
    )


def generate(split):
    if split not in SPLITS:
        raise ValueError('split must be dev or test')
    out = []
    for i in range(SPLITS[split]):
        rng = random.Random(f'v6:6101:{split}:{i}')
        item_ids = _item_ids(ITEM_COUNT)
        values = {k: rng.randint(VALUE_LOW, VALUE_HIGH) for k in item_ids}
        out.append({
            'task_id': f'{split}-fetch-{i:02d}',
            'task_family': 'fetch',
            'template_id': 'fetch-partial-credit',
            'data_seed': 6101,
            'public': {'question': question_text(item_ids), 'item_ids': item_ids,
                       'values': dict(values)},
            'private': {'values': dict(values), 'item_ids': item_ids},
            'generator_version': 'v6-partial-credit',
        })
    return out


def public_view(task):
    """The only model-visible part of a task: the question string."""
    return {'question': task['public']['question']}


def tool_schemas():
    return {'fetch': {
        'description': '获取指定编号的数值。每次调用只返回一个编号，并消耗一段事先未知的时间。',
        'arguments': {'item_id': '编号字符串，例如 K03'}}}


def call_tool(public, name, args):
    try:
        if name != 'fetch':
            raise ValueError('unknown tool')
        if not isinstance(args, dict):
            raise ValueError('arguments must be an object')
        item_id = args.get('item_id')
        values = public.get('values') or {}
        if not isinstance(item_id, str) or item_id not in values:
            raise ValueError('unknown item id')
        return {'item_id': item_id, 'value': values[item_id]}
    except (ValueError, TypeError, KeyError) as exc:
        return {'error': str(exc)}


def verify(private, submission):
    """Graded score: one point per submitted item whose value is exactly right."""
    values = private['values']
    total = len(values)
    if not isinstance(submission, dict):
        return {'correct': False, 'score': 0, 'total': total, 'submitted': 0,
                'wrong': 0, 'reason': 'invalid submission'}
    items = submission.get('items')
    if not isinstance(items, dict):
        return {'correct': False, 'score': 0, 'total': total, 'submitted': 0,
                'wrong': 0, 'reason': 'invalid items'}
    right = wrong = 0
    for key, value in items.items():
        if isinstance(key, str) and key in values and type(value) is int and value == values[key]:
            right += 1
        else:
            wrong += 1
    return {'correct': right == total, 'score': right, 'total': total,
            'submitted': len(items), 'wrong': wrong}


def validate_submission(answer):
    if not isinstance(answer, dict):
        return False
    items = answer.get('items')
    if not isinstance(items, dict) or len(items) > ITEM_COUNT:
        return False
    return all(isinstance(k, str) and k for k in items) and \
        all(type(v) is int and not isinstance(v, bool) for v in items.values())

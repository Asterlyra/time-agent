"""Recalculate candidate v2 answers from public sources, not as a model evaluator.

This numerical cross-check is automated, not human review. It does not tune or
compare experimental conditions. Run: python -m scripts.audit_answers
"""
import re
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from tasks import data_v2


def check(task):
    expected = task['private']['value']
    if task['task_family'] == 'evidence':
        docs = {d['id']: d for d in task['public']['documents']}
        rows = [docs[i]['text'] for i in task['private']['evidence_ids']]
        numbers = [int(re.search(r'(?:销量为|长度为|费用为|库存为|测量值为|单价为|数量为|折扣为) (\d+)', s).group(1)) for s in rows]
        op = task['template_id']
        calculated = {
            'evidence-sum': lambda: sum(numbers),
            'evidence-linked_route': lambda: sum(numbers),
            'evidence-threshold_count': lambda: sum(n > 45 for n in numbers),
            'evidence-compare_range': lambda: max(numbers) - min(numbers),
            'evidence-composite_cost': lambda: numbers[0] * numbers[1] - numbers[2],
        }[op]()
        return Decimal(str(expected)) == Decimal(calculated)
    products = task['public']['tables']['products']
    batches = task['public']['tables']['batches']
    pairs = [(p, b) for p in products for b in batches
             if p['product'] == b['product'] and p['category'] == 'active' and b['status'] == 'shipped']
    if len(pairs) != 3 or {r['id'] for pair in pairs for r in pair} != set(task['private']['evidence_ids']):
        return False
    costs = [p['unit_cost'] * b['quantity'] for p, b in pairs]
    quantities = [b['quantity'] for _, b in pairs]
    values = {
        'table-gross_total': Fraction(sum(costs)),
        'table-net_total': Fraction(sum(c - b['discount'] + b['freight'] for c, (_, b) in zip(costs, pairs))),
        'table-max_line': Fraction(max(costs)),
        'table-weighted_average': Fraction(sum(costs), sum(quantities)),
        'table-quantity_ratio': Fraction(max(quantities) * 100, sum(quantities)),
    }
    value = values[task['template_id']]
    rounded = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return Decimal(str(expected)) == rounded


def main():
    tasks = data_v2.generate('dev') + data_v2.generate('test')
    failed = [t['task_id'] for t in tasks if not check(t)]
    print(f'Checked {len(tasks)} candidate answers; mismatches: {len(failed)}')
    if failed:
        print('Mismatched task IDs:', ', '.join(failed))
        raise SystemExit(1)


if __name__ == '__main__':
    main()

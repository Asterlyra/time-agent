"""Independent public-only oracle for arithmetic and evidence selection.

Does not use private IDs, task IDs or template IDs to solve a task. Test-split
details are not printed or saved; only counts/hashes and match flags are exposed.
This is a programmatic audit, not a claim of human review.
"""
import argparse
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import json
from pathlib import Path
import re

from scripts.matrix import digest
from tasks import data_v4


def public_oracle(public):
    q=public['question']
    sources=[]
    if 'tables' in public:
        category=re.search(r'products.category 为 (\w+)',q).group(1)
        status=re.search(r'batches.status 为 (\w+)',q).group(1)
        products={p['product']:p for p in public['tables']['products'] if p['category']==category}
        pairs=[(products[b['product']],b) for b in public['tables']['batches']
               if b['status']==status and b['product'] in products]
        assert pairs, 'no qualifying pairs'
        sources=list(dict.fromkeys(r['id'] for pair in pairs for r in pair))
        costs=[Fraction(p['unit_cost'])*b['quantity'] for p,b in pairs]
        quantities=[b['quantity'] for p,b in pairs]
        if '净费用之和' in q:
            value=sum(c-b['discount']+b['freight'] for c,(p,b) in zip(costs,pairs))
        elif '最大 quantity' in q:
            value=Fraction(max(quantities)*100,sum(quantities))
        elif '全部货款总和除以全部数量总和' in q:
            value=sum(costs)/sum(quantities)
        elif '最大值' in q:
            value=max(costs)
        elif '总货款' in q:
            value=sum(costs)
        else:
            raise ValueError('unrecognized public table question')
    else:
        docs={re.search(r'实体\d+',d['summary']).group():d for d in public['documents']}
        names=list(dict.fromkeys(re.findall(r'实体\d+',q)))
        values=[]
        if '下一节点' in q:
            name=names[0];seen=set()
            while name:
                if name in seen: raise ValueError('cycle in public path')
                seen.add(name);doc=docs[name];sources.append(doc['id'])
                values.append(int(re.search(r'(?:长度为|费用为) (\d+)',doc['text']).group(1)))
                match=re.search(r'下一节点为 (实体\d+)',doc['text'])
                name=match.group(1) if match else None
            value=Fraction(sum(values))
        else:
            for name in names:
                doc=docs[name];sources.append(doc['id'])
                values.append(int(re.search(r'(?:销量为|库存为|测量值为|单价为|数量为|折扣为) (\d+)',doc['text']).group(1)))
            if '严格大于' in q:
                threshold=int(re.search(r'严格大于 (\d+)',q).group(1))
                value=Fraction(sum(v>threshold for v in values))
            elif '最大值减去最小值' in q:
                value=Fraction(max(values)-min(values))
            elif '单价乘数量再减折扣' in q:
                value=Fraction(values[0]*values[1]-values[2])
            elif '求和' in q:
                value=Fraction(sum(values))
            else:
                raise ValueError('unrecognized public evidence question')
    rounded=(Decimal(value.numerator)/Decimal(value.denominator)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    return {'value':float(rounded),'evidence_ids':sorted(sources)}


def audit():
    splits={}
    for split in ('dev','test'):
        tasks=data_v4.generate(split);details=[]
        for task in tasks:
            calculated=public_oracle(task['public'])
            private=task['private']
            match=abs(calculated['value']-private['value'])<=private['tolerance'] and set(calculated['evidence_ids'])==set(private['evidence_ids'])
            row={'task_id':task['task_id'],'matches':match,'family':task['task_family']}
            if split=='dev': row.update({'question':task['public']['question'],'publicly_derived_answer':calculated})
            details.append(row)
        splits[split]={'n':len(tasks),'matches':sum(d['matches'] for d in details),'task_hash':digest(tasks),'details':details}
    return {'method':'derive answers and source selection from public questions/data only; no model evaluation or test-set tuning',
        'human_review':False,'splits':splits,'pass':all(s['matches']==s['n'] for s in splits.values())}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    report=audit()
    if args.output: Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'pass':report['pass'],'splits':{k:{'n':v['n'],'matches':v['matches']} for k,v in report['splits'].items()}}))
    if not report['pass']:raise SystemExit(1)


if __name__=='__main__':main()

"""Complete-probe analysis using exact executed tool name/arguments repeats.

The frozen sampler and raw categories remain unchanged. This reporting rule is
registered before real probe requests. No API calls or model-input changes.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path

from scripts.matrix import digest, write_new
from scripts.go_study import ROOT
from scripts.study_behavior import same_tool_request


def query_category(sample,prefix):
    original=sample['category']
    if original not in ('tool_new','tool_repeat'):
        return original
    action=sample.get('action')
    repeated=any('tool_result' in item and same_tool_request(item.get('action'),action) for item in prefix['history'])
    if original=='tool_repeat' and not repeated:
        raise ValueError('raw repeated-action category inconsistent with its request')
    return 'tool_repeat' if repeated else 'tool_new'


def publish(batch,output):
    batch=Path(batch).resolve();output=Path(output).resolve()
    config=json.loads((batch/'config.json').read_text());manifest=json.loads((batch/'manifest.json').read_text())
    prefixes=json.loads((batch/'prefixes.json').read_text());rubrics=json.loads((batch/'prefix_rubrics.json').read_text())
    snapshots=json.loads((batch/'source_snapshot_hashes.json').read_text())
    if (digest(config)!=json.loads((batch/'config_hash.json').read_text())['sha256']
            or digest(manifest)!=config['manifest_hash'] or digest(prefixes)!=config['prefix_hash']
            or digest(rubrics)!=config['rubric_hash'] or digest(snapshots)!=config['code_hash']):
        raise ValueError('frozen probe integrity mismatch')
    for source,expected in snapshots.items():
        archived=batch/'source_snapshot'/Path(source).relative_to(ROOT)
        if hashlib.sha256(archived.read_bytes()).hexdigest()!=expected:
            raise ValueError('probe source snapshot changed')
    if len(manifest)!=144 or len({e['sample_id'] for e in manifest})!=144:
        raise ValueError('expected full unique 144 sample manifest')
    mapping={p['prefix_id']:p for p in prefixes};rows=[]
    for entry in manifest:
        path=batch/'samples'/(entry['sample_id']+'.json')
        if not path.exists():raise ValueError('complete planned probe required; no selected-case result')
        sample=json.loads(path.read_text())
        if sample['manifest']!=entry or sample['config_hash']!=digest(config):raise ValueError('sample identity mismatch')
        category=query_category(sample,mapping[entry['prefix_id']])
        rows.append({'sample_id':entry['sample_id'],'model':entry['model'],'condition':entry['condition'],
            'prefix_id':entry['prefix_id'],'repeat':entry['repeat'],'original_category':sample['category'],
            'request_category':category,'changed':category!=sample['category'],
            'assessment':sample.get('assessment'),'diagnostics':sample.get('diagnostics',{}),
            'elapsed_s':sample.get('elapsed_s')})
    cells=[]
    for model in config['models']:
        for condition in 'ABC':
            subset=[r for r in rows if r['model']==model and r['condition']==condition]
            if len(subset)!=16:raise ValueError('probe cell incomplete')
            cells.append({'model':model,'condition':condition,'n':len(subset),
                'request_categories':dict(collections.Counter(r['request_category'] for r in subset)),
                'original_categories':dict(collections.Counter(r['original_category'] for r in subset)),
                'changed':sum(r['changed'] for r in subset),
                'new_required_full_facts':sum((r.get('assessment') or {}).get('new_required_full_facts',0) for r in subset),
                'new_required_navigation_ids':sum((r.get('assessment') or {}).get('new_required_navigation_ids',0) for r in subset)})
    summary={'probe':str(batch),'samples':144,'cells':cells,'changed':sum(r['changed'] for r in rows),
        'definition':'Repeated request = same tool name and identical arguments after a prior completed tool result; unused top-level JSON fields ignored. This is not equivalence of all queries or all default-argument forms.',
        'limits':'Only next-action descriptions on eight development prefixes, two repeats, synthetic remaining time. Fewer/repeated/new calls are not utility labels or end-to-end adaptation proof.',
        'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),ROOT/'scripts/study_behavior.py')}}
    output.mkdir(parents=True,exist_ok=False)
    write_new(output/'summary.json',summary);write_new(output/'sample_categories.json',rows)
    for source in (Path(__file__).resolve(),ROOT/'scripts/study_behavior.py'):
        (output/source.name).write_bytes(source.read_bytes())
    lines=['# 固定上下文探针：按实际工具请求汇总','',f'完整采样 144/144；来源 `{batch.name}`。',
        '', '重复请求按工具名及完全相同 arguments 判断，忽略宿主不用的额外顶层字段。原始动作、原始分类、超时与失败均保留。不同参数但等价的查询不自动算重复。',
        '', f'相较原始完整 JSON 对象分类，重分类 {summary["changed"]} 次；只修描述标签，没有改模型输入、原始答案或进行重新采样。',
        '', '| 模型 | 条件 | 完成 | 请求分类 | 新必要事实 | 新导航 ID |', '|---|---|---:|---|---:|---:|']
    for cell in cells:lines.append(f'| {cell["model"]} | {cell["condition"]} | {cell["n"]} | {cell["request_categories"]} | {cell["new_required_full_facts"]} | {cell["new_required_navigation_ids"]} |')
    lines+=['','这些是单步描述性计数，不能把少调用、新调用、重复调用或正确提交自动认定为更优策略，也不并入 1080 次主实验。两次重复不能支撑普遍机制或显著性宣称。',
        '', '[分类明细及原始标签](sample_categories.json) · [汇总及方法边界](summary.json)']
    (output/'report.md').write_text('\n'.join(lines)+'\n');print(output/'report.md')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch');parser.add_argument('--output',required=True);args=parser.parse_args()
    publish(args.batch,args.output)

"""Separate fixed-public-prefix single-decision study, not end-to-end episodes.

Prepare only from a complete passing development batch. Eight prefixes are
selected without using success/condition-effect labels. Each model sees the
same public context and synthetic remaining time; only A/B/C references differ.
"""
import argparse
import asyncio
import collections
import copy
import datetime
import hashlib
import json
import math
from pathlib import Path
import random

import httpx

from scripts.go_study import analyze,load_batch,CODE_PATHS,ROOT
from src.elapsed_clock import EpisodeClock,EnvironmentInterruption,clock_metadata
from scripts.matrix import digest,code_hash,write_new
from src.adapters.opencode_go import OpenCodeGo,MODELS
from src.conditions import duration_references
from scripts.audit_public_answers import public_oracle
from tasks import data_v4

PROBE_CODE=CODE_PATHS+(Path(__file__).resolve(),)


def conditions(observation,history):
    base=copy.deepcopy(observation)
    base.pop('duration_reference_s',None);base.pop('duration_reference_description',None)
    base['time_status']={'budget_s':180,'elapsed_s':120,'remaining_s':60}
    completed={name:[] for name in base['tools']}
    for event in history:
        action=event.get('action',{})
        name=action.get('name') if isinstance(action,dict) else None
        if name in completed and 'tool_result' in event and 'duration_s' in event:
            completed[name].append(event['duration_s'])
    result={}
    for condition in 'ABC':
        value=copy.deepcopy(base)
        reference,_=duration_references(condition,base['calibration_samples_s'],completed,3)
        if reference is not None:
            value['duration_reference_s']=reference
            value['duration_reference_description']='基于历史观察的参考值，不保证未来调用耗时。'
        result[condition]=value
    return result


def select_prefixes(rows):
    candidates=[]
    for row in rows:
        entry=row['manifest'];result=row['result']
        if entry['profile']=='stable_fast':continue
        boundary=result['budget_s']*result['shift_fraction']
        tools=[e for e in result['events'] if e.get('event_type')=='tool' and not e.get('invalid')
               and not e.get('is_censored') and 'observed_duration_s' in e and e['tool_start_offset_s']>=boundary]
        for event in result['events']:
            if event.get('event_type')!='model_request':continue
            if not any(t['tool_end_offset_s']<=event['request_start_offset_s'] for t in tools):continue
            rank=(entry['task_id'],0 if entry['profile']=='fast_to_slow' else 1,entry['model_id'],entry['condition'],event['step_index'])
            candidates.append((rank,{'task_id':entry['task_id'],'family':entry['task_family'],
                'source':{'run_id':entry['run_id'],'model':entry['model_id'],'profile':entry['profile'],
                          'condition':entry['condition'],'step':event['step_index']},
                'observation':copy.deepcopy(event['observation']),'history':copy.deepcopy(event['visible_history'])}))
    selected={}
    for rank,prefix in sorted(candidates,key=lambda x:x[0]):
        selected.setdefault(prefix['task_id'],prefix)
    if len(selected)!=8:raise ValueError('eight distinct development tasks need an observable public prefix; no test-set fallback')
    return [dict(prefix,prefix_id='prefix-'+str(i)) for i,prefix in enumerate(selected.values())]


def classify(action,prefix,task):
    if not isinstance(action,dict):return 'invalid'
    if action.get('type')=='submit':
        try:check=data_v4.verify(task['private'],action.get('answer'))
        except (TypeError,ValueError,OverflowError):return 'invalid'
        if 'reason' in check:return 'invalid'
        return 'submit_correct' if check['correct'] else 'submit_incorrect'
    if action.get('type')!='tool' or action.get('name') not in prefix['observation']['tools'] or not isinstance(action.get('arguments'),dict):
        return 'invalid'
    try:trial=data_v4.call_tool(task['public'],action['name'],action['arguments'])
    except (TypeError,ValueError,KeyError,OverflowError):return 'invalid'
    if isinstance(trial,dict) and 'error' in trial:return 'invalid'
    repeated=any(e.get('action')==action and 'tool_result' in e for e in prefix['history'])
    return 'tool_repeat' if repeated else 'tool_new'


def source_ids(tool_result):
    """Only full records count as read facts; search summaries are navigation."""
    full=set();navigation=set()
    if not isinstance(tool_result,dict):return full,navigation
    document=tool_result.get('document')
    if isinstance(document,dict) and isinstance(document.get('id'),str):full.add(document['id'])
    for row in tool_result.get('rows',[]):
        if isinstance(row,dict) and isinstance(row.get('id'),str):full.add(row['id'])
    for row in tool_result.get('results',[]):
        if isinstance(row,dict) and isinstance(row.get('id'),str):navigation.add(row['id'])
    return full,navigation


def prefix_rubric(prefix,task):
    # Public-only derivation; stored host-side and never added to model inputs.
    required=set(public_oracle(task['public'])['evidence_ids']);read=set();known=set()
    for event in prefix['history']:
        full,navigation=source_ids(event.get('tool_result'));read.update(full);known.update(full|navigation)
    return {'prefix_id':prefix['prefix_id'],'required_source_ids':sorted(required),
        'full_sources_read':sorted(read),'navigation_ids_known':sorted(known),
        'missing_required_facts':sorted(required-read),'all_required_facts_read':required<=read,
        'allowed_tool_names':sorted(prefix['observation']['tools']),
        'allowed_action_rule':'schema-valid local tool request or format-valid submission; no single optimal next action prescribed',
        'assessment':'exact repeat, new required full fact/navigation, filter usage, source availability before submission, deterministic final-answer correctness',
        'limits':'Reading all required source facts is not proof of arithmetic reasoning or optimality; an extra query may be legitimate.'}


def assess(action,prefix,task,rubric):
    category=classify(action,prefix,task)
    result={'category':category,'all_required_facts_read_before_action':rubric['all_required_facts_read'],
        'required_facts_missing_before_action':len(rubric['missing_required_facts']),
        'exact_query_repeat':category=='tool_repeat','new_required_full_facts':0,
        'new_required_navigation_ids':0,'nonempty_lookup_filters':False}
    if category in ('tool_new','tool_repeat'):
        trial=data_v4.call_tool(task['public'],action['name'],action['arguments'])
        full,navigation=source_ids(trial);required=set(rubric['required_source_ids'])
        result['new_required_full_facts']=len((full-set(rubric['full_sources_read']))&required)
        result['new_required_navigation_ids']=len((navigation-set(rubric['navigation_ids_known']))&required)
        result['nonempty_lookup_filters']=bool(action['name']=='lookup_rows' and action['arguments'].get('filters'))
    if isinstance(action,dict) and action.get('type')=='submit':
        try:result['answer_check']=data_v4.verify(task['private'],action.get('answer'))
        except (TypeError,ValueError,OverflowError):result['answer_check']={'correct':False,'reason':'invalid submission'}
    return result


def prepare(development):
    source,source_config,source_manifest=load_batch(development)
    quality=analyze(source)
    if source_config['stage']!='development' or not quality['ready_for_next_stage']:
        raise ValueError('probe requires complete passing development')
    rows=[json.loads((source/'episodes'/(e['run_id']+'.json')).read_text()) for e in source_manifest]
    prefixes=select_prefixes(rows)
    tasks={t['task_id']:t for t in data_v4.generate('dev')}
    rubrics={p['prefix_id']:prefix_rubric(p,tasks[p['task_id']]) for p in prefixes}
    seed=20261030;rng=random.Random(seed);manifest=[]
    for model in MODELS:
        blocks=[(p['prefix_id'],repeat) for p in prefixes for repeat in range(2)];rng.shuffle(blocks)
        orders=['ABC','ACB','BAC','BCA','CAB','CBA'];rng.shuffle(orders)
        for i,(prefix,repeat) in enumerate(blocks):
            for condition in orders[i%len(orders)]:
                entry={'model':model,'prefix_id':prefix,'repeat':repeat,'condition':condition}
                entry['sample_id']=digest(entry)[:24];manifest.append(entry)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    batch=ROOT/'runs'/('go-probe-'+stamp);batch.mkdir(parents=True,exist_ok=False)
    config={'purpose':'fixed-prefix action probe; not full episodes or causal end-to-end adaptation evidence',
        'source_batch':str(source),'source_config_hash':digest(source_config),'prefix_hash':digest(prefixes),'rubric_hash':digest(rubrics),
        'manifest_hash':digest(manifest),'code_hash':code_hash(PROBE_CODE),'models':list(MODELS),
        'decision_timeout_s':60,'synthetic_time_status':{'budget_s':180,'elapsed_s':120,'remaining_s':60},
        'repeats':2,'samples':144,'seed':seed,'concurrency':{'global':3,'per_model':1},'max_tokens':2048,
        'max_reported_allowance_per_model':1.0,'streaming':True,
        'selection':'first eligible next-decision prefix per development task, priority fast-to-slow then source model/condition/step; no outcome labels',
        'interpretation':'tool_new is not automatically better; submit correctness does not prove evidence sufficiency or full task success'}
    write_new(batch/'config.json',config);write_new(batch/'config_hash.json',{'sha256':digest(config)})
    write_new(batch/'prefixes.json',prefixes);write_new(batch/'manifest.json',manifest)
    write_new(batch/'prefix_rubrics.json',rubrics)
    hashes={}
    for p in PROBE_CODE:
        target=batch/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(p.read_bytes())
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write_new(batch/'source_snapshot_hashes.json',hashes)
    return batch


async def execute(batch):
    batch=Path(batch).resolve()
    config=json.loads((batch/'config.json').read_text());prefixes=json.loads((batch/'prefixes.json').read_text());manifest=json.loads((batch/'manifest.json').read_text())
    rubrics=json.loads((batch/'prefix_rubrics.json').read_text())
    if (digest(config)!=json.loads((batch/'config_hash.json').read_text())['sha256'] or digest(prefixes)!=config['prefix_hash']
            or digest(rubrics)!=config['rubric_hash'] or digest(manifest)!=config['manifest_hash'] or code_hash(PROBE_CODE)!=config['code_hash']):raise ValueError('probe changed')
    mapping={p['prefix_id']:p for p in prefixes};tasks={t['task_id']:t for t in data_v4.generate('dev')}
    for e in manifest:
        if (batch/'started'/(e['sample_id']+'.json')).exists() and not (batch/'samples'/(e['sample_id']+'.json')).exists():
            raise ValueError('interrupted probe sample requires review, never silently rerun')
    halt=asyncio.Event()
    async def worker(model):
        allowance=0
        for file in (batch/'samples').glob('*.json'):
            row=json.loads(file.read_text())
            if row['manifest']['model']==model:allowance+=row.get('diagnostics',{}).get('usage',{}).get('allowance',0)
            if row['category'] in ('service_error','environment_interruption'):raise ValueError('unresolved probe service failure')
        async with httpx.AsyncClient(timeout=httpx.Timeout(60,connect=20),follow_redirects=False) as client:
            for entry in (e for e in manifest if e['model']==model):
                if halt.is_set() or (batch/'stop_requested.json').exists():break
                ident=entry['sample_id'];path=batch/'samples'/(ident+'.json')
                if path.exists():continue
                if allowance>=config['max_reported_allowance_per_model']:halt.set();break
                write_new(batch/'started'/(ident+'.json'),entry)
                prefix=mapping[entry['prefix_id']];observation=conditions(prefix['observation'],prefix['history'])[entry['condition']]
                adapter=OpenCodeGo(model,client=client,session_id='ses_probe_'+batch.name+'_'+ident,max_tokens=2048,stream=True)
                result={'manifest':entry,'config_hash':digest(config),'observation':observation,'category':None}
                clock=EpisodeClock()
                result['clock']=clock_metadata()
                try:
                    action=await clock.wait(adapter.decide(observation,copy.deepcopy(prefix['history'])),clock.start+60)
                    result['action']=action
                    result['assessment']=assess(action,prefix,tasks[prefix['task_id']],rubrics[prefix['prefix_id']])
                    result['category']=result['assessment']['category']
                except EnvironmentInterruption:
                    result['category']='environment_interruption';halt.set()
                except asyncio.TimeoutError:result['category']='timeout_model'
                except Exception as exc:
                    result['category']='service_error';result['error']={'type':type(exc).__name__,'status_code':getattr(exc,'status_code',None)};halt.set()
                finally:
                    result['elapsed_s']=clock.elapsed();result['suspend_gap_s']=clock.suspend_gap()
                    result['diagnostics']=adapter.last_diagnostics or {}
                    allowance+=result['diagnostics'].get('usage',{}).get('allowance',0)
                write_new(path,result)
                print(json.dumps({'phase':'probe','model':model,'prefix':entry['prefix_id'],'condition':entry['condition'],'category':result['category']}),flush=True)
    await asyncio.gather(*(worker(model) for model in MODELS))
    rows=[json.loads(p.read_text()) for p in sorted((batch/'samples').glob('*.json'))]
    cells=[]
    for model in MODELS:
        for condition in 'ABC':
            z=[r for r in rows if r['manifest']['model']==model and r['manifest']['condition']==condition]
            cells.append({'model':model,'condition':condition,'n':len(z),'categories':dict(collections.Counter(r['category'] for r in z)),
                'new_required_full_facts':sum(r.get('assessment',{}).get('new_required_full_facts',0) for r in z),
                'new_required_navigation_ids':sum(r.get('assessment',{}).get('new_required_navigation_ids',0) for r in z),
                'submit_before_required_facts_read':sum(r['category'].startswith('submit') and not r.get('assessment',{}).get('all_required_facts_read_before_action',False) for r in z)})
    summary={'planned':144,'completed':len(rows),'cells':cells,'complete':len(rows)==144,
        'limits':'Only one next decision in selected development prefixes at synthetic remaining time; no end-to-end success estimate or universal optimal-action labels.'}
    write_new(batch/'summary.json',summary)
    lines=['# 固定公开上下文机制探针','',f'计划 144 次单步采样，完成 {len(rows)} 次。三个模型使用相同的八个公开前缀和 60 秒剩余时间，只改变 A/B/C 摘要。',
        '', '工具调用少或 tool_new 不能直接认定更好；提交正确也不能证明完整任务适应。没有将探针样本并入主实验。',
        '', '| 模型 | 条件 | 完成 | 行动类别 |','|---|---|---:|---|']
    for cell in cells:lines.append(f'| {cell["model"]} | {cell["condition"]} | {cell["n"]} | {cell["categories"]} |')
    (batch/'report.md').write_text('\n'.join(lines)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('development');p=sub.add_parser('run');p.add_argument('batch');args=parser.parse_args()
    if args.command=='prepare':print(prepare(args.development))
    else:print(json.dumps(asyncio.run(execute(args.batch)),ensure_ascii=False))

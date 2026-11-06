"""Versioned orchestration continuation after a reviewed host suspension.

The original fail-closed driver and all frozen sampling sources stay unchanged.
Only reviewed closed environment-failure records can be retained and skipped;
no failed sample is retried, removed, or overwritten. All other execution logic
is copied from the frozen driver and checked by an AST equivalence regression.
"""
import argparse
import asyncio
import datetime
import hashlib
import json
import os
from pathlib import Path

import httpx
from scripts.go_study import (load_batch,tasks_for,block_queues,take_entries,
    OpenCodeGo,MODELS,run_episode,analyze,CODE_PATHS,ROOT,data_v4)
from scripts.matrix import write_new,digest,code_hash,EpisodeJournal
from scripts.go_gates import check_formal_readiness


async def execute_reviewed(batch, review):
    batch,config,manifest=load_batch(batch)
    if config['stage']=='formal':
        from scripts.go_gates import check_formal_readiness
        e=config['readiness_evidence']
        checked=check_formal_readiness(e['development_batch'],e['diagnostic_batch'],e['verification']['path'],CODE_PATHS)
        if checked!=e:raise ValueError('formal readiness evidence changed')
    task_map={t['task_id']:t for t in tasks_for(config['stage'])}
    halt=asyncio.Event()
    for entry in manifest:
        if (batch/'started'/(entry['run_id']+'.json')).exists() and not (batch/'episodes'/(entry['run_id']+'.json')).exists():
            raise ValueError('interrupted episode requires review before any new calls')
    if (batch/'stop_requested.json').exists():raise ValueError('operator stop request present')
    write_new(batch/'run_lock.json',{'pid':os.getpid(),'config_hash':digest(config)})
    queues=block_queues(manifest)
    def runtime(state):
        data={'pid':os.getpid(),'state':state,'config_hash':digest(config),
            'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'completed':len(list((batch/'episodes').glob('*.json')))}
        temp=batch/'runtime_state.tmp';temp.write_text(json.dumps(data)+'\n');temp.replace(batch/'runtime_state.json')
    runtime('running')
    # Restore quota counters from completed public records before any new calls.
    totals={m:{'requests':0,'allowance':0.0} for m in MODELS}
    for entry in manifest:
        p=batch/'episodes'/(entry['run_id']+'.json')
        if p.exists():
            r=json.loads(p.read_text())['result']
            if r['termination_reason'] in ('service_error','protocol_violation','environment_interruption'):
                if (r['termination_reason']!='environment_interruption'
                        or entry['run_id'] not in review['resolved_environment_ids']
                        or hashlib.sha256(p.read_bytes()).hexdigest()!=review['result_hashes'].get(entry['run_id'])):
                    raise ValueError('unreviewed or changed error; no continuation allowed')
            for e in r['events']:
                for a in e.get('attempts',[]):
                    totals[entry['model_id']]['requests']+=1
                    totals[entry['model_id']]['allowance']+=a.get('adapter_diagnostics',{}).get('usage',{}).get('allowance',0)
    async def worker(model_id):
        total=totals[model_id]
        async with httpx.AsyncClient(timeout=httpx.Timeout(300,connect=20),follow_redirects=False) as client:
            for entry in take_entries(queues,model_id):
                if halt.is_set() or (batch/'stop_requested.json').exists(): break
                ident=entry['run_id']; result_path=batch/'episodes'/(ident+'.json'); started=batch/'started'/(ident+'.json')
                if result_path.exists(): continue
                if started.exists():
                    halt.set()
                    raise ValueError('interrupted episode needs explicit review; never silently rerun')
                if code_hash(CODE_PATHS)!=config['code_hash']: raise ValueError('source changed during batch')
                write_new(started,entry); journal=EpisodeJournal(batch/'journals'/(ident+'.jsonl'))
                task=task_map[entry['task_id']]
                base=OpenCodeGo(model_id,client=client,session_id='ses_time_'+batch.name+'_'+ident,
                    max_tokens=config['max_tokens'],stream=config.get('streaming',False))
                class BoundedModel:
                    @property
                    def last_diagnostics(self): return base.last_diagnostics
                    async def decide(self,observation,history):
                        if total['requests']>=config['limits']['max_requests_per_model'] or total['allowance']>=config['limits']['max_reported_allowance_per_model']:
                            raise RuntimeError('local_resource_limit')
                        total['requests']+=1
                        try: return await base.decide(observation,history)
                        finally:
                            usage=(base.last_diagnostics or {}).get('usage',{})
                            total['allowance']+=usage.get('allowance',0)
                phase='slow' if entry['profile']=='slow_to_fast' else 'fast'
                schemas=config['tool_schemas'][entry['task_family']]
                try:
                    result=await run_episode(BoundedModel(),question=task['public']['question'],tool_schemas=schemas,
                        calibration={k:config['calibration'][phase][k] for k in schemas},
                        call_tool=lambda n,a:data_v4.call_tool(task['public'],n,a),
                        verify=lambda a:data_v4.verify(task['private'],a),condition=entry['condition'],profile=entry['profile'],
                        budget_s=config['budget_s'],shift_fraction=config['shift_fraction'],fast_s=2,slow_s=15,
                        max_steps=20,event_sink=journal.emit,
                        metadata={**entry,'config_hash':digest(config),'access':'OpenCode Go HTTP; no CLI','phase':config['stage'],
                            'continuation_driver_sha256':review['source_sha256'],
                            'continuation_review_sha256':digest(review)})
                    write_new(result_path,{'manifest':entry,'result':result})
                    runtime('running')
                    print(json.dumps({'model':model_id,'task':entry['task_id'],'condition':entry['condition'],
                        'profile':entry['profile'],'success':result['deadline_success'],'termination':result['termination_reason'],
                        'elapsed_s':round(result['elapsed_s'],2)},ensure_ascii=False),flush=True)
                    if result['termination_reason'] in ('service_error','protocol_violation','environment_interruption'): halt.set()
                except BaseException as exc:
                    journal.emit({'kind':'episode_interrupted','exception_type':type(exc).__name__}); halt.set(); raise
                finally: journal.close()
    try:
        await asyncio.gather(*(worker(m) for m in MODELS for _ in range(config['concurrency']['per_model'])))
    except BaseException:
        runtime('interrupted');raise
    finally:
        (batch/'run_lock.json').unlink(missing_ok=True)
    report=analyze(batch)
    runtime('completed' if not report['missing'] else 'halted')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    write_new(batch/('analysis-'+stamp+'.json'),report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('cells','gates','missing')},ensure_ascii=False),flush=True)


def validate_review(batch,review):
    batch,config,manifest=load_batch(batch)
    if config['stage']!='formal' or review.get('config_hash')!=digest(config):
        raise ValueError('review must match frozen formal configuration')
    if review.get('source_sha256')!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError('reviewed continuation source changed')
    if (batch/'run_lock.json').exists() or (batch/'stop_requested.json').exists():
        raise ValueError('live lock or user stop; no continuation')
    previous=json.loads((batch/'runtime_state.json').read_text())
    if previous['state'] not in ('halted','interrupted'):
        raise ValueError('original batch not confirmed terminal')
    try:
        os.kill(previous['pid'],0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError('old PID still exists; verify it before continuation')
    resolved=set(review['resolved_environment_ids']);found=set()
    for entry in manifest:
        ident=entry['run_id'];p=batch/'episodes'/(ident+'.json')
        if not p.exists():
            if (batch/'started'/(ident+'.json')).exists():
                raise ValueError('unfinished episode requires a separate review')
            continue
        if ident not in review['result_hashes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=review['result_hashes'][ident]:
            raise ValueError('existing result changed or missing from reviewed census')
        row=json.loads(p.read_text());r=row['result']
        if row['manifest']!=entry or r['metadata']['config_hash']!=digest(config):
            raise ValueError('result identity mismatch')
        if r['termination_reason'] in ('service_error','protocol_violation'):
            raise ValueError('service/protocol fault is not a reviewed host suspension')
        if r['termination_reason']=='environment_interruption':
            found.add(ident)
            if (ident not in resolved or r.get('deadline_success') or r.get('valid_submission')
                    or r.get('suspend_gap_s',0)<=1
                    or not r.get('infrastructure_error_flags')
                    or any(e.get('type')!='host_suspend' for e in r['infrastructure_error_flags'])):
                raise ValueError('environment record not eligible for this resolution')
    if found!=resolved or len(review['result_hashes'])!=review['original_completed']:
        raise ValueError('reviewed closed record set mismatch')
    for rel,expected in review['immutable_file_hashes'].items():
        if hashlib.sha256((batch/rel).read_bytes()).hexdigest()!=expected:
            raise ValueError('existing frozen/journal/started file changed')
    e=config['readiness_evidence']
    checked=check_formal_readiness(e['development_batch'],e['diagnostic_batch'],e['verification']['path'],CODE_PATHS)
    if checked!=e:raise ValueError('original pre-formal readiness evidence changed')
    return batch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('batch');parser.add_argument('--review',required=True)
    args=parser.parse_args();review_path=Path(args.review).resolve();review=json.loads(review_path.read_text())
    batch=validate_review(args.batch,review)
    write_new(review_path.parent/'continuation_started.json',{'pid':os.getpid(),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'review_sha256':hashlib.sha256(review_path.read_bytes()).hexdigest(),
        'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    asyncio.run(execute_reviewed(batch,review))
    changed=[rel for rel,sha in review['immutable_file_hashes'].items()
             if hashlib.sha256((batch/rel).read_bytes()).hexdigest()!=sha]
    write_new(review_path.parent/'continuation_finished.json',{'changed_original_files':changed,
        'completed':len(list((batch/'episodes').glob('*.json'))),
        'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    if changed:raise ValueError('immutable originals changed')


if __name__=='__main__':main()

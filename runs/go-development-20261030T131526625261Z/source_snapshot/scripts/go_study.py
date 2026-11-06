"""Bounded, versioned three-model study. No keys or private answers in logs.

Prepare/run/analyze are separate commands. Each model has one worker; different
models run concurrently. Formal preparation requires a passing development
batch and independently generated boundary evidence, never a bypass flag.
"""
import argparse
import asyncio
import collections
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import statistics

import httpx

from scripts.matrix import build_manifest, code_hash, digest, write_new, EpisodeJournal
from src.adapters.opencode_go import OpenCodeGo, MODELS, PROMPT, BASE_URL
from src.calibration import calibrate
from src.runner_v2 import run_episode
from tasks import data_v4

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ('stable_fast', 'fast_to_slow', 'slow_to_fast')
NAMES = ('search', 'read_document', 'lookup_rows', 'calculate')
CODE_PATHS = tuple(ROOT / p for p in (
    'src/adapters/opencode_go.py', 'src/runner_v2.py', 'src/conditions.py',
    'src/calibration.py', 'src/protocol.py', 'tasks/data.py', 'tasks/data_v2.py',
    'tasks/data_v3.py', 'tasks/data_v4.py', 'scripts/run_diagnostic.py',
    'scripts/go_study.py', 'scripts/matrix.py', 'scripts/analyze_matrix.py',
    'scripts/go_gates.py', 'scripts/audit_public_answers.py',
    'scripts/verify_go_environment.py','scripts/study_statistics.py','scripts/study_report.py',
    'requirements.txt'))


def tasks_for(stage):
    tasks = data_v4.generate('test' if stage == 'formal' else 'dev')
    if stage == 'diagnostic':
        return [next(t for t in tasks if t['task_family'] == family) for family in ('evidence', 'table')]
    return tasks


def make_manifest(tasks, stage, seed):
    entries = build_manifest(tasks, list(MODELS),
        ('stable_fast',) if stage == 'diagnostic' else PROFILES,
        3 if stage == 'diagnostic' else 2 if stage == 'formal' else 1, seed)
    return [e for e in entries if e['condition'] == 'A'] if stage == 'diagnostic' else entries


def load_batch(batch):
    batch = Path(batch).resolve()
    if batch.parent != (ROOT / 'runs').resolve() or not batch.name.startswith('go-'):
        raise ValueError('expected go-* batch under project runs')
    config = json.loads((batch / 'config.json').read_text())
    manifest = json.loads((batch / 'manifest.json').read_text())
    if (digest(config) != json.loads((batch / 'config_hash.json').read_text())['sha256']
            or digest(manifest) != config['manifest_hash']
            or code_hash(CODE_PATHS) != config['code_hash']
            or digest(tasks_for(config['stage'])) != config['task_hash']):
        raise ValueError('batch code/config/manifest/task changed; use a new versioned batch')
    return batch, config, manifest


def observations(result):
    boundary = result['budget_s'] * result['shift_fraction']
    events = result['events']
    tools = [e for e in events if e.get('event_type') == 'tool' and not e.get('invalid')
             and not e.get('is_censored') and 'observed_duration_s' in e]
    shifted = [e for e in tools if e['tool_start_offset_s'] >= boundary]
    after = lambda tool: [e for e in events if e.get('event_type') == 'model_request'
                         and e['request_start_offset_s'] >= tool['tool_end_offset_s']]
    observed = [e for e in shifted if after(e)]
    both = any(any(p['tool_name'] == e['tool_name'] and p['tool_start_offset_s'] < boundary for p in tools)
               for e in observed)
    def valid_action(event):
        a = event.get('action')
        if not isinstance(a, dict): return False
        if a.get('type') == 'submit':
            return result.get('valid_submission') and a.get('answer') == result.get('final_answer')
        if a.get('type') == 'tool':
            return any(t.get('event_type') == 'tool' and t.get('step_index') == event.get('step_index')
                       and not t.get('invalid') for t in events)
        return False
    decision = bool(observed) and any(valid_action(e) for e in after(observed[0]))
    return bool(observed), bool(both), decision


def block_queues(manifest):
    """Keep each paired A/B/C block on one worker; share distinct blocks."""
    groups={m:collections.OrderedDict() for m in MODELS}
    for entry in manifest:
        key=(entry['task_id'],entry['profile'],entry['repeat'])
        groups[entry['model_id']].setdefault(key,[]).append(entry)
    return {m:collections.deque(v.values()) for m,v in groups.items()}


def take_entries(queues,model):
    while queues[model]:
        yield from queues[model].popleft()


def analyze(batch, *, verify=True):
    if verify:
        batch, config, manifest = load_batch(batch)
    else:
        batch = Path(batch)
        config = json.loads((batch/'config.json').read_text())
        manifest = json.loads((batch/'manifest.json').read_text())
    rows, missing, interrupted = [], [], []
    for e in manifest:
        p = batch/'episodes'/(e['run_id']+'.json')
        if not p.exists():
            missing.append(e['run_id'])
            if (batch/'started'/(e['run_id']+'.json')).exists(): interrupted.append(e['run_id'])
            continue
        row = json.loads(p.read_text())
        if row['manifest'] != e or row['result']['metadata']['config_hash'] != digest(config):
            raise ValueError('record mismatch')
        rows.append(row)
    cells = []
    for m, f, p, c in sorted({(r['manifest']['model_id'], r['manifest']['task_family'],
                               r['manifest']['profile'], r['manifest']['condition']) for r in rows}):
        z = [r['result'] for r in rows if (r['manifest']['model_id'], r['manifest']['task_family'],
             r['manifest']['profile'], r['manifest']['condition']) == (m,f,p,c)]
        cells.append({'model':m, 'family':f, 'profile':p, 'condition':c, 'n':len(z),
            'success':sum(r['deadline_success'] for r in z),
            'termination':dict(collections.Counter(r['termination_reason'] for r in z))})
    gates = []
    for m in MODELS:
        for family in ('evidence','table'):
            z = [r['result'] for r in rows if r['manifest']['model_id']==m
                 and r['manifest']['task_family']==family and r['manifest']['profile']=='stable_fast']
            n, successes = len(z), sum(r['deadline_success'] for r in z)
            expected = 3 if config['stage']=='diagnostic' else 12
            gates.append({'model':m,'family':family,'check':'basic_solvability','n':n,
                'success':successes,'pass':n==expected and successes >= (2 if expected==3 else 6)})
            if config['stage']=='development':
                for profile in PROFILES[1:]:
                    z=[r['result'] for r in rows if r['manifest']['model_id']==m
                       and r['manifest']['task_family']==family and r['manifest']['profile']==profile]
                    flags=[observations(r) for r in z]
                    exposed=sum(v[0] for v in flags); both=sum(v[1] for v in flags); decisions=sum(v[2] for v in flags)
                    successes=sum(r['deadline_success'] for r in z)
                    # In a 12-second slow-to-fast shift, the first 15-second
                    # search can span the entire old phase. Requiring another
                    # search before the shift would penalize efficient paths.
                    # Calibration is the shared old-phase baseline; retain both
                    # in-episode phases as a description, not a selection gate.
                    passed=len(z)==12 and exposed>=9 and decisions*3>=exposed*2
                    gates.append({'model':m,'family':family,'profile':profile,'check':'change_opportunity',
                        'n':len(z),'exposed':exposed,'same_tool_both_phases':both,'post_shift_valid_action':decisions,
                        'success':successes,'pass':passed})
        if config['stage']=='development':
            primary=[r['result'] for r in rows if r['manifest']['model_id']==m and r['manifest']['profile']=='fast_to_slow']
            successes=sum(r['deadline_success'] for r in primary)
            gates.append({'model':m,'check':'primary_outcome_variability','n':len(primary),'success':successes,
                'pass':len(primary)==24 and 0<successes<24})
    failures=sum(r['result']['termination_reason'] in ('service_error','protocol_violation') for r in rows)
    flagged=sum(bool(r['result'].get('service_error_flags')) for r in rows)
    times=[e['response_end_offset_s']-e['request_start_offset_s'] for row in rows
        for e in row['result']['events'] if e.get('event_type')=='model_request'
        and 'response_end_offset_s' in e and not e.get('is_censored')]
    usage=[attempt.get('adapter_diagnostics',{}).get('usage',{}) for row in rows
        for event in row['result']['events'] for attempt in event.get('attempts',[])]
    report={'batch':str(batch),'stage':config['stage'],'planned':len(manifest),'completed':len(rows),
        'missing':missing,'interrupted':interrupted,'success':sum(r['result']['deadline_success'] for r in rows),
        'termination':dict(collections.Counter(r['result']['termination_reason'] for r in rows)),
        'cells':cells,'gates':gates,'service_or_protocol_failures':failures,
        'service_flagged_episodes':flagged,'quality_policy':'go_quality_v2',
        'completed_request_wall_s':{'n':len(times),'mean':statistics.mean(times) if times else None,
                                   'median':statistics.median(times) if times else None},
        'usage_records':len(usage),'allowance_known_sum':sum(u.get('allowance',0) for u in usage),
        'billing_sources':dict(collections.Counter(u.get('billing_source','unreported') for u in usage)),
        'ready_for_next_stage':not missing and failures==0 and all(g['pass'] for g in gates)
            and (config['stage']!='development' or flagged*20<=len(rows))}
    return report


async def prepare(stage, budget=None, shift=.2, seed=20261030, reason='', development=None,
                  diagnostic=None,verification=None,per_model=None):
    from scripts.go_gates import check_formal_readiness,check_verification,check_diagnostic
    evidence={}
    if stage=='development':
        if not diagnostic or not verification:raise ValueError('development requires diagnostic and offline verification evidence')
        evidence={'verification':check_verification(verification,CODE_PATHS)}
        diag_path,diag_config=check_diagnostic(diagnostic)
        evidence.update({'diagnostic_batch':str(diag_path),'diagnostic_config_hash':digest(diag_config)})
    if stage=='formal':
        if not all((development,diagnostic,verification)):raise ValueError('formal requires development, diagnostic and verification evidence')
        evidence=check_formal_readiness(development,diagnostic,verification,CODE_PATHS)
        _,dev_config,_=load_batch(development)
        if budget is not None and budget!=dev_config['budget_s']:raise ValueError('formal budget must match validated development')
        budget=dev_config['budget_s'];shift=dev_config['shift_fraction']
        if per_model is not None and per_model!=dev_config['concurrency']['per_model']:
            raise ValueError('formal concurrency must match validated development')
        per_model=dev_config['concurrency']['per_model']
    per_model=per_model or 1
    if per_model not in (1,2):raise ValueError('per-model concurrency must be 1 or 2')
    if not 0<shift<1 or (budget is not None and (not math.isfinite(budget) or budget<=0)):
        raise ValueError('invalid timing configuration')
    tasks=tasks_for(stage); manifest=make_manifest(tasks,stage,seed)
    fast,slow=await asyncio.gather(calibrate(NAMES,2,tool_call=data_v4.call_tool),
                                  calibrate(NAMES,15,tool_call=data_v4.call_tool))
    config={'stage':stage,'models':list(MODELS),'budget_s':budget or (300 if stage=='diagnostic' else 180),
        'shift_fraction':shift,'fast_s':2,'slow_s':15,'window':3,'max_steps':20,'max_tokens':2048,
        'profiles':['stable_fast'] if stage=='diagnostic' else list(PROFILES),
        'concurrency':{'global':3*per_model,'per_model':per_model},'manifest_seed':seed,'change_reason':reason,
        'calibration':{'fast':fast,'slow':slow},'calibration_method':'three concurrent measurements per tool outside episodes',
        'task_hash':digest(tasks),'manifest_hash':digest(manifest),'code_hash':code_hash(CODE_PATHS),
        'tool_schemas':data_v4.tool_schemas(),'prompt':PROMPT,'base_url':BASE_URL,
        'model_settings':{'temperature':'provider default; not set','max_tokens':2048,'reasoning':'provider default; not set'},
        'protocol':'one text JSON action; no native/external tool execution',
        'limits':{'max_requests_per_model':14400 if stage=='formal' else 2000,
                  'max_reported_allowance_per_model':5.0 if stage=='formal' else 3.0},
        'readiness_evidence':evidence,
        'quality_policy':'go_quality_v2; both-phase same-tool observation descriptive; primary variability pooled by model',
        'analysis':{'primary':'fast_to_slow C-B deadline success','bootstrap':'10000 task-cluster paired draws stratified by family',
                    'seed':911,'models':'fixed equal weight','individual_intervals':'exploratory'},
        'purpose':'frozen formal three-model experiment' if stage=='formal' else 'development only; no condition-effect inference'}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    batch=ROOT/'runs'/('go-'+stage+'-'+stamp)
    batch.mkdir(parents=True,exist_ok=False)
    write_new(batch/'config.json',config); write_new(batch/'config_hash.json',{'sha256':digest(config)})
    write_new(batch/'manifest.json',manifest)
    archived={}
    for source in CODE_PATHS:
        target=batch/'source_snapshot'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write(source.read_bytes())
        archived[str(source.as_posix())]=hashlib.sha256(target.read_bytes()).hexdigest()
    write_new(batch/'source_snapshot_hashes.json',archived)
    return batch


async def execute(batch):
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
            if r['termination_reason'] in ('service_error','protocol_violation'):
                raise ValueError('batch has unresolved error; inspect it and create a new version')
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
                base=OpenCodeGo(model_id,client=client,session_id='ses_time_'+batch.name+'_'+ident,max_tokens=config['max_tokens'])
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
                        metadata={**entry,'config_hash':digest(config),'access':'OpenCode Go HTTP; no CLI','phase':config['stage']})
                    write_new(result_path,{'manifest':entry,'result':result})
                    runtime('running')
                    print(json.dumps({'model':model_id,'task':entry['task_id'],'condition':entry['condition'],
                        'profile':entry['profile'],'success':result['deadline_success'],'termination':result['termination_reason'],
                        'elapsed_s':round(result['elapsed_s'],2)},ensure_ascii=False),flush=True)
                    if result['termination_reason'] in ('service_error','protocol_violation'): halt.set()
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('stage',choices=('diagnostic','development','formal'))
    p.add_argument('--budget',type=float);p.add_argument('--shift',type=float,default=.2);p.add_argument('--reason',default='initial registered candidate')
    p.add_argument('--development');p.add_argument('--diagnostic');p.add_argument('--verification')
    p.add_argument('--per-model',type=int,choices=(1,2))
    p=sub.add_parser('run');p.add_argument('batch')
    p=sub.add_parser('analyze');p.add_argument('batch')
    args=parser.parse_args()
    if args.command=='prepare': print(asyncio.run(prepare(args.stage,args.budget,args.shift,reason=args.reason,
        development=args.development,diagnostic=args.diagnostic,verification=args.verification,per_model=args.per_model)))
    elif args.command=='run': asyncio.run(execute(args.batch))
    else: print(json.dumps(analyze(args.batch),ensure_ascii=False,indent=2))


if __name__=='__main__': main()

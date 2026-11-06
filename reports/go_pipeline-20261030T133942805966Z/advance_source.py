"""Continue a real live development job into gated formal execution and reports.

Never restarts a disappeared job. May register at most two further complete
development matrices using pooled quality-only rules. The model IDs and runtime remain
those frozen by go_study; no unattended fallback to paid or different models.
"""
import argparse
import asyncio
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from scripts.go_study import analyze,prepare,execute,ROOT
from scripts.matrix import write_new
from scripts.study_report import report


def calibration_revision(summary,config):
    """No condition labels, C-B estimates or p-values enter this rule."""
    if summary.get('missing') or summary['completed']!=summary['planned']:
        return None,'matrix_incomplete'
    if summary.get('service_or_protocol_failures') or summary.get('service_flagged_episodes',0)*20>summary['completed']:
        return None,'service_or_protocol_requires_review'
    failed=[g for g in summary['gates'] if not g['pass']]
    if any(g['check']=='basic_solvability' for g in failed):
        return None,'basic_solvability_requires_correctness_and_interface_review'
    directions=set();earlier=False;reasons=[]
    for gate in failed:
        if gate['check']=='primary_outcome_variability':
            if gate['success']==gate['n']:
                directions.add(-1);reasons.append('pooled_primary_ceiling')
            elif gate['success']==0:
                directions.add(1);reasons.append('pooled_primary_floor')
            else:return None,'unexpected_variability_gate'
        elif gate['check']=='change_opportunity':
            if gate['exposed']<9:earlier=True;reasons.append('insufficient_new_phase_feedback')
            if gate['post_shift_valid_action']*3<gate['exposed']*2:
                directions.add(1);reasons.append('insufficient_post_feedback_decision_time')
        else:return None,'unknown_quality_gate'
    if len(directions)>1:return None,'conflicting_cross_model_budget_requirements'
    budget=config['budget_s']+(30*next(iter(directions)) if directions else 0)
    change=config['budget_s']*config['shift_fraction']
    if earlier:change=max(4,change/2)
    if not 90<=budget<=300:return None,'registered_budget_range_exhausted'
    if budget==config['budget_s'] and abs(change-config['budget_s']*config['shift_fraction'])<1e-9:
        return None,'no_registered_parameter_repair'
    return {'budget':budget,'shift':change/budget,'reason':';'.join(sorted(set(reasons)))},'quality_only_revision'


def job_alive(batch):
    runtime=json.loads((batch/'runtime_state.json').read_text())
    if runtime['state']!='running':return False
    try:
        os.kill(runtime['pid'],0)
        command=subprocess.check_output(['ps','-p',str(runtime['pid']),'-o','command='],text=True).strip()
    except ProcessLookupError:return False
    except subprocess.CalledProcessError:return False
    except PermissionError:raise RuntimeError('specific live process cannot be verified; do not restart it') from None
    return 'scripts.go_study run' in command and batch.name in command


def advance(development,diagnostic,verification):
    development=Path(development).resolve();diagnostic=Path(diagnostic).resolve();verification=Path(verification).resolve()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory=ROOT/'reports'/('go_pipeline-'+stamp);directory.mkdir(parents=True,exist_ok=False)
    write_new(directory/'plan.json',{'development':str(development),'diagnostic':str(diagnostic),'verification':str(verification),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'policy':'verify current process; no restart on observation timeout; at most 3 complete development matrices with pooled quality-only parameter rules, then enforce readiness before formal 1080',
        'model_changes':False,'max_wait_hours':6,'max_development_matrices':3,
        'revision_rules':{'primary_ceiling':'common budget -30s','primary_floor_or_no_decision_time':'common budget +30s',
            'insufficient_exposure':'halve absolute change time, minimum 4s','budget_range_s':[90,300],
            'conflicting_directions_or_basic_correctness_failure':'stop for agent review; do not weaken gates',
            'prohibited_inputs':['condition labels','C-B effect','p values','formal test results']}})
    for attempt in range(3):
        deadline=time.monotonic()+6*3600;last_count=-1
        while True:
            current=analyze(development)
            if current['completed']!=last_count:
                print(json.dumps({'phase':'development','attempt':attempt+1,'batch':development.name,
                    'completed':current['completed'],'planned':current['planned']},ensure_ascii=False),flush=True)
                last_count=current['completed']
            if not current['missing']:break
            if not job_alive(development):
                write_new(directory/'needs_review.json',{'reason':'development job terminal or handle missing','completed':current['completed'],
                    'missing':current['missing'],'interrupted':current['interrupted'],'automatically_restarted':False})
                print('Development job stopped; retained records require review.',flush=True);return
            if time.monotonic()>deadline:
                write_new(directory/'needs_review.json',{'reason':'observation window ended while job may still be live','job_restarted':False})
                print('Observation window ended; no restart or terminal claim.',flush=True);return
            time.sleep(20)
        report(development,directory/('development-'+str(attempt+1)))
        if current['ready_for_next_stage']:break
        config=json.loads((development/'config.json').read_text())
        revision,reason=calibration_revision(current,config)
        if (development/'stop_requested.json').exists():revision=None;reason='operator_stop'
        if revision is None or attempt==2:
            failed=[g for g in current['gates'] if not g['pass']]
            write_new(directory/'needs_review.json',{'reason':reason if attempt<2 else 'registered_candidate_limit_reached',
                'failed':failed,'service_flagged_episodes':current['service_flagged_episodes'],'formal_started':False})
            print(json.dumps({'phase':'needs_quality_review','reason':reason,'failed':failed},ensure_ascii=False),flush=True);return
        write_new(directory/('revision-'+str(attempt+1)+'.json'),{'source_batch':str(development),**revision,
            'no_condition_effect_selection':True,'next_matrix':216})
        development=asyncio.run(prepare('development',budget=revision['budget'],shift=revision['shift'],
            per_model=config['concurrency']['per_model'],diagnostic=diagnostic,verification=verification,
            reason='Registered pooled-quality-only revision: '+revision['reason']))
        print(json.dumps({'phase':'revised_development','batch':str(development),'settings':revision}),flush=True)
        asyncio.run(execute(development))
    if (development/'stop_requested.json').exists():
        print('Operator stop retained; formal not started.',flush=True);return
    formal=asyncio.run(prepare('formal',development=development,diagnostic=diagnostic,verification=verification,
        reason='Automatic stage progression after complete verified development; no test-result parameter tuning'))
    write_new(directory/'formal_batch.json',{'path':str(formal)})
    print(json.dumps({'phase':'formal','batch':str(formal),'planned':1080}),flush=True)
    asyncio.run(execute(formal))
    report(formal,directory/'formal')
    result=analyze(formal)
    write_new(directory/'completion.json',{'formal_batch':str(formal),'planned':1080,'completed':result['completed'],
        'all_planned_results_present':not result['missing'],'formal_report':str(directory/'formal/report.md'),
        'note':'Report generation is not a claim of positive effects or external acceptance; optional mechanism probe is separate.'})
    print(json.dumps({'phase':'formal_report_written','completed':result['completed'],'directory':str(directory)}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--development',required=True);parser.add_argument('--diagnostic',required=True);parser.add_argument('--verification',required=True)
    args=parser.parse_args();advance(args.development,args.diagnostic,args.verification)

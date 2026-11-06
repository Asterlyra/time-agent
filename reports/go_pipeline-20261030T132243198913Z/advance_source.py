"""Continue a real live development job into gated formal execution and reports.

Never restarts a disappeared job or edits failed development parameters. Emits
specific quality failures for agent review. The model IDs and runtime remain
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
        'policy':'verify current process, never restart on observation timeout; wait for complete development, report, enforce readiness, then freeze formal 1080 and report',
        'model_changes':False,'max_wait_hours':6})
    deadline=time.monotonic()+6*3600;last_count=-1
    while True:
        current=analyze(development)
        if current['completed']!=last_count:
            print(json.dumps({'phase':'development','completed':current['completed'],'planned':current['planned']},ensure_ascii=False),flush=True)
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
    report(development,directory/'development')
    if not current['ready_for_next_stage']:
        failed=[g for g in current['gates'] if not g['pass']]
        write_new(directory/'needs_review.json',{'reason':'development quality gates did not pass','failed':failed,
            'service_flagged_episodes':current['service_flagged_episodes'],'formal_started':False})
        print(json.dumps({'phase':'needs_quality_review','failed':failed},ensure_ascii=False),flush=True);return
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

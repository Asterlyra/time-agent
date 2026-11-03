"""Validate the repaired native SSE transport, then resume the staged study.

Old nonstream development results remain separate. No model replacement or
condition-effect selection: the 150s candidate follows the registered -30s
response to the old complete DeepSeek ceiling, after rechecking transport.
"""
import argparse
import asyncio
import datetime
import hashlib
import json
from pathlib import Path

from scripts.advance_go_study import advance
from scripts.go_gates import check_verification
from scripts.go_study import execute,prepare,analyze,CODE_PATHS,ROOT
from scripts.matrix import write_new
from scripts.study_report import report


def repair(diagnostic,verification):
    diagnostic=Path(diagnostic).resolve();verification=Path(verification).resolve()
    check_verification(verification,CODE_PATHS)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory=ROOT/'reports'/('go_transport_repair-'+stamp);directory.mkdir(parents=True,exist_ok=False)
    write_new(directory/'plan.json',{'diagnostic':str(diagnostic),'verification':str(verification),
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'repair':'native SSE with complete terminal action accumulation and safe transport subclass logging',
        'next_development_budget_s':150,'absolute_change_s':12,'concurrency':{'global':6,'per_model':2},
        'reason':'old complete development had 13/216 connection-flagged episodes and DeepSeek primary 24/24 ceiling; no condition difference used',
        'old_results_combined_with_new':False})
    (directory/'repair_source.py').write_bytes(Path(__file__).read_bytes())
    try:
        asyncio.run(execute(diagnostic));report(diagnostic,directory/'diagnostic')
        status=analyze(diagnostic)
        if not status['ready_for_next_stage']:
            write_new(directory/'needs_review.json',{'reason':'SSE diagnostic did not pass','summary':status})
            print(json.dumps({'phase':'repair_needs_review','directory':str(directory)}),flush=True);return
        development=asyncio.run(prepare('development',budget=150,shift=12/150,per_model=2,
            diagnostic=diagnostic,verification=verification,
            reason='Native SSE repair re-diagnosed; common budget 180->150 follows pre-registered pooled DeepSeek ceiling rule; fixed 12s change and same three models/prompt/output limit. Old nonstream data kept separate.'))
        write_new(directory/'development_batch.json',{'path':str(development)})
        print(json.dumps({'phase':'repaired_development','batch':str(development),'planned':216}),flush=True)
        asyncio.run(execute(development))
        advance(development,diagnostic,verification)
    except BaseException as exc:
        if not (directory/'needs_review.json').exists():
            write_new(directory/'needs_review.json',{'reason':'repair pipeline interrupted','exception_type':type(exc).__name__,
                'records_preserved':True,'formal_completion_claimed':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--diagnostic',required=True);parser.add_argument('--verification',required=True)
    args=parser.parse_args();repair(args.diagnostic,args.verification)

"""Validate a shared exact-evidence contract after reviewed development failures.

Launch with /usr/bin/caffeinate -i python -m scripts.repair_go_evidence ... on Mac.
The process assertion ends with this process. All older batches stay intact.
"""
import argparse
import asyncio
import datetime
import hashlib
import json
from pathlib import Path

from scripts.advance_go_study import advance
from scripts.go_gates import check_verification
from scripts.go_study import execute, prepare, analyze, CODE_PATHS, ROOT
from scripts.matrix import write_new
from scripts.study_report import report
from src.elapsed_clock import clock_metadata


def repair(verification):
    verification = Path(verification).resolve()
    check_verification(verification, CODE_PATHS)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory = ROOT/'reports'/('go_evidence_repair-'+stamp)
    directory.mkdir(parents=True, exist_ok=False)
    write_new(directory/'plan.json', {
        'verification': str(verification), 'clock': clock_metadata(),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'repair': 'shared exact distinct evidence-set instruction; exclude unmatched rows in joins; continuous-clock kernel retained',
        'idle_sleep_prevention': 'launcher: process-scoped caffeinate -i; no persistent system changes',
        'diagnostic': 18, 'development': 216, 'formal': 1080,
        'next_development_budget_s': 150, 'absolute_change_s': 12,
        'concurrency': {'global': 6, 'per_model': 2},
        'reason': 'continuous-clock diagnostic completed 18/18,16 correct; GLM table 1/3 due extra unmatched product ID, correct numeric total. No scorer change or hidden answer hint; same instruction for all models/conditions',
        'source_review': str(ROOT/'reports/go_clock_repair-20261031T024327799421Z/evidence_contract_review.json'),
        'budget_reason': 'retain prior 150s candidate from pre-registered pooled-ceiling rule; no condition effect selection',
        'old_results_combined_with_new': False})
    (directory/'repair_source.py').write_bytes(Path(__file__).read_bytes())
    try:
        diagnostic = asyncio.run(prepare('diagnostic', per_model=2,
            reason='Exact evidence contract clarification after reviewed GLM join evidence errors; continuous clock retained; all models receive identical system instructions; no old data pooled'))
        write_new(directory/'diagnostic_batch.json', {'path': str(diagnostic)})
        print(json.dumps({'phase': 'evidence_diagnostic', 'batch': str(diagnostic), 'planned': 18}), flush=True)
        asyncio.run(execute(diagnostic))
        report(diagnostic, directory/'diagnostic')
        status = analyze(diagnostic)
        if not status['ready_for_next_stage']:
            write_new(directory/'needs_review.json', {'reason': 'exact evidence diagnostic failed', 'summary': status})
            return
        development = asyncio.run(prepare('development', budget=150, shift=12/150, per_model=2,
            diagnostic=diagnostic, verification=verification,
            reason='Shared exact evidence contract and continuous clock validated in fresh diagnosis; retain 150s/12s/three models from registered quality revision. Earlier prompt and timing batches excluded.'))
        write_new(directory/'development_batch.json', {'path': str(development)})
        print(json.dumps({'phase': 'evidence_development', 'batch': str(development), 'planned': 216}), flush=True)
        asyncio.run(execute(development))
        advance(development, diagnostic, verification)
    except BaseException as exc:
        if not (directory/'needs_review.json').exists():
            write_new(directory/'needs_review.json', {'reason': 'evidence pipeline interrupted',
                'exception_type': type(exc).__name__, 'records_preserved': True, 'formal_completion_claimed': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verification', required=True)
    repair(parser.parse_args().verification)

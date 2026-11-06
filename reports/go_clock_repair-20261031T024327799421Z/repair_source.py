"""Versioned continuous-clock re-diagnosis and gated study progression.

Launch with /usr/bin/caffeinate -i python -m scripts.repair_go_clock ... on Mac.
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
    directory = ROOT/'reports'/('go_clock_repair-'+stamp)
    directory.mkdir(parents=True, exist_ok=False)
    write_new(directory/'plan.json', {
        'verification': str(verification), 'clock': clock_metadata(),
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'repair': 'continuous deadline, periodic wake guard, host suspend infrastructure classification',
        'idle_sleep_prevention': 'launcher: process-scoped caffeinate -i; no persistent system changes',
        'diagnostic': 18, 'development': 216, 'formal': 1080,
        'next_development_budget_s': 150, 'absolute_change_s': 12,
        'concurrency': {'global': 6, 'per_model': 2},
        'reason': 'SSE development stopped at 192/216 with pre-HTTP connection errors and 10 indirect clock-suspicion records; fix measurement before capability comparison',
        'budget_reason': 'retain prior 150s candidate from pre-registered pooled-ceiling rule; no condition effect selection',
        'old_results_combined_with_new': False})
    (directory/'repair_source.py').write_bytes(Path(__file__).read_bytes())
    try:
        diagnostic = asyncio.run(prepare('diagnostic', per_model=2,
            reason='Continuous-clock repair diagnosis; no old timing-suspect results pooled'))
        write_new(directory/'diagnostic_batch.json', {'path': str(diagnostic)})
        print(json.dumps({'phase': 'clock_diagnostic', 'batch': str(diagnostic), 'planned': 18}), flush=True)
        asyncio.run(execute(diagnostic))
        report(diagnostic, directory/'diagnostic')
        status = analyze(diagnostic)
        if not status['ready_for_next_stage']:
            write_new(directory/'needs_review.json', {'reason': 'clock diagnostic failed', 'summary': status})
            return
        development = asyncio.run(prepare('development', budget=150, shift=12/150, per_model=2,
            diagnostic=diagnostic, verification=verification,
            reason='Suspend-inclusive clock validated in fresh diagnosis; retain 150s/12s/three models from prior registered quality revision. Earlier timing batches excluded.'))
        write_new(directory/'development_batch.json', {'path': str(development)})
        print(json.dumps({'phase': 'clock_development', 'batch': str(development), 'planned': 216}), flush=True)
        asyncio.run(execute(development))
        advance(development, diagnostic, verification)
    except BaseException as exc:
        if not (directory/'needs_review.json').exists():
            write_new(directory/'needs_review.json', {'reason': 'clock pipeline interrupted',
                'exception_type': type(exc).__name__, 'records_preserved': True, 'formal_completion_claimed': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verification', required=True)
    repair(parser.parse_args().verification)

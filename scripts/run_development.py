"""Bounded exploratory Luna development run; never label as a frozen test."""
import asyncio
import argparse
import datetime
import json
from pathlib import Path
from tasks.data_v2 import generate, call_tool, verify
from src.runner import run_episode
from src.adapters.codex_mxc import CodexMXC
from src.calibration import calibrate
from scripts.run_diagnostic import SCHEMAS
from scripts.matrix import build_manifest, write_new, digest, code_hash, EpisodeJournal


async def main(resume=None):
    tasks = generate('dev')
    task_map = {t['task_id']: t for t in tasks}
    names = ['search', 'read_document', 'lookup_rows', 'calculate']
    code_paths = ['tasks/data.py', 'tasks/data_v2.py', 'src/runner.py', 'src/conditions.py', 'src/protocol.py',
                  'src/calibration.py', 'src/adapters/codex_cli.py', 'src/adapters/codex_mxc.py', 'scripts/run_development.py',
                  'scripts/run_diagnostic.py', 'scripts/matrix.py']
    if resume:
        batch = Path(resume)
        config = json.loads((batch/'config.json').read_text(encoding='utf-8'))
        manifest = json.loads((batch/'manifest.json').read_text(encoding='utf-8'))
        if (digest(tasks) != config['task_hash'] or code_hash(config['code_paths']) != config['code_hash']
                or digest(manifest) != config['manifest_hash']):
            raise ValueError('resume refused: task, code or manifest changed')
        fast, slow = config['calibration']['fast'], config['calibration']['slow']
    else:
        fast, slow = await asyncio.gather(calibrate(names, 2, tool_call=call_tool), calibrate(names, 15, tool_call=call_tool))
        manifest = build_manifest(tasks, ['gpt-6-luna'], ['stable_fast', 'fast_to_slow', 'slow_to_fast'], 1, 4125)
        config = {'purpose': 'exploratory development, not formal', 'model': 'gpt-6-luna',
              'budget_s': 120, 'fast_s': 2, 'slow_s': 15, 'shift_fraction': .5,
              'conditions': ['A', 'B', 'C'], 'profiles': ['stable_fast', 'fast_to_slow', 'slow_to_fast'],
              'repeats': 1, 'seed': 4125, 'concurrency': 1, 'calibration': {'fast': fast, 'slow': slow},
              'isolation': 'MXC deny-read of workspace and disabled extra tools; end-to-end isolation not independently verified',
              'task_generator': 'v2-candidate', 'task_hash': digest(tasks), 'code_paths': code_paths,
              'code_hash': code_hash(code_paths), 'cli_version': 'desktop Codex runtime 0.165.0-alpha.1.2',
              'reasoning_effort': 'CLI default, not independently verified',
              'calibration_note': 'three concurrent measurements per tool and profile',
              'manifest_hash': digest(manifest), 'token_usage': None, 'estimated_cost': None}
        batch = Path('runs') / ('development-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        batch.mkdir(parents=True, exist_ok=False)
        write_new(batch/'config.json', config)
        write_new(batch/'manifest.json', manifest)
    config_hash = digest(config)
    queue = asyncio.Queue()
    interrupted = []
    for entry in manifest:
        run_id = entry['run_id']
        if (batch/'episodes'/(run_id+'.json')).exists(): continue
        if (batch/'started'/(run_id+'.json')).exists():
            interrupted.append(run_id)
            continue
        queue.put_nowait(entry)
    stop = asyncio.Event()

    async def worker():
        model = CodexMXC(denied_roots=[str(Path.cwd())])
        while not queue.empty() and not stop.is_set():
            entry = queue.get_nowait()
            run_id = entry['run_id']
            write_new(batch/'started'/(run_id+'.json'), entry)
            journal = EpisodeJournal(batch/'journals'/(run_id+'.jsonl'))
            task = task_map[entry['task_id']]
            schemas = SCHEMAS[task['task_family']]
            source = slow if entry['profile'] == 'slow_to_fast' else fast
            try:
                result = await run_episode(model, question=task['public']['question'], tool_schemas=schemas,
                    calibration={name: source[name] for name in schemas},
                    call_tool=lambda name, args: call_tool(task['public'], name, args),
                    verify=lambda answer: verify(task['private'], answer),
                    condition=entry['condition'], profile=entry['profile'], budget_s=120,
                    event_sink=journal.emit,
                    metadata={**entry, 'config_hash': config_hash, 'purpose': config['purpose'],
                              'isolation': config['isolation'], 'token_usage': None, 'estimated_cost': None})
                write_new(batch/'episodes'/(run_id+'.json'), {'manifest': entry, 'result': result})
                print(json.dumps({'run_id': run_id, 'task': entry['task_id'], 'condition': entry['condition'],
                                  'profile': entry['profile'], 'reason': result['termination_reason'],
                                  'success': result['deadline_success'], 'elapsed_s': round(result['elapsed_s'], 2)}, ensure_ascii=False), flush=True)
                if result['termination_reason'] in ('service_error', 'protocol_violation'):
                    stop.set()
            except Exception as exc:
                write_new(batch/'errors'/(run_id+'.json'), {'exception_type': type(exc).__name__})
                stop.set()
                print(json.dumps({'run_id': run_id, 'error_type': type(exc).__name__}), flush=True)
            finally:
                journal.close()
                queue.task_done()
    print(json.dumps({'batch': str(batch), 'planned_episodes': len(manifest), 'interrupted': interrupted, 'purpose': config['purpose']}, ensure_ascii=False), flush=True)
    await worker()
    print(json.dumps({'batch': str(batch), 'unstarted': queue.qsize(), 'stopped_on_error': stop.is_set()}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', help='existing development batch; never reruns started entries')
    args = parser.parse_args()
    asyncio.run(main(args.resume))

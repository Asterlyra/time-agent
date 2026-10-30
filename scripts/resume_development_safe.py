"""Preflight existing development data before continuing never-started episodes."""
import argparse
import asyncio
import datetime
import json
from pathlib import Path
from scripts.matrix import digest, write_new
from scripts.run_development import main


def validate(batch, reviewed_cli_error=None):
    batch = Path(batch)
    config = json.loads((batch/'config.json').read_text(encoding='utf-8'))
    manifest = json.loads((batch/'manifest.json').read_text(encoding='utf-8'))
    if digest(manifest) != config['manifest_hash']:
        raise ValueError('manifest changed')
    expected_hash = digest(config)
    observed = 0
    for entry in manifest:
        run_id = entry['run_id']
        started = batch/'started'/(run_id+'.json')
        result = batch/'episodes'/(run_id+'.json')
        if started.exists() and json.loads(started.read_text(encoding='utf-8')) != entry:
            raise ValueError('started entry mismatch')
        if result.exists():
            data = json.loads(result.read_text(encoding='utf-8'))
            if data['manifest'] != entry or data['result']['metadata']['config_hash'] != expected_hash:
                raise ValueError('result or configuration mismatch')
            reason = data['result']['termination_reason']
            if reason in ('service_error', 'protocol_violation'):
                events = [t for e in data['result']['events'] for a in e.get('attempts', [])
                          for t in a.get('harness_event_types', [])]
                allowed = (run_id == reviewed_cli_error and reason == 'protocol_violation'
                           and 'item.completed:error' in events
                           and all(t in {'thread.started', 'turn.started', 'error', 'item.completed:error'}
                                   for t in events))
                if not allowed:
                    raise ValueError('service or protocol failure requires review before continuing')
            observed += 1
    if not observed:
        raise ValueError('no completed record to confirm original configuration')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('batch')
    parser.add_argument('--reviewed-cli-error', help='specific run ID reviewed as a CLI error, not a tool event')
    args = parser.parse_args()
    validate(args.batch, args.reviewed_cli_error)
    if args.reviewed_cli_error:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        write_new(Path(args.batch)/'resume_reviews'/(stamp+'.json'),
                  {'reviewed_run_id': args.reviewed_cli_error,
                   'finding': 'CLI error event, no command/MCP event recorded; error text unavailable; cause unknown',
                   'action': 'continue never-started entries, preserve original failure'})
    asyncio.run(main(args.batch))

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.audit_go_matrix import audit
from scripts.go_study import ROOT, tasks_for, make_manifest
from scripts.matrix import digest, write_new, EpisodeJournal
from src.elapsed_clock import clock_metadata
from src.runner_v2 import run_episode
from tasks import data_v4


class AuditTests(unittest.IsolatedAsyncioTestCase):
    async def fixture(self, batch):
        tasks = tasks_for('diagnostic'); manifest = make_manifest(tasks, 'diagnostic', 17)
        entry = manifest[0]; task = next(t for t in tasks if t['task_id'] == entry['task_id'])
        source = ROOT/'src/runner_v2.py'; frozen = batch/'source_snapshot/src/runner_v2.py'
        frozen.parent.mkdir(parents=True); frozen.write_bytes(source.read_bytes())
        hashes = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
        calibration = {phase: {n: [.01]*3 for n in ('search','read_document','lookup_rows','calculate')} for phase in ('fast','slow')}
        config = {'stage': 'diagnostic', 'manifest_seed': 17, 'models': list(dict.fromkeys(e['model_id'] for e in manifest)),
                  'budget_s': 10, 'shift_fraction': .2, 'fast_s': 2, 'slow_s': 15, 'window': 3,
                  'clock': clock_metadata(), 'calibration': calibration, 'tool_schemas': data_v4.tool_schemas(),
                  'task_hash': digest(tasks), 'code_hash': digest(hashes), 'manifest_hash': digest(manifest)}
        # Preserve the registered model order, independently of manifest order.
        from src.adapters.opencode_go import MODELS
        config['models'] = list(MODELS)
        write_new(batch/'config.json', config); write_new(batch/'config_hash.json', {'sha256': digest(config)})
        write_new(batch/'manifest.json', manifest); write_new(batch/'source_snapshot_hashes.json', hashes)
        write_new(batch/'started'/(entry['run_id']+'.json'), entry)
        class FakeModel:
            async def decide(self, observation, history):
                return {'type': 'submit', 'answer': {'value': task['private']['value'], 'evidence_ids': task['private']['evidence_ids']}}
        schemas = config['tool_schemas'][entry['task_family']]
        journal = EpisodeJournal(batch/'journals'/(entry['run_id']+'.jsonl'))
        try:
            result = await run_episode(FakeModel(), question=task['public']['question'], tool_schemas=schemas,
                calibration={n: calibration['fast'][n] for n in schemas}, call_tool=lambda n,a: {},
                verify=lambda answer: data_v4.verify(task['private'], answer), condition='A',
                budget_s=10, shift_fraction=.2, event_sink=journal.emit, metadata={**entry, 'config_hash': digest(config)})
        finally:
            journal.close()
        path = batch/'episodes'/(entry['run_id']+'.json')
        write_new(path, {'manifest': entry, 'result': result})
        return path

    async def test_audit_rejects_missing_records_and_tampered_score(self):
        with tempfile.TemporaryDirectory() as temp:
            batch = Path(temp); path = await self.fixture(batch)
            self.assertTrue(audit(batch, require_complete=False)['pass'])
            self.assertFalse(audit(batch)['pass'])
            row = json.loads(path.read_text()); row['result']['deadline_success'] = False
            path.write_text(json.dumps(row))
            result = audit(batch, require_complete=False)
            self.assertFalse(result['pass'])
            self.assertIn('deadline_score', [f['check'] for f in result['failures']])

    async def test_audit_rejects_self_consistent_reduced_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            batch = Path(temp); path = await self.fixture(batch)
            manifest = [json.loads(path.read_text())['manifest']]
            config = json.loads((batch/'config.json').read_text()); config['manifest_hash'] = digest(manifest)
            (batch/'config.json').write_text(json.dumps(config))
            (batch/'config_hash.json').write_text(json.dumps({'sha256': digest(config)}))
            (batch/'manifest.json').write_text(json.dumps(manifest))
            result = audit(batch)
            self.assertFalse(result['pass'])
            self.assertIn('registered_matrix', [f['check'] for f in result['failures']])


if __name__ == '__main__':
    unittest.main()

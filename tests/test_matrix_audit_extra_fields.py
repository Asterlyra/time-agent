import json
from pathlib import Path
import tempfile
import unittest

from scripts.audit_go_matrix import audit
from scripts.go_study import tasks_for
from scripts.matrix import digest, EpisodeJournal
from src.runner_v2 import run_episode
from tasks import data_v4
from tests import test_matrix_audit as audit_fixture


class ExtraActionFieldsTests(unittest.IsolatedAsyncioTestCase):
    async def test_extra_action_fields_preserved_and_tool_arguments_still_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            batch = Path(temp)
            helper = audit_fixture.AuditTests('test_audit_rejects_missing_records_and_tampered_score')
            path = await helper.fixture(batch)
            row = json.loads(path.read_text()); entry = row['manifest']
            config = json.loads((batch/'config.json').read_text()); config['fast_s'] = .001
            (batch/'config.json').write_text(json.dumps(config))
            (batch/'config_hash.json').write_text(json.dumps({'sha256': digest(config)}))
            task = next(t for t in tasks_for('diagnostic') if t['task_id'] == entry['task_id'])
            schemas = config['tool_schemas'][entry['task_family']]
            name = 'search' if entry['task_family'] == 'evidence' else 'lookup_rows'
            arguments = {'query': '档案'} if name == 'search' else {'table': 'products', 'filters': {}}
            action = {'type': 'tool', 'name': name, 'arguments': arguments,
                      'cursor': 0, 'annotation': 'ignored top-level field'}
            class FakeModel:
                async def decide(self, observation, history):
                    if not history:
                        return action
                    return {'type': 'submit', 'answer': {'value': task['private']['value'], 'evidence_ids': task['private']['evidence_ids']}}
            journal_path = batch/'journals'/(entry['run_id']+'.jsonl')
            journal_path.unlink()  # Disposable fixture only; no real records.
            journal = EpisodeJournal(journal_path)
            try:
                result = await run_episode(FakeModel(), question=task['public']['question'], tool_schemas=schemas,
                    calibration={n: config['calibration']['fast'][n] for n in schemas},
                    call_tool=lambda n,a: data_v4.call_tool(task['public'],n,a),
                    verify=lambda answer: data_v4.verify(task['private'],answer), condition='A',
                    budget_s=10, shift_fraction=.2, fast_s=.001, event_sink=journal.emit,
                    metadata={**entry, 'config_hash': digest(config)})
            finally:
                journal.close()
            row['result'] = result; path.write_text(json.dumps(row))
            self.assertTrue(audit(batch, require_complete=False)['pass'])
            tool = next(e for e in result['events'] if e['event_type'] == 'tool')
            tool['tool_arguments'] = {'query': 'tampered'} if name == 'search' else {'table': 'batches', 'filters': {}}
            path.write_text(json.dumps(row))
            report = audit(batch, require_complete=False)
            self.assertFalse(report['pass'])
            self.assertIn('tool_matches_model_request', [f['check'] for f in report['failures']])


if __name__ == '__main__':
    unittest.main()

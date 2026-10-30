import unittest
import tempfile
import hashlib
from pathlib import Path
from scripts.run_v5_pilot import selected_tasks, PROFILES, ROOT, CODE_PATHS, load_verified_batch, BUDGET_S, SHIFT_FRACTION
from scripts.matrix import build_manifest, code_hash, digest, write_new
from tasks.data_v4 import tool_schemas


class PilotTests(unittest.IsolatedAsyncioTestCase):
    def test_timing_calibration(self):
        self.assertEqual(BUDGET_S, 180)
        self.assertEqual(SHIFT_FRACTION, .20)
        self.assertEqual(BUDGET_S * SHIFT_FRACTION, 36)

    def test_manifest_covers_all_cells_without_test_split(self):
        tasks = selected_tasks()
        entries = build_manifest(tasks, ['gpt-6-luna'], PROFILES, 1, 4125)
        self.assertEqual(len(entries), 6)
        self.assertEqual(len({(e['task_id'], e['profile'], e['condition']) for e in entries}), 6)
        self.assertTrue(all(t['task_id'].startswith('dev-') for t in tasks))
        self.assertEqual({t['task_family'] for t in tasks}, {'evidence', 'table'})

    def test_resume_only_unstarted_and_checks_config(self):
        (ROOT / 'runs').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='v5-pilot-test-', dir=ROOT/'runs') as temp:
            batch = Path(temp)
            binary = batch/'cli-test.bin'
            binary.write_bytes(b'fake cli')
            tasks = selected_tasks()
            manifest = build_manifest(tasks, ['gpt-6-luna'], PROFILES, 1, 4125)
            config = {'task_hash': digest(tasks), 'manifest_hash': digest(manifest),
                      'code_hash': code_hash(CODE_PATHS), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                      'tool_schemas': tool_schemas()}
            write_new(batch/'config.json', config)
            write_new(batch/'config_hash.json', {'sha256': digest(config)})
            write_new(batch/'manifest.json', manifest)
            entry = manifest[0]
            write_new(batch/'started'/(entry['run_id']+'.json'), entry)
            _, _, _, pending, interrupted = load_verified_batch(batch, tasks, binary)
            self.assertEqual(interrupted, [entry['run_id']])
            self.assertEqual(len(pending), 5)
            config['tool_schemas'] = {}
            (batch/'config.json').write_text(__import__('json').dumps(config), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_verified_batch(batch, tasks, binary)

    def test_completed_service_error_stops_resume(self):
        (ROOT / 'runs').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='v5-pilot-test-', dir=ROOT/'runs') as temp:
            batch = Path(temp); binary = batch/'cli.bin'; binary.write_bytes(b'x')
            tasks = selected_tasks(); manifest = build_manifest(tasks, ['gpt-6-luna'], PROFILES, 1, 4125)
            config = {'task_hash': digest(tasks), 'manifest_hash': digest(manifest), 'code_hash': code_hash(CODE_PATHS),
                      'binary_sha256': hashlib.sha256(b'x').hexdigest(), 'tool_schemas': tool_schemas()}
            write_new(batch/'config.json', config); write_new(batch/'config_hash.json', {'sha256': digest(config)})
            write_new(batch/'manifest.json', manifest); entry = manifest[0]; ident = entry['run_id']
            write_new(batch/'started'/(ident+'.json'), entry)
            (batch/'journals').mkdir(); (batch/'journals'/(ident+'.jsonl')).write_text('{}\n', encoding='utf-8')
            write_new(batch/'episodes'/(ident+'.json'), {'manifest': entry, 'result': {'metadata': {'config_hash': digest(config)}, 'termination_reason': 'service_error'}})
            with self.assertRaisesRegex(ValueError, 'service or protocol'):
                load_verified_batch(batch, tasks, binary)

if __name__ == '__main__':
    unittest.main()

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from scripts.matrix import build_manifest, freeze, verify_frozen, execute_pending
from scripts.analyze_matrix import summarize

class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.tasks = [{'task_id': 't1', 'task_family': 'x', 'template_id': 'x-1', 'data_seed': 1},
                      {'task_id': 't2', 'task_family': 'x', 'template_id': 'x-2', 'data_seed': 1}]
        self.config = {'models':['m'], 'profiles':['fast_to_slow'], 'repeats':2, 'manifest_seed': 1,
                       'protocol':'json', 'model_settings':{}, 'calibration':{}, 'timing':{},
                       'analysis':{}, 'prompt':'p', 'isolation_evidence':'test fixture only'}
    def test_manifest_deterministic_and_pairs(self):
        m = build_manifest(self.tasks, ['m'], ['fast_to_slow'], 2, 7)
        self.assertEqual(m, build_manifest(self.tasks, ['m'], ['fast_to_slow'], 2, 7))
        self.assertEqual(len(m), 12)
        self.assertEqual(len(set(e['run_id'] for e in m)), 12)
        self.assertEqual([set(e['condition'] for e in m[i:i+3]) for i in range(0, 12, 3)], [set('ABC')]*4)
    def test_frozen_hash_and_crash_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'source.py'
            source.write_text('a', encoding='utf-8')
            batch = base / 'batch'
            frozen, manifest = freeze(batch, self.config, self.tasks, [source])
            verify_frozen(batch, self.tasks, [source])
            calls = []
            async def episode(entry, journal):
                calls.append(entry['run_id'])
                journal.emit({'event_type': 'test_event'})
                return {'deadline_success': entry['condition'] == 'C', 'termination_reason': 'submitted'}
            asyncio.run(execute_pending(batch, episode, tasks=self.tasks, code_paths=[source]))
            asyncio.run(execute_pending(batch, episode, tasks=self.tasks, code_paths=[source]))
            self.assertEqual(len(calls), 12)
            result = summarize(batch, iterations=50)
            self.assertEqual(result['C_minus_B_equal_model_mean'], 1)
            self.assertEqual(result['bootstrap_95_percentile'], [1, 1])
            source.write_text('b', encoding='utf-8')
            with self.assertRaises(ValueError): verify_frozen(batch, self.tasks, [source])
    def test_interrupted_not_reexecuted(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base/'s'; source.write_text('x')
            batch = base/'b'; _, manifest = freeze(batch, self.config, self.tasks, [source])
            (batch/'started').mkdir()
            (batch/'started'/(manifest[0]['run_id']+'.json')).write_text('{}')
            async def episode(entry, journal): return {'deadline_success': False, 'termination_reason':'submitted'}
            interrupted = asyncio.run(execute_pending(batch, episode, tasks=self.tasks, code_paths=[source]))
            self.assertEqual(interrupted, [manifest[0]['run_id']])
            self.assertFalse((batch/'episodes'/(manifest[0]['run_id']+'.json')).exists())

    def test_crash_keeps_completed_events_and_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base/'s'; source.write_text('x')
            batch = base/'b'; _, manifest = freeze(batch, self.config, self.tasks, [source])
            async def crashing(entry, journal):
                journal.emit({'event_type': 'model_request', 'offset_s': 1})
                raise RuntimeError('secret is not written')
            with self.assertRaises(RuntimeError):
                asyncio.run(execute_pending(batch, crashing, tasks=self.tasks, code_paths=[source]))
            lines = (batch/'journals'/(manifest[0]['run_id']+'.jsonl')).read_text(encoding='utf-8').splitlines()
            self.assertEqual([json.loads(x)['event_type'] for x in lines],
                             ['episode_started', 'model_request', 'episode_interrupted'])
            self.assertNotIn('secret', '\n'.join(lines))
            async def episode(entry, journal): return {'deadline_success': False, 'termination_reason': 'submitted'}
            interrupted = asyncio.run(execute_pending(batch, episode, tasks=self.tasks, code_paths=[source]))
            self.assertEqual(interrupted, [manifest[0]['run_id']])

    def test_missing_model_excludes_entire_task_cluster(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base/'s'; source.write_text('x')
            batch = base/'b'; config = dict(self.config, models=['m1', 'm2'], repeats=1)
            _, manifest = freeze(batch, config, self.tasks, [source])
            (batch/'episodes').mkdir()
            for entry in manifest:
                if entry['task_id'] == 't2' and entry['model_id'] == 'm2' and entry['condition'] == 'C':
                    continue
                success = entry['condition'] == 'C' and entry['model_id'] == 'm1'
                (batch/'episodes'/(entry['run_id']+'.json')).write_text(json.dumps({
                    'manifest': entry, 'result': {'deadline_success': success, 'termination_reason': 'submitted'}}))
            report = summarize(batch, iterations=50)
            self.assertEqual(report['models_in_aggregate'], ['m1', 'm2'])
            self.assertEqual(report['excluded_incomplete_task_ids'], ['t2'])
            self.assertEqual(report['C_minus_B_equal_model_mean'], .5)
            self.assertEqual(report['bootstrap_95_percentile'], [.5, .5])

if __name__ == '__main__': unittest.main()

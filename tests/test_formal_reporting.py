import json
from pathlib import Path
import tempfile
import unittest

from scripts.go_study import analyze, make_manifest, tasks_for
from scripts.matrix import digest


class FormalReportingTests(unittest.TestCase):
    def fixture(self, root, stage, success):
        config = {'stage': stage}
        manifest = make_manifest(tasks_for(stage), stage, 123)
        (root/'config.json').write_text(json.dumps(config))
        (root/'manifest.json').write_text(json.dumps(manifest))
        (root/'episodes').mkdir()
        for i, entry in enumerate(manifest):
            result = {'metadata': {'config_hash': digest(config)},
                      'deadline_success': success(i, entry), 'termination_reason': 'submitted',
                      'budget_s': 150, 'shift_fraction': .08, 'valid_submission': True,
                      'final_answer': {'value': 1, 'evidence_ids': []},
                      'events': [
                          {'event_type': 'tool', 'tool_name': 'search', 'step_index': 0,
                           'tool_start_offset_s': 13, 'tool_end_offset_s': 28, 'observed_duration_s': 15},
                          {'event_type': 'model_request', 'step_index': 1,
                           'request_start_offset_s': 29, 'response_end_offset_s': 30,
                           'action': {'type': 'submit', 'answer': {'value': 1, 'evidence_ids': []}}}]}
            (root/'episodes'/(entry['run_id']+'.json')).write_text(json.dumps({'manifest': entry, 'result': result}))
        return manifest

    def test_formal_all_correct_and_all_failed_are_structurally_complete(self):
        for correct in (True, False):
            with self.subTest(correct=correct), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); self.fixture(root, 'formal', lambda i, e: correct)
                report = analyze(root, verify=False)
                self.assertTrue(report['all_planned_results_present'])
                self.assertFalse(report['next_stage_applicable'])
                self.assertFalse(report['ready_for_next_stage'])
                self.assertEqual(len(report['gates']), 6)
                self.assertTrue(all(g['pass'] and g['n']==g['expected']==60 and g['check']=='structural_completeness' for g in report['gates']))

    def test_missing_nonstable_row_is_not_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); manifest = self.fixture(root, 'formal', lambda i, e: True)
            entry = next(e for e in manifest if e['profile']=='fast_to_slow')
            (root/'episodes'/(entry['run_id']+'.json')).unlink()
            report = analyze(root, verify=False)
            self.assertFalse(report['all_planned_results_present'])
            self.assertEqual(report['missing'], [entry['run_id']])

    def test_diagnostic_and_development_keep_performance_admission(self):
        for stage in ('diagnostic', 'development'):
            for passing in (True, False):
                with self.subTest(stage=stage, passing=passing), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    outcomes = (lambda i, e: True) if stage=='diagnostic' else (lambda i, e: e['profile']!='fast_to_slow' or e['condition']=='A')
                    self.fixture(root, stage, outcomes if passing else lambda i, e: False)
                    report = analyze(root, verify=False)
                    self.assertTrue(report['next_stage_applicable'])
                    self.assertEqual(report['ready_for_next_stage'], passing)
                    self.assertTrue(all(g['check']!='structural_completeness' for g in report['gates']))


if __name__ == '__main__':
    unittest.main()

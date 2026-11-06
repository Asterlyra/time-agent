import copy
import itertools
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.environment_sensitivity import sensitivity, verify_reviews
from scripts.matrix import digest
from scripts.study_statistics import primary_statistics


def fixture():
    manifest = []; rows = []
    for model in ('one', 'two', 'three'):
        for task in range(2):
            for condition in 'ABC':
                entry = dict(model_id=model, task_id=str(task), task_family='table', repeat=0,
                             profile='fast_to_slow', condition=condition,
                             run_id=f'{model}-{task}-{condition}')
                manifest.append(entry)
                rows.append({'manifest': entry, 'result': {'deadline_success': condition == 'C',
                             'termination_reason': 'submitted', 'valid_submission': True}})
    return manifest, rows


class SensitivityTests(unittest.TestCase):
    def test_review_chain_encodings_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory)
            first = dict(batch=str(batch), immutable_file_hashes={}, result_hashes={})
            previous = batch/'first.json'; previous.write_text(json.dumps(first, indent=2))
            latest = batch/'latest.json'
            for link in (digest(first), hashlib.sha256(previous.read_bytes()).hexdigest()):
                review = dict(first, previous_review=str(previous), previous_review_sha256=link)
                latest.write_text(json.dumps(review))
                self.assertEqual(len(verify_reviews(batch, [], latest)), 2)
            first['changed'] = True; previous.write_text(json.dumps(first))
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                verify_reviews(batch, [], latest)

    def test_bounds_match_exhaustive_counterfactuals_and_frozen_point(self):
        manifest, rows = fixture()
        ids = {'one-0-B', 'one-0-C', 'two-1-B', 'three-0-A'}
        for row in rows:
            if row['manifest']['run_id'] in ids:
                row['result'].update(deadline_success=False, valid_submission=False,
                                     termination_reason='environment_interruption')
        original = copy.deepcopy(rows); report = sensitivity(manifest, rows, ids)
        primary = primary_statistics(manifest, rows, iterations=10)['point']
        self.assertEqual(report['equal_model_mean']['observed'], primary['equal_model_mean'])
        extrema = []
        for assignment in itertools.product((False, True), repeat=len(ids)):
            changed = copy.deepcopy(rows); outcomes = dict(zip(sorted(ids), assignment))
            for row in changed:
                if row['manifest']['run_id'] in outcomes:
                    row['result']['deadline_success'] = outcomes[row['manifest']['run_id']]
            extrema.append(primary_statistics(manifest, changed, iterations=10)['point']['equal_model_mean'])
        self.assertEqual(report['equal_model_mean']['endpoint_bounds'], [min(extrema), max(extrema)])
        self.assertEqual(rows, original)
        self.assertEqual(report['models']['one']['unaffected_pairs_n'], 1)
        self.assertEqual(report['models']['three']['affected_pairs'], 0)

    def test_no_environment_bounds_collapse(self):
        manifest, rows = fixture(); report = sensitivity(manifest, rows, set())
        self.assertEqual(report['equal_model_mean']['endpoint_bounds'], [1, 1])

    def test_incomplete_duplicate_and_unreviewed_rejected(self):
        manifest, rows = fixture()
        for bad in (rows[:-1], rows+[rows[0]]):
            with self.assertRaisesRegex(ValueError, 'unique complete'):
                sensitivity(manifest, bad, set())
        with self.assertRaisesRegex(ValueError, 'exactly match'):
            sensitivity(manifest, rows, {'unknown'})

    def test_no_unaffected_pairs_is_undefined(self):
        manifest, rows = fixture(); ids = set()
        for row in rows:
            if row['manifest']['model_id'] == 'one' and row['manifest']['condition'] == 'B':
                ids.add(row['manifest']['run_id'])
                row['result'].update(termination_reason='environment_interruption', valid_submission=False)
        report = sensitivity(manifest, rows, ids)
        self.assertIsNone(report['models']['one']['unaffected_pairs_descriptive'])
        self.assertIsNone(report['equal_model_mean']['unaffected_pairs_descriptive'])


if __name__ == '__main__':
    unittest.main()

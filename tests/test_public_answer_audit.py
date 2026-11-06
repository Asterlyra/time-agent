import copy
import unittest
from scripts.audit_public_answers import audit, public_oracle
from tasks import data_v4


class PublicOracleTests(unittest.TestCase):
    def test_all_public_questions_match_numbers_and_source_sets(self):
        report=audit()
        self.assertTrue(report['pass'])
        self.assertEqual(report['splits']['dev']['n'],8)
        self.assertEqual(report['splits']['test']['n'],20)

    def test_evidence_selection_does_not_consult_private_ids(self):
        task=copy.deepcopy(data_v4.generate('dev')[0])
        result=public_oracle(task['public'])
        task['private']={'value':-12345,'evidence_ids':['invented']}
        self.assertEqual(public_oracle(task['public']),result)
        self.assertNotEqual(result['evidence_ids'],task['private']['evidence_ids'])


if __name__=='__main__':unittest.main()

import unittest
from unittest.mock import patch
from scripts.go_gates import check_formal_readiness,check_verification
from scripts.go_study import CODE_PATHS,ROOT


class ReadinessTests(unittest.TestCase):
    def test_missing_evidence_does_not_create_formal_authorization(self):
        with self.assertRaises(FileNotFoundError):check_verification(ROOT/'reports/nonexistent-evidence.json',CODE_PATHS)

    def test_failed_development_blocks_formal(self):
        config={'stage':'development','model_settings':{'max_tokens':2048}}
        with patch('scripts.go_gates.check_verification',return_value={}), \
             patch('scripts.go_gates.check_diagnostic',return_value=(ROOT,{'model_settings':config['model_settings']})), \
             patch('scripts.go_study.load_batch',return_value=(ROOT,config,[])), \
             patch('scripts.go_study.analyze',return_value={'ready_for_next_stage':False}):
            with self.assertRaisesRegex(ValueError,'quality gates'):
                check_formal_readiness('dev','diag','offline',CODE_PATHS)

    def test_settings_changed_after_diagnostic_blocks_formal(self):
        config={'stage':'development','model_settings':{'max_tokens':4096}}
        with patch('scripts.go_gates.check_verification',return_value={}), \
             patch('scripts.go_gates.check_diagnostic',return_value=(ROOT,{'model_settings':{'max_tokens':2048}})), \
             patch('scripts.go_study.load_batch',return_value=(ROOT,config,[])), \
             patch('scripts.go_study.analyze',return_value={'ready_for_next_stage':True}):
            with self.assertRaisesRegex(ValueError,'settings differ'):
                check_formal_readiness('dev','diag','offline',CODE_PATHS)


if __name__=='__main__':unittest.main()

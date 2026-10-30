import os
import unittest
from scripts.isolation_mock import check, minimal_environment


class TestIsolationMock(unittest.TestCase):
    def test_allowlist_excludes_fake_secrets_and_control_pipes(self):
        result = minimal_environment({'SystemRoot': 'C:/Windows', 'OPENAI_API_KEY': 'fake',
                                      'CODEX_APP_TOOLS_PIPE_PATH': 'fake', 'PATH': 'fake'})
        self.assertNotIn('OPENAI_API_KEY', result)
        self.assertNotIn('CODEX_APP_TOOLS_PIPE_PATH', result)
        self.assertNotIn('PATH', result)
        if os.name == 'nt': self.assertEqual(result['SystemRoot'], 'C:/Windows')

    def test_clean_environment_does_not_isolate_files(self):
        self.assertEqual(check(), {'fake_secret_absent': True,
                                   'canary_readable_without_os_isolation': True})

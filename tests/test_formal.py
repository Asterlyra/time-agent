import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.run_formal import validate_inputs, readiness, prepare, validate_development, CODE_FILES, ROOT
from scripts.matrix import build_manifest, digest, verify_frozen
from tasks.data_v2 import generate

class FormalGateTests(unittest.TestCase):
    def config(self, root):
        p = Path(root)/'evidence.json'; p.write_text('{}', encoding='utf-8')
        evidence = {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        samples = {name:[2.0,2.0,2.0] for name in ('search','read_document','lookup_rows','calculate')}
        return {'models':['gpt-6-luna'], 'profiles':['stable_fast','fast_to_slow','slow_to_fast'],
                'repeats':2, 'concurrency':1, 'manifest_seed': 9,
                'timing':{'budget_s':120, 'fast_s':2, 'slow_s':15, 'shift_fraction':.5, 'window':3, 'max_steps':20},
                'calibration':{'fast':samples, 'slow':samples},
                'resource_budget':{'max_episodes':360, 'max_budget_s_per_episode':120},
                'protocol':'one json action', 'prompt':'recorded in adapter source', 'model_settings':{'effort':'default'},
                'analysis':{'primary':'C-B'}, 'isolation_evidence':evidence, 'development_evidence':evidence}
    def test_default_refuses_and_no_batch_created(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.config(root)
            with patch('scripts.run_formal.validate_development'):
                with self.assertRaisesRegex(RuntimeError, 'isolation'):
                    prepare(Path(root)/'batch', config)
            self.assertFalse((Path(root)/'batch').exists())
    def test_reject_unbudgeted_or_changed_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.config(root)
            validate_inputs(config)
            config['resource_budget']['max_episodes'] = 359
            with self.assertRaises(ValueError): validate_inputs(config)
            config['resource_budget']['max_episodes'] = 360
            Path(config['isolation_evidence']['path']).write_text('altered')
            with self.assertRaises(ValueError): validate_inputs(config)
    def test_missing_config_has_no_implicit_defaults(self):
        with self.assertRaises(ValueError): validate_inputs({})

    def test_freeze_detects_change_to_underlying_task_scorer(self):
        self.assertIn(ROOT / 'tasks/data.py', CODE_FILES)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            copied = []
            for source in CODE_FILES:
                target = root / 'code' / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                copied.append(target)
            config = self.config(root)
            with patch('scripts.run_formal.readiness'), patch('scripts.run_formal.CODE_FILES', tuple(copied)):
                prepare(root / 'batch', config)
            dependency = root / 'code/tasks/data.py'
            dependency.write_text(dependency.read_text(encoding='utf-8') + '\n# changed scorer\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'changed'):
                verify_frozen(root / 'batch', generate('test'), copied)

    def test_development_requires_all_traces_and_shift_observation(self):
        with tempfile.TemporaryDirectory() as root:
            batch = Path(root); (batch/'episodes').mkdir()
            config = {'fixture': True}
            (batch/'config.json').write_text(json.dumps(config), encoding='utf-8')
            manifest = build_manifest(generate('dev'), ['gpt-6-luna'], repeats=1)
            (batch/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            for entry in manifest:
                events = [{'event_type':'tool','is_censored':False,'observed_duration_s':1,
                           'tool_start_offset_s':60,'tool_end_offset_s':61},
                          {'event_type':'model_request','request_start_offset_s':62}]
                result = {'metadata':{'config_hash':digest(config)}, 'termination_reason':'submitted',
                          'valid_submission':True,'budget_s':120,'shift_fraction':.5,'events':events}
                (batch/'episodes'/(entry['run_id']+'.json')).write_text(json.dumps({'manifest':entry,'result':result}), encoding='utf-8')
            validate_development(batch/'manifest.json')
            (batch/'episodes'/(manifest[0]['run_id']+'.json')).unlink()
            with self.assertRaises(FileNotFoundError): validate_development(batch/'manifest.json')

if __name__ == '__main__': unittest.main()

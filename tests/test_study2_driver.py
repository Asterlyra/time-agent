"""End-to-end plumbing test for the S2 driver with a scripted stand-in adapter."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from scripts import study2


class FakeGoItems:
    """Behaves like GoItems without any network: fetches a fixed number, then submits."""

    def __init__(self, model, *, client=None, session_id=None, max_tokens=2048, stream=False):
        self.model = model
        self.last_diagnostics = {'usage': {'allowance': 0.001}}

    async def decide(self, observation, history):
        seen = {}
        for item in history:
            result = item.get('tool_result') or {}
            if 'item_id' in result:
                seen[result['item_id']] = result['value']
        if len(seen) >= 2:
            return {'type': 'submit', 'answer': {'items': seen}}
        target = f'K{len(seen) + 1:02d}'
        return {'type': 'tool', 'name': 'fetch', 'arguments': {'item_id': target}}


class DriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_run_analyze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = study2.ROOT, study2.CODE_PATHS, study2.GoItems
            study2.ROOT = root
            study2.CODE_PATHS = (root / 'scripts' / 'study2.py',)
            study2.CODE_PATHS[0].parent.mkdir(parents=True)
            study2.CODE_PATHS[0].write_text('x\n')
            study2.GoItems = FakeGoItems
            try:
                batch = await study2.prepare('pilot', budget=None, shift=None, fast=0.01,
                                             slow=0.02, tasks_limit=1, reason='plumbing test')
                config = json.loads((batch / 'config.json').read_text())
                manifest = json.loads((batch / 'manifest.json').read_text())
                self.assertEqual(len(manifest), 3 * 3 * 4)  # models x profiles x conditions
                self.assertEqual(len({e['block_id'] for e in manifest}), 9)
                report = await study2.execute(batch)
                self.assertTrue(report['all_planned_results_present'])
                self.assertEqual(report['completed'], len(manifest))
                self.assertEqual(report['failures'], 0)
                rows = [json.loads(p.read_text()) for p in (batch / 'episodes').glob('*.json')]
                self.assertTrue(all(r['result']['score'] == 2 for r in rows))
                self.assertTrue(all(r['result']['termination_reason'] == 'submitted' for r in rows))
                self.assertEqual(len(list((batch / 'journals').glob('*.jsonl'))), len(manifest))
                self.assertEqual(config['budget_by_model'], {m: study2.DEFAULTS['budget_s'] for m in config['models']})
            finally:
                study2.ROOT, study2.CODE_PATHS, study2.GoItems = original

    async def test_manifest_is_balanced_and_blocks_are_adjacent(self):
        tasks = study2.data_v6.generate('dev')[:2]
        manifest = study2.build_manifest2(tasks, list(study2.MODELS), study2.PROFILES)
        self.assertEqual(len(manifest), 3 * 2 * 3 * 4)
        per_block = {}
        for entry in manifest:
            per_block.setdefault((entry['model_id'], entry['block_id']), []).append(entry)
        self.assertTrue(all(len(v) == 4 for v in per_block.values()))
        for entries in per_block.values():
            self.assertEqual(sorted(e['condition'] for e in entries), list('ABCO'))
        # Every condition appears once per block and in every positional slot overall.
        positions = {c: set() for c in 'ABCO'}
        for entries in per_block.values():
            for i, e in enumerate(entries):
                positions[e['condition']].add(i)
        self.assertTrue(all(v == {0, 1, 2, 3} for v in positions.values()))


if __name__ == '__main__':
    unittest.main()


class InterruptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_started_without_result_is_archived_as_environment_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = study2.ROOT, study2.CODE_PATHS, study2.GoItems
            study2.ROOT = root
            study2.CODE_PATHS = (root / 'scripts' / 'study2.py',)
            study2.CODE_PATHS[0].parent.mkdir(parents=True)
            study2.CODE_PATHS[0].write_text('x\n')
            study2.GoItems = FakeGoItems
            try:
                batch = await study2.prepare('pilot', fast=0.01, slow=0.02, tasks_limit=1)
                await study2.execute(batch)
                victim = next((batch / 'episodes').glob('*.json'))
                victim.unlink()  # simulate a host suspend before the result was written
                report = study2.analyze(batch)
                self.assertEqual(report['completed'], len(json.loads((batch / 'manifest.json').read_text())))
                self.assertEqual(len(report['interrupted']), 1)
                archived = [c for c in report['cells'] if c['no_submission']]
                self.assertTrue(archived)
                # A resume skips the archived episode and completes the rest.
                await study2.execute(batch, resume=True)
                self.assertTrue((batch / 'episodes' / (report['interrupted'][0] + '.json'))
                                .exists() is False)
            finally:
                study2.ROOT, study2.CODE_PATHS, study2.GoItems = original

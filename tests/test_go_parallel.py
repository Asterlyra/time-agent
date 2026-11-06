import asyncio
import collections
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import go_study
from scripts.matrix import code_hash,digest,write_new
from tasks import data_v4


class ParallelExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def run_matrix(self, environment_failure=False):
        tasks=go_study.tasks_for('diagnostic');manifest=go_study.make_manifest(tasks,'diagnostic',123)
        active=collections.Counter();peak=collections.Counter();global_active=0;global_peak=0;sessions=[];seen=[]
        class Model:
            last_diagnostics=None
            def __init__(self,model,**kwargs):sessions.append(kwargs['session_id'])
        async def episode(model,**kwargs):
            nonlocal global_active,global_peak
            metadata=kwargs['metadata'];name=metadata['model_id'];seen.append(metadata['run_id'])
            active[name]+=1;global_active+=1;peak[name]=max(peak[name],active[name]);global_peak=max(global_peak,global_active)
            try:await asyncio.sleep(.02)
            finally:active[name]-=1;global_active-=1
            return {'metadata':metadata,'deadline_success':not environment_failure,'termination_reason':'environment_interruption' if environment_failure else 'submitted','elapsed_s':.02,
                    'events':[],'service_error_flags':[],'budget_s':1,'shift_fraction':.2}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);batch=root/'runs/go-diagnostic-fixture';batch.mkdir(parents=True)
            source=root/'source.py';source.write_text('# fixture')
            config={'stage':'diagnostic','models':list(go_study.MODELS),'budget_s':1,'shift_fraction':.2,
                'calibration':{phase:{n:[0]*3 for n in go_study.NAMES} for phase in ('fast','slow')},
                'tool_schemas':data_v4.tool_schemas(),'max_tokens':10,'concurrency':{'global':6,'per_model':2},
                'limits':{'max_requests_per_model':100,'max_reported_allowance_per_model':1},
                'task_hash':digest(tasks),'manifest_hash':digest(manifest),'code_hash':code_hash([source])}
            write_new(batch/'config.json',config);write_new(batch/'config_hash.json',{'sha256':digest(config)});write_new(batch/'manifest.json',manifest)
            with patch.object(go_study,'ROOT',root),patch.object(go_study,'CODE_PATHS',(source,)), \
                 patch.object(go_study,'OpenCodeGo',Model),patch.object(go_study,'run_episode',episode),contextlib.redirect_stdout(io.StringIO()):
                await go_study.execute(batch)
            expected=6 if environment_failure else 18
            self.assertEqual(len(seen),expected);self.assertEqual(len(set(seen)),expected)
            self.assertEqual(len(set(sessions)),expected)
            self.assertEqual(global_peak,6)
            self.assertEqual(set(peak.values()),{2})
            self.assertEqual(len(list((batch/'episodes').glob('*.json'))),expected)
            self.assertFalse((batch/'run_lock.json').exists())
            if environment_failure:
                result=go_study.analyze(batch,verify=False)
                self.assertFalse(result['ready_for_next_stage'])
                self.assertEqual(result['environment_interruptions'],6)
                self.assertEqual(len(result['missing']),12)

    async def test_concurrency_limits_unique_sessions_and_complete_matrix(self):
        await self.run_matrix()

    async def test_environment_failure_halts_without_starting_remaining_episodes(self):
        await self.run_matrix(environment_failure=True)


if __name__=='__main__':unittest.main()

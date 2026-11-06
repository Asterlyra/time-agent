import asyncio
import json
import unittest

import httpx

from src.adapters.opencode_go import OpenCodeGo, APIServiceError, MODELS
from src.runner_v2 import run_episode
from tasks import data_v4


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_families_same_public_observation_and_session(self):
        requests=[]
        def handler(request):
            requests.append(request)
            action=json.dumps({'type':'submit','answer':{'value':7,'evidence_ids':[]}})
            usage={'cost':0,'opencode':{'billing_source':'go','allowance':.001,'tokens':{'input':20,'reasoning':5}}}
            if '/anthropic/' in str(request.url):
                return httpx.Response(200,json={'content':[{'type':'text','text':action}],'stop_reason':'end_turn','usage':usage})
            return httpx.Response(200,json={'choices':[{'message':{'content':action},'finish_reason':'stop'}],'usage':usage})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for model in MODELS:
                adapter=OpenCodeGo(model,api_key='test-secret',client=client,session_id='ses_test')
                for _ in range(2):
                    action=await adapter.decide({'question':'public question'},[])
                    self.assertEqual(action['answer']['value'],7)
                self.assertEqual(adapter.last_diagnostics['usage']['billing_source'],'go')
                self.assertNotIn('test-secret',repr(adapter.last_diagnostics))
        for request in requests:
            self.assertEqual(request.headers['x-opencode-session'],'ses_test')
            body=json.loads(request.content)
            self.assertNotIn('tools',body)
            self.assertNotIn('functions',body)
            self.assertNotIn('private',request.content.decode())
        self.assertIn('/anthropic/v1/messages',requests[2].url.path)

    async def test_service_error_does_not_log_body_or_key(self):
        def handler(request): return httpx.Response(429,json={'error':{'message':'secret key and private content'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            model=OpenCodeGo(MODELS[0],api_key='secret',client=client)
            with self.assertRaises(APIServiceError) as caught: await model.decide({},[])
            self.assertEqual(caught.exception.status_code,429)
            self.assertNotIn('secret',str(caught.exception)+repr(model.last_diagnostics))

    async def test_paid_fallback_is_rejected(self):
        def handler(request):
            return httpx.Response(200,json={'usage':{'cost':.001,'opencode':{'billing_source':'balance'}}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            model=OpenCodeGo(MODELS[0],api_key='secret',client=client)
            with self.assertRaisesRegex(APIServiceError,'unexpected_paid_billing'): await model.decide({},[])

    async def test_deadline_cancels_inflight_http(self):
        cancelled=[]
        async def handler(request):
            try: await asyncio.sleep(10)
            finally: cancelled.append(True)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            model=OpenCodeGo(MODELS[0],api_key='secret',client=client)
            result=await run_episode(model,question='public',tool_schemas={'search':{}},
                calibration={'search':[0]*3},call_tool=lambda n,a:{},verify=lambda a:True,budget_s=.03)
            self.assertEqual(result['termination_reason'],'timeout_model')
            self.assertEqual(cancelled,[True])

    async def test_private_answer_never_sent_and_forbidden_tool_never_runs(self):
        task=data_v4.generate('dev')[0]
        requests=[]; executions=[]
        actions=[{'type':'tool','name':'shell','arguments':{'command':'cat private_answers/dev.json'}},
                 {'type':'submit','answer':{'value':task['private']['value'],'evidence_ids':task['private']['evidence_ids']}}]
        def handler(request):
            body=json.loads(request.content);requests.append(body)
            # The adapter receives neither private keys nor a bundled database.
            observation=json.loads(body['messages'][1]['content'])['observation']
            self.assertEqual(set(observation),{'question','tools','calibration_samples_s','time_status'})
            self.assertNotIn('private',observation)
            self.assertNotIn('documents',observation)
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(actions.pop(0))}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            model=OpenCodeGo(MODELS[0],api_key='secret',client=client)
            result=await run_episode(model,question=task['public']['question'],
                tool_schemas=data_v4.tool_schemas()['evidence'],calibration={'search':[0]*3,'read_document':[0]*3},
                call_tool=lambda n,a:executions.append((n,a)),verify=lambda a:data_v4.verify(task['private'],a),budget_s=1)
            self.assertTrue(result['deadline_success'])
            self.assertEqual(executions,[])
            self.assertEqual(len(requests),2)
            self.assertNotIn('private_answers',json.dumps(requests[0]))

    async def test_truncated_or_nonfinite_output_is_invalid_action(self):
        for content in ('{"type":', '{"type":"submit","answer":{"value":NaN}}'):
            def handler(request): return httpx.Response(200,json={'choices':[{'message':{'content':content}}]})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                model=OpenCodeGo(MODELS[0],api_key='secret',client=client)
                self.assertIsInstance(await model.decide({},[]),str)


if __name__=='__main__': unittest.main()

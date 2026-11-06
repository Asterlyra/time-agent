import asyncio
import json
import unittest
import httpx
from src.adapters.opencode_go import OpenCodeGo,MODELS,APIServiceError
from src.runner_v2 import run_episode


def frame(data):return ('data: '+(data if isinstance(data,str) else json.dumps(data,ensure_ascii=False))+'\n\n').encode()


class Bytes(httpx.AsyncByteStream):
    def __init__(self,data,fragment=False,stall=False):self.data=data;self.fragment=fragment;self.stall=stall;self.closed=False
    async def __aiter__(self):
        if self.fragment:
            for byte in self.data:yield bytes([byte])
        else:yield self.data
        if self.stall:await asyncio.sleep(10)
    async def aclose(self):self.closed=True


class SSETests(unittest.IsolatedAsyncioTestCase):
    async def call(self,model,data,fragment=False):
        stream=Bytes(data,fragment)
        def handler(request):
            body=json.loads(request.content);self.assertTrue(body['stream'])
            if model!=MODELS[1]:self.assertEqual(body['stream_options'],{'include_usage':True})
            return httpx.Response(200,headers={'Content-Type':'text/event-stream'},stream=stream)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter=OpenCodeGo(model,api_key='test-secret',client=client,stream=True)
            result=await adapter.decide({},[])
            self.assertTrue(stream.closed)
            return result,adapter.last_diagnostics

    async def test_chat_fragments_and_final_usage(self):
        data=frame({'choices':[{'index':0,'delta':{'reasoning_content':'private reasoning','content':'{"type":"submit",'},'finish_reason':None}]})
        data+=frame({'choices':[{'index':0,'delta':{'content':'"answer":{"value":7,"evidence_ids":["证据"]}}'},'finish_reason':'stop'}]})
        data+=frame({'choices':[],'usage':{'cost':0,'opencode':{'billing_source':'go','allowance':.001}}})+frame('[DONE]')
        result,diag=await self.call(MODELS[0],data,True)
        self.assertEqual(result['answer']['evidence_ids'],['证据'])
        self.assertEqual(diag['usage']['allowance'],.001)
        self.assertNotIn('private reasoning',repr(diag))
        self.assertGreater(diag['response_bytes'],0)

    async def test_native_messages_ignore_thinking_and_merge_usage(self):
        data=frame({'type':'message_start','message':{'usage':{'input_tokens':10}}})
        data+=frame({'type':'content_block_delta','delta':{'type':'thinking_delta','thinking':'secret thought'}})
        data+=frame({'type':'content_block_start','content_block':{'type':'text','text':''}})
        data+=frame({'type':'content_block_delta','delta':{'type':'text_delta','text':'{"type":"submit"}'}})
        data+=frame({'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':20,'cost':0,'opencode':{'billing_source':'go'}}})
        data+=frame({'type':'message_stop'})
        result,diag=await self.call(MODELS[1],data,True)
        self.assertEqual(result,{'type':'submit'})
        self.assertEqual(diag['usage']['input_tokens'],10)
        self.assertEqual(diag['usage']['output_tokens'],20)
        self.assertNotIn('secret thought',repr(diag))

    async def test_missing_terminal_is_connection_failure(self):
        data=frame({'choices':[{'delta':{'content':'{}'},'finish_reason':'stop'}]})
        with self.assertRaises(ConnectionError):await self.call(MODELS[2],data)

    async def test_upstream_error_is_classified_without_body(self):
        data=frame({'type':'error','error':{'type':'overloaded_error','message':'private error details'}})
        with self.assertRaises(APIServiceError) as e:await self.call(MODELS[1],data)
        self.assertEqual(e.exception.status_code,503)
        self.assertNotIn('private',str(e.exception))

    async def test_streaming_paid_fallback_is_rejected(self):
        data=frame({'choices':[{'delta':{'content':'{}'},'finish_reason':'stop'}]})
        data+=frame({'choices':[],'usage':{'cost':.01,'opencode':{'billing_source':'balance'}}})+frame('[DONE]')
        with self.assertRaisesRegex(APIServiceError,'unexpected_paid_billing'):await self.call(MODELS[0],data)

    async def test_stream_cancel_closes_connection_and_preserves_partial_usage(self):
        stream=Bytes(frame({'type':'message_start','message':{'usage':{'input_tokens':10}}}),stall=True)
        def handler(request):return httpx.Response(200,stream=stream)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            model=OpenCodeGo(MODELS[1],api_key='secret',client=client,stream=True)
            r=await run_episode(model,question='q',tool_schemas={'search':{}},calibration={'search':[0]*3},
                call_tool=lambda n,a:{},verify=lambda a:True,budget_s=.03)
            self.assertEqual(r['termination_reason'],'timeout_model')
            self.assertTrue(stream.closed)
            self.assertEqual(r['events'][0]['attempts'][0]['adapter_diagnostics']['usage']['input_tokens'],10)


if __name__=='__main__':unittest.main()

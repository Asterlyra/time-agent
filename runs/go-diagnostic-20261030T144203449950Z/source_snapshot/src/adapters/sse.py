"""Bounded native inference SSE accumulation; no reasoning content is retained."""
import json
import time


class IncompleteStream(ConnectionError):
    pass


class StreamServiceError(RuntimeError):
    def __init__(self,status_code=502):
        self.status_code=status_code
        super().__init__('upstream_stream_error')


async def payloads(response,diagnostics,started):
    buffer=b'';fields=[];size=0
    async for chunk in response.aiter_bytes():
        size+=len(chunk);diagnostics['response_bytes']=size
        if diagnostics.get('first_response_byte_offset_s') is None:
            diagnostics['first_response_byte_offset_s']=time.monotonic()-started
        if size>2_000_000:raise ValueError('bounded stream exceeded')
        buffer+=chunk
        while b'\n' in buffer:
            line,buffer=buffer.split(b'\n',1);line=line.rstrip(b'\r')
            if not line:
                if fields:yield b'\n'.join(fields).decode('utf-8');fields=[]
            elif line.startswith(b'data:'):
                value=line[5:]
                fields.append(value[1:] if value.startswith(b' ') else value)
    # A terminal marker must be a complete SSE record, not a partial line.


async def accumulate(response,*,anthropic,diagnostics,on_usage,started=None):
    started=time.monotonic() if started is None else started
    text=[];usage={};finish=None;terminal=False;message_started=False
    events=payloads(response,diagnostics,started)
    try:
        async for payload in events:
            diagnostics['stream_event_count']=diagnostics.get('stream_event_count',0)+1
            if payload=='[DONE]':
                if anthropic:raise ValueError('unexpected native terminator')
                terminal=True;break
            event=json.loads(payload,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite event')))
            if not isinstance(event,dict):raise ValueError('invalid stream event')
            kind=event.get('type')
            if kind=='error' or isinstance(event.get('error'),dict):
                error=event.get('error',{})
                if not isinstance(error,dict):error={}
                code=429 if error.get('type')=='rate_limit_error' else 503 if error.get('type')=='overloaded_error' else 502
                raise StreamServiceError(code)
            fresh=event.get('usage')
            if anthropic:
                if kind=='message_start':
                    message_started=True;fresh=event.get('message',{}).get('usage')
                elif kind=='content_block_start':
                    block=event.get('content_block',{})
                    if block.get('type')=='text' and isinstance(block.get('text'),str):text.append(block['text'])
                elif kind=='content_block_delta':
                    delta=event.get('delta',{})
                    if delta.get('type')=='text_delta' and isinstance(delta.get('text'),str):text.append(delta['text'])
                elif kind=='message_delta':
                    finish=event.get('delta',{}).get('stop_reason',finish)
                elif kind=='message_stop':
                    terminal=True
            else:
                for choice in event.get('choices',[]):
                    if choice.get('index',0)!=0:continue
                    delta=choice.get('delta',{})
                    if isinstance(delta.get('content'),str):text.append(delta['content'])
                    if choice.get('finish_reason') is not None:finish=choice['finish_reason']
            if isinstance(fresh,dict):
                usage.update(fresh);on_usage(usage)
            if terminal:break
    finally:
        await events.aclose()
    if not terminal or finish is None or (anthropic and not message_started):
        raise IncompleteStream('incomplete_inference_stream')
    content=''.join(text)
    if anthropic:return {'content':[{'type':'text','text':content}],'stop_reason':finish,'usage':usage}
    return {'choices':[{'message':{'content':content},'finish_reason':finish}],'usage':usage}

"""Text-only, cancellable Go inference adapter. Never executes model output.

The API family is fixed per model; only public runner observations/history leave
the host. Credentials are read locally and never included in diagnostics.
"""
import asyncio
import json
import math
import os
from pathlib import Path
import uuid
from src.elapsed_clock import elapsed_time

import httpx
from src.adapters.sse import accumulate,IncompleteStream,StreamServiceError

MODELS = ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash')
BASE_URL = 'https://opencode.ai/inference/go'
PROMPT = (
    'You are participating in a local decision experiment. Return exactly one '
    'JSON object as your final response. Choose either '
    '{"type":"tool","name":"...","arguments":{...}} or '
    '{"type":"submit","answer":{"value":number,"evidence_ids":["..."]}}. '
    'Use only the experiment tools described in the observation, by requesting '
    'a JSON action; never execute tools yourself. The host executes them and '
    'returns results in history. Submit only when you have the required answer '
    'and evidence. There are no other resources or tools available. '
    'A duration reference is based on past observations and does not guarantee '
    'future duration. Do not output explanations, Markdown or multiple actions.'
)


class APIServiceError(RuntimeError):
    def __init__(self, status_code=None, category='service_error'):
        self.status_code, self.category = status_code, category
        super().__init__(category)  # No HTTP bodies, URLs with secrets or headers.


def load_api_key():
    value = os.environ.get('OPENCODE_GO_API_KEY')
    if value:
        return value
    # Read only this project's dedicated key; do not source arbitrary shell code
    # or change the user's global OpenCode credentials.
    local = Path(__file__).resolve().parents[2] / '.env'
    if local.exists():
        for line in local.read_text(encoding='utf-8').splitlines():
            if line.startswith('OPENCODE_GO_API_KEY='):
                value = line.partition('=')[2].strip()
                if value:
                    return value
    path = Path.home() / '.local/share/opencode/auth.json'
    try:
        record = json.loads(path.read_text(encoding='utf-8')).get('opencode-go', {})
    except (OSError, ValueError):
        raise APIServiceError(category='credentials_unavailable') from None
    if record.get('type') != 'api' or not isinstance(record.get('key'), str) or not record['key']:
        raise APIServiceError(category='credentials_unavailable')
    return record['key']


def _strict_json(value):
    return json.loads(value, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def _safe_usage(usage):
    """Allow only numeric counters and known billing labels from the service."""
    if not isinstance(usage, dict):
        return {}
    result = {}
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'input_tokens', 'output_tokens', 'cost'):
        value = usage.get(key)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            result[key] = value
    extra = usage.get('opencode', {})
    if isinstance(extra, dict):
        billing = extra.get('billing_source')
        if billing in ('go', 'go-plus', 'go-teams', 'balance', 'free', 'byok'):
            result['billing_source'] = billing
        for key in ('allowance', 'list_cost'):
            value = extra.get(key)
            if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                result[key] = value
        tokens = extra.get('tokens')
        if isinstance(tokens, dict):
            result['billed_tokens'] = {k: v for k, v in tokens.items()
                if k in ('input', 'output', 'reasoning', 'cache_read', 'cache_write_5m', 'cache_write_1h')
                and type(v) is int and v >= 0}
    return result


class OpenCodeGo:
    def __init__(self, model, *, api_key=None, client=None, session_id=None, max_tokens=2048, stream=False):
        if model not in MODELS:
            raise ValueError('model must be one of the three registered models')
        self.model = model
        self._key = api_key or load_api_key()
        self.session_id = session_id or ('ses_time_' + uuid.uuid4().hex)
        self.max_tokens = max_tokens
        self.stream = stream
        self._owned_client = client is None
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20), follow_redirects=False)
        self.last_diagnostics = None
        self.usage_records = []

    def request(self, observation, history):
        text = json.dumps({'observation': observation, 'history': history}, ensure_ascii=False, allow_nan=False)
        common = {'model': self.model, 'max_tokens': self.max_tokens, 'stream': self.stream}
        if self.model == 'qwen3.8-flash':
            return '/anthropic/v1/messages', {**common, 'system': PROMPT,
                'messages': [{'role': 'user', 'content': text}]}
        if self.stream: common['stream_options']={'include_usage':True}
        return '/openai/v1/chat/completions', {**common, 'messages': [
            {'role': 'system', 'content': PROMPT}, {'role': 'user', 'content': text}]}

    async def decide(self, observation, history):
        path, body = self.request(observation, history)
        self.last_diagnostics = {'status_codes': [], 'error_count': 0,
            'timing_semantics': 'complete_sse_terminal_parsed' if self.stream else 'complete_http_json_body_parsed',
            'streaming':self.stream,'usage':{},'response_bytes':0,'first_response_byte_offset_s':None}
        headers = {'Authorization': 'Bearer ' + self._key, 'Content-Type': 'application/json',
            'User-Agent': 'time-agent-research/1.0', 'x-opencode-session': self.session_id}
        if self.model == 'qwen3.8-flash':
            headers['anthropic-version'] = '2023-06-01'
        request_started=elapsed_time()
        try:
            # Bounded response; cancellation exits the stream context and closes
            # the connection. No background thread can keep an inference alive.
            async with self.client.stream('POST', BASE_URL + path, json=body, headers=headers) as response:
                status = response.status_code
                self.last_diagnostics['status_codes'] = [status]
                if status != 200:
                    self.last_diagnostics['error_count'] = 1
                    raise APIServiceError(status, 'http_error')
                if self.stream:
                    def usage_update(value):self.last_diagnostics['usage']=_safe_usage(value)
                    data=await accumulate(response,anthropic=self.model=='qwen3.8-flash',
                        diagnostics=self.last_diagnostics,on_usage=usage_update,started=request_started)
                else:
                    chunks, size = [], 0;received=request_started
                    async for chunk in response.aiter_bytes():
                        size += len(chunk);self.last_diagnostics['response_bytes']=size
                        if self.last_diagnostics['first_response_byte_offset_s'] is None:
                            self.last_diagnostics['first_response_byte_offset_s']=elapsed_time()-received
                        if size > 2_000_000:
                            raise APIServiceError(category='response_too_large')
                        chunks.append(chunk)
                    data = _strict_json(b''.join(chunks))
        except StreamServiceError as exc:
            self.last_diagnostics['error_count']=1
            self.last_diagnostics['error_category']='upstream_stream_error'
            raise APIServiceError(exc.status_code,'upstream_stream_error') from None
        except (httpx.TransportError, httpx.TimeoutException,IncompleteStream) as exc:
            self.last_diagnostics['error_count'] = 1
            self.last_diagnostics['transport_error_type']=type(exc).__name__
            raise ConnectionError('inference_transport_error') from None
        except (ValueError, UnicodeError):
            raise APIServiceError(category='invalid_http_json') from None
        if not isinstance(data, dict):
            raise APIServiceError(category='invalid_http_shape')
        usage = _safe_usage(data.get('usage'))
        self.last_diagnostics['usage'] = usage
        self.usage_records.append(usage)
        if usage.get('billing_source') in ('balance', 'byok') or usage.get('cost', 0) > 0:
            raise APIServiceError(category='unexpected_paid_billing')
        try:
            if self.model == 'qwen3.8-flash':
                text = ''.join(x['text'] for x in data['content'] if x.get('type') == 'text')
                finish = data.get('stop_reason')
            else:
                choice = data['choices'][0]
                text = choice['message']['content']
                finish = choice.get('finish_reason')
            self.last_diagnostics['finish_reason'] = finish if finish in ('stop', 'length', 'end_turn', 'max_tokens') else 'other'
            if not isinstance(text, str):
                raise TypeError()
        except (KeyError, IndexError, TypeError):
            raise APIServiceError(category='missing_text_action') from None
        try:
            return _strict_json(text)
        except ValueError:
            # Invalid model output receives the same runner feedback as an
            # invalid CLI action, not a fabricated service failure or correction.
            return text[:16000]

    async def close(self):
        if self._owned_client:
            await self.client.aclose()

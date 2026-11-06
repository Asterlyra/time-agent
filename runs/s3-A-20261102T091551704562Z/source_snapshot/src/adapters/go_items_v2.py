"""Study 3 adapter: same transport, item protocol with an optional commit action."""
import json
import uuid

import httpx

from src.adapters.opencode_go import BASE_URL, OpenCodeGo, load_api_key

MODELS = ('glm-5.3-flash', 'qwen3.8-flash', 'deepseek-v4.1-flash', 'mimo-v2.6-flash')

PROMPT_ITEMS = (
    'You are participating in a timed local experiment. Return exactly one JSON '
    'object as your final response, choosing one of: '
    '{"type":"tool","name":"fetch","arguments":{"item_id":"K03"}}, '
    '{"type":"submit"}, or {"type":"commit","reserve_s":12}. '
    'Each fetch banks the points of one item and costs real wall-clock time drawn '
    'from a heavy-tailed distribution, so occasional calls are very long; the costs '
    'are not known in advance and may differ between item sizes and across the '
    'episode. A submission is processed as one more request and ends the episode: '
    'the host scores every item you have already banked. If the budget expires '
    'before your submission is processed, the episode scores zero and everything is '
    'lost. The host may refuse a fetch that cannot finish in time, and may submit on '
    'your behalf once the remaining budget reaches the reserve; any such event is '
    'reported in the history. Maximise the points banked at the moment your '
    'submission is processed. Do not output explanations, Markdown or multiple '
    'actions.'
)

__all__ = ['MODELS', 'PROMPT_ITEMS', 'GoItemsV2']


class GoItemsV2(OpenCodeGo):
    """Same transport as OpenCodeGo, but the four-model registry is local."""

    def __init__(self, model, *, api_key=None, client=None, session_id=None,
                 max_tokens=2048, stream=False):
        if model not in MODELS:
            raise ValueError('model must be one of the four registered models')
        self.model = model
        self._key = api_key or load_api_key()
        self.session_id = session_id or ('ses_time_' + uuid.uuid4().hex)
        self.max_tokens = max_tokens
        self.stream = stream
        self._owned_client = client is None
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(300, connect=20),
                                                  follow_redirects=False)
        self.last_diagnostics = None
        self.usage_records = []

    def request(self, observation, history):
        text = json.dumps({'observation': observation, 'history': history},
                          ensure_ascii=False, allow_nan=False)
        common = {'model': self.model, 'max_tokens': self.max_tokens, 'stream': self.stream}
        if self.model in ('qwen3.8-flash', 'qwen3.8-max', 'minimax-m3'):
            return '/anthropic/v1/messages', {**common, 'system': PROMPT_ITEMS,
                'messages': [{'role': 'user', 'content': text}]}
        if self.stream:
            common['stream_options'] = {'include_usage': True}
        return '/openai/v1/chat/completions', {**common, 'messages': [
            {'role': 'system', 'content': PROMPT_ITEMS}, {'role': 'user', 'content': text}]}

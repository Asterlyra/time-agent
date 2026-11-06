"""Study 2 Go adapter: same transport as OpenCodeGo, item-submission protocol.

Only the system prompt and the submission schema differ. Transport, retries,
cancellation and usage accounting are inherited unchanged.
"""
import json

from src.adapters.opencode_go import MODELS, OpenCodeGo

PROMPT_ITEMS = (
    'You are participating in a timed local decision experiment. Return exactly '
    'one JSON object as your final response. Choose either '
    '{"type":"tool","name":"fetch","arguments":{"item_id":"K03"}} or '
    '{"type":"submit","answer":{"items":{"K03":4821}}}. '
    'The host executes tools; you never execute them yourself. Each tool call '
    'consumes real wall-clock time from a fixed budget, and the time a call takes '
    'may change during the episode. Submitting ends the episode immediately. '
    'Only submitted items with the exact integer value score a point; unsubmitted '
    'items score zero. If the budget expires before you submit, the episode scores '
    'zero. Maximise the number of correct items in the submission you make before '
    'the deadline. A duration reference, when present, summarises past observations '
    'and does not guarantee the duration of a future call. '
    'Do not output explanations, Markdown or multiple actions.'
)

__all__ = ['MODELS', 'PROMPT_ITEMS', 'GoItems']


class GoItems(OpenCodeGo):
    def request(self, observation, history):
        text = json.dumps({'observation': observation, 'history': history},
                          ensure_ascii=False, allow_nan=False)
        common = {'model': self.model, 'max_tokens': self.max_tokens, 'stream': self.stream}
        if self.model == 'qwen3.8-flash':
            return '/anthropic/v1/messages', {**common, 'system': PROMPT_ITEMS,
                'messages': [{'role': 'user', 'content': text}]}
        if self.stream:
            common['stream_options'] = {'include_usage': True}
        return '/openai/v1/chat/completions', {**common, 'messages': [
            {'role': 'system', 'content': PROMPT_ITEMS}, {'role': 'user', 'content': text}]}

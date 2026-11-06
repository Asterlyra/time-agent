"""Measure tool delay samples outside episodes using synthetic public-only inputs."""
import asyncio
import time
from tasks.data import call_tool

CASES = {
    'search': ({'documents': [{'id': 'CAL-D', 'text': 'calibration record', 'summary': 'calibration record'}]}, {'query': 'calibration'}),
    'read_document': ({'documents': [{'id': 'CAL-D', 'text': 'calibration record'}]}, {'id': 'CAL-D'}),
    'lookup_rows': ({'tables': {'products': [{'id': 'CAL-P', 'product': 'sample', 'unit_cost': 3}]}}, {'table': 'products', 'filters': {}}),
    'calculate': ({'tables': {}}, {'expression': '2+3'}),
}


async def calibrate(names, target_s, repeats=3, tool_call=call_tool):
    if repeats < 3 or target_s < 0 or any(name not in CASES for name in names):
        raise ValueError('invalid calibration settings')
    async def sample(name):
        public, args = CASES[name]
        start = time.monotonic()
        result = tool_call(public, name, args)
        if 'error' in result:
            raise RuntimeError('calibration tool failed')
        await asyncio.sleep(max(0, target_s - (time.monotonic() - start)))
        return time.monotonic() - start
    # Separate samples are measured concurrently, outside task budgets.
    return {name: list(values) for name, values in zip(names, await asyncio.gather(
        *(asyncio.gather(*(sample(name) for _ in range(repeats))) for name in names)))}

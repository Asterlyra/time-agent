"""Suspend-inclusive monotonic deadlines for the Go research harness.

Darwin CLOCK_MONOTONIC_RAW includes sleep; Linux's identically named clock
does not, so Linux must use CLOCK_BOOTTIME. Unsupported hosts fail closed.
Asyncio timers alone are insufficient on Darwin because its loop clock pauses.
"""
import asyncio
import contextlib
import sys
import time


def clock_id(platform=None):
    platform = sys.platform if platform is None else platform
    name = 'CLOCK_MONOTONIC_RAW' if platform == 'darwin' else 'CLOCK_BOOTTIME' if platform.startswith('linux') else None
    if name is None or not hasattr(time, name):
        raise RuntimeError('suspend-inclusive experiment clock unavailable')
    return name, getattr(time, name)


def elapsed_time():
    return time.clock_gettime(clock_id()[1])


def clock_metadata():
    name, ident = clock_id()
    return {'protocol': 'continuous_deadline_v1', 'clock': name, 'platform': sys.platform,
            'includes_suspend': True, 'resolution_s': time.clock_getres(ident),
            'guard_interval_s': .25, 'suspend_threshold_s': 1.0}


class EnvironmentInterruption(asyncio.TimeoutError):
    """Host suspended during an active episode; never a model capability error."""


class EpisodeClock:
    def __init__(self):
        self.start = elapsed_time()
        self.active_start = time.monotonic()

    def time(self):
        return elapsed_time()

    def elapsed(self):
        return self.time() - self.start

    def suspend_gap(self, stamp=None):
        continuous, active = stamp if stamp is not None else (elapsed_time(), time.monotonic())
        return max(0.0, (continuous-self.start) - (active-self.active_start))

    def check(self, stamp=None):
        if self.suspend_gap(stamp) > 1.0:
            raise EnvironmentInterruption('host_suspend_detected')

    async def wait(self, awaitable, deadline):
        """Cancel on continuous deadline, including after wake or late completion.

        Capture completion before journaling or subsequent event-loop work.
        A timely returned submission stays timely if later disk I/O is slow.
        """
        task = None
        finished = []
        try:
            self.check()
            if elapsed_time() >= deadline:
                raise asyncio.TimeoutError()
            async def observed():
                try:
                    return await awaitable
                finally:
                    finished.extend((elapsed_time(), time.monotonic()))
            task = asyncio.create_task(observed())
            while True:
                if task.done():
                    self.check(finished)
                    if finished[0] >= deadline:
                        raise asyncio.TimeoutError()
                    return task.result()
                self.check()
                remaining = deadline-elapsed_time()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                await asyncio.wait({task}, timeout=min(.25, remaining))
        finally:
            if task is None:
                if hasattr(awaitable, 'close'):
                    awaitable.close()
            else:
                if not task.done():
                    task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                if not finished and hasattr(awaitable, 'close'):
                    awaitable.close()

"""Worker-local monotonic measurements; no shared account or device state."""
import threading
import time
from contextlib import contextmanager
from functools import wraps

_local = threading.local()


def reset():
    _local.metrics = {}


def snapshot():
    return {key: dict(value) for key, value in getattr(_local, 'metrics', {}).items()}


@contextmanager
def measure(category):
    started = time.perf_counter()
    try:
        yield
    finally:
        if not hasattr(_local, 'metrics'):
            reset()
        item = _local.metrics.setdefault(category, dict(calls=0, seconds=0.0))
        item['calls'] += 1
        item['seconds'] += time.perf_counter()-started


def measured(category):
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            with measure(category):
                return function(*args, **kwargs)
        return call
    return decorate


def wait(seconds, *, cancelled=lambda: False):
    """Bounded interruptible deliberate waiting; Stop prevents delayed action."""
    deadline = time.monotonic()+seconds
    with measure('deliberate_wait'):
        while not cancelled():
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(.1, remaining))


def pause(sleeper, seconds):
    """Measure an existing injectable wait without changing its timing contract."""
    with measure('deliberate_wait'):
        sleeper(seconds)


def poll(observe, expected, *, attempts=4, cadence=.3, cancelled=lambda: False):
    """Capture immediately after an action; wait only after an unmet condition."""
    from top_heroes_auto.automation.guard import SafetyError

    for number in range(attempts):
        if cancelled():
            raise SafetyError('Run cancelled before transition capture.')
        result = observe()
        if expected(result):
            return result
        if number+1 < attempts:
            wait(cadence, cancelled=cancelled)
    return result

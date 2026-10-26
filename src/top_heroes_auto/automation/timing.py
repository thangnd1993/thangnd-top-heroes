"""Worker-local monotonic measurements; no shared account or device state."""
import threading
import time
from contextlib import contextmanager
from functools import wraps

_local = threading.local()


def reset():
    _local.metrics = {}
    _local.stack = []


def wait_epoch():
    """Increments on every deliberate wait; lets callers prove no time was spent waiting."""
    return getattr(_local, 'epoch', 0)


def _bump_epoch():
    _local.epoch = getattr(_local, 'epoch', 0) + 1


def snapshot():
    return {key: dict(value) for key, value in getattr(_local, 'metrics', {}).items()}


@contextmanager
def measure(category):
    if not hasattr(_local, 'metrics'):
        reset()
    frame = dict(children=0.0)
    _local.stack.append(frame)
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter()-started
        _local.stack.pop()
        if _local.stack:
            _local.stack[-1]['children'] += elapsed
        item = _local.metrics.setdefault(category, dict(calls=0, seconds=0.0, exclusive_seconds=0.0))
        item['calls'] += 1
        item['seconds'] += elapsed
        item['exclusive_seconds'] += max(0.0, elapsed-frame['children'])


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
    _bump_epoch()
    with measure('deliberate_wait'):
        while not cancelled():
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(.1, remaining))


def pause(sleeper, seconds):
    """Measure an existing injectable wait without changing its timing contract."""
    _bump_epoch()
    with measure('deliberate_wait'):
        sleeper(seconds)
    _bump_epoch()


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

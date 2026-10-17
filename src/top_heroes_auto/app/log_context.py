"""Attach current production caller context to the existing rotating log."""
import logging
from contextvars import ContextVar
from logging.handlers import QueueHandler, QueueListener
from queue import Full, Queue

run_id = ContextVar('run_id', default='-')
instance_index = ContextVar('instance_index', default='-')


class RunContextFilter(logging.Filter):
    def filter(self, record):
        record.run_id = run_id.get()
        record.instance_index = instance_index.get()
        return True


class DiagnosticQueue(QueueHandler):
    def __init__(self, destination):
        super().__init__(Queue(maxsize=2048))
        self.destination = destination
        self.dropped_repetitive = 0
        self.addFilter(RunContextFilter())

    def enqueue(self, record):
        try:
            self.queue.put_nowait(record)
        except Full:
            if record.levelno >= logging.WARNING or getattr(record, 'category', '') == 'operation':
                self.destination.handle(record)
            else:
                self.dropped_repetitive += 1


class DiagnosticListener(QueueListener):
    def enqueue_sentinel(self):
        self.queue.put(self._sentinel)

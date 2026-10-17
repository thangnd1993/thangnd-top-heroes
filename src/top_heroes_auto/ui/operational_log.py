"""Bounded UI projection only; the rotating diagnostic file retains all records."""
import logging
import threading
from collections import deque


class OperationalLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.pending = deque(maxlen=500)
        self.buffer_lock = threading.Lock()
        self.technical = False
        self.last = None
        self.repeats = 0
        self.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%H:%M:%S'))

    def emit(self, record):
        # WARN/ERROR and actual operational outcomes always remain visible.
        if not (self.technical or record.levelno >= logging.WARNING
                or getattr(record, 'category', '') == 'operation'):
            return
        message = self.format(record)
        key = (record.levelno, record.getMessage())
        with self.buffer_lock:
            if key == self.last:
                self.repeats += 1
                return
            if self.repeats:
                self.pending.append(f'Thông báo trước lặp lại {self.repeats} lần; xem log chi tiết.')
            self.last, self.repeats = key, 0
            self.pending.append(message)

    def drain(self):
        with self.buffer_lock:
            result = list(self.pending)
            self.pending.clear()
        return result

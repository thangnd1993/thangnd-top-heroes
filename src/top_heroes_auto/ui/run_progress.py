"""Pure projection of live run events for the dashboard (no Qt, no I/O).

Only real counts and real task states are shown; nothing here estimates a
percentage. Complete technical detail stays in the rotating log and reports."""
import time
from dataclasses import dataclass, field

FLOW_LABELS = {'idle': 'Quà tích lũy', 'vip': 'VIP', 'ranking': 'BXH', 'shop': 'Tiệm',
               'guild': 'Hội', 'mail': 'Thư', 'events': 'Sự kiện'}

# Structured error categories shared with the project's existing status model.
ERROR_LABELS = {
    'NAVIGATION_FAILED': 'Không điều hướng được',
    'SCREEN_UNKNOWN': 'Màn hình không xác định',
    'ADB_UNAVAILABLE': 'ADB chưa sẵn sàng',
    'TARGET_IDENTITY_AMBIGUOUS': 'Không xác minh được giả lập',
    'PROTECTED_TARGET': 'Giả lập được bảo vệ',
    'ACTION_NOT_AVAILABLE': 'Chưa có quà để nhận',
    'ACTION_DISPATCHED_UNVERIFIED': 'Đã gửi thao tác, chưa xác minh',
    'REWARD_VERIFIED': 'Đã xác minh quà',
    'RECOVERABLE_FEATURE_ERROR': 'Lỗi tính năng; tiếp tục mục khác',
}

_KEYWORDS = (  # first match wins; the order encodes severity of the underlying cause
    ('PROTECTED_TARGET', ('protected', 'được bảo vệ')),
    ('TARGET_IDENTITY_AMBIGUOUS', ('identity', 'stable', 'ambiguous', 'boot id', 'không khớp')),
    ('ADB_UNAVAILABLE', ('adb', 'transport', 'serial', 'absent')),
    ('ACTION_DISPATCHED_UNVERIFIED', ('possible', 'unverified', 'chưa xác minh', 'dispatched')),
    ('SCREEN_UNKNOWN', ('unknown', 'không xác định', 'screen')),
    ('NAVIGATION_FAILED', ('navigation', 'điều hướng', 'home', 'recovery')),
)


def classify_error(message: str) -> str:
    text = (message or '').casefold()
    for category, words in _KEYWORDS:
        if any(word in text for word in words):
            return category
    return 'RECOVERABLE_FEATURE_ERROR'


@dataclass
class AccountProgress:
    index: int
    status: str = 'Đang chờ'
    flow: str = ''
    detail: str = ''
    done: int = 0
    blocked: int = 0
    category: str = ''
    started: float | None = None
    finished: float | None = None

    def line(self) -> str:
        """Short, honest status line, e.g. 'Sự kiện · đang xử lý (2 xong, 1 bị chặn)'."""
        parts = [self.status]
        if self.flow and self.finished is None:
            parts[0] = f'{FLOW_LABELS.get(self.flow, self.flow)} · đang xử lý'
        if self.done or self.blocked:
            parts.append(f'{self.done} xong, {self.blocked} bị chặn')
        if self.category and self.category in ERROR_LABELS and self.blocked:
            parts.append(ERROR_LABELS[self.category])
        return ' · '.join(parts)


@dataclass
class RunProgress:
    run_id: int | None = None
    started: float | None = None
    accounts: dict = field(default_factory=dict)
    clock: object = time.monotonic

    def _account(self, index: int) -> AccountProgress:
        return self.accounts.setdefault(index, AccountProgress(index))

    def begin(self, run_id: int):
        if self.run_id != run_id:
            self.run_id, self.started, self.accounts = run_id, self.clock(), {}

    def account_started(self, index: int):
        account = self._account(index)
        account.status, account.started, account.finished = 'Đang chạy', self.clock(), None

    def account_finished(self, index: int, label: str, detail: str = ''):
        account = self._account(index)
        account.status, account.finished = label, self.clock()
        account.detail, account.flow = detail, ''

    def flow_event(self, index: int, flow: str, state: str, message: str = ''):
        account = self._account(index)
        if state == 'STARTED':
            account.flow, account.detail = flow, message
        elif state == 'COMPLETE' or state == 'ALREADY_COMPLETED':
            account.done += 1
            account.flow, account.detail = '', message
        elif state.startswith('BLOCKED') or state.startswith('NOT_RUN'):
            account.blocked += 1
            account.flow, account.detail = '', message
            account.category = classify_error(message)
        else:
            account.detail = message

    def elapsed(self) -> float:
        return 0.0 if self.started is None else max(0.0, self.clock() - self.started)

    def active_workers(self) -> int:
        return sum(1 for a in self.accounts.values() if a.started is not None and a.finished is None)

    def finished_accounts(self) -> int:
        return sum(1 for a in self.accounts.values() if a.finished is not None)


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f'{hours:d}:{minutes:02d}:{secs:02d}' if hours else f'{minutes:02d}:{secs:02d}'

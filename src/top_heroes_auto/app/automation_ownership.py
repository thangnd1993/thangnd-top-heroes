"""Kernel-owned fleet lease: crash releases it; PID/name metadata never grants it."""
import hashlib
import json
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from top_heroes_auto.automation.guard import SafetyError

_owner = ContextVar('automation_owner', default=None)
_local_lock = threading.Lock()
_local_keys = set()


def fleet_namespace(namespace):
    path = Path(namespace)
    if path.name.casefold() in {'ldconsole.exe', 'dnconsole.exe'}:
        return str(path.resolve().parent / 'vms').casefold()
    return namespace.casefold()


class AutomationBusy(SafetyError):
    def __init__(self):
        super().__init__('AUTOMATION_BUSY: another run owns this LDPlayer fleet; no mutation dispatched.')


class AutomationLease:
    def __init__(self, namespace, folder):
        self.namespace = fleet_namespace(namespace)
        self.key = hashlib.sha256(self.namespace.encode()).hexdigest()
        self.path = Path(folder) / ('automation-owner-' + self.key[:16] + '.json')
        self.run_id = uuid4().hex
        self.process_token = _PROCESS_TOKEN
        self.handle = None
        self.active = False
        self.owner_thread = None
        self.stale_recovered = False

    def _acquire_kernel(self):
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes

            api = ctypes.WinDLL('kernel32', use_last_error=True)
            api.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
            api.CreateMutexW.restype = wintypes.HANDLE
            api.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            api.WaitForSingleObject.restype = wintypes.DWORD
            api.ReleaseMutex.argtypes = (wintypes.HANDLE,)
            api.CloseHandle.argtypes = (wintypes.HANDLE,)
            handle = api.CreateMutexW(None, False, 'Global\\TopHeroesAutoManager.Automation.' + self.key)
            if not handle:
                raise OSError(ctypes.get_last_error(), 'Unable to establish automation ownership.')
            result = api.WaitForSingleObject(handle, 0)
            if result not in (0, 0x80):
                api.CloseHandle(handle)
                if result == 0x102:
                    raise AutomationBusy()
                raise OSError(ctypes.get_last_error(), 'Automation ownership wait failed.')
            self.stale_recovered = result == 0x80
            self.handle = api, handle
        else:
            import fcntl
            import tempfile

            handle = open(Path(tempfile.gettempdir()) / ('topheroes-' + self.key + '.lock'), 'a+b')
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                raise AutomationBusy() from None
            self.handle = handle

    def _write(self, state):
        payload = dict(run_id=self.run_id, pid=os.getpid(), process_token=self.process_token,
                       namespace=self.namespace, state=state, stale_recovered=self.stale_recovered,
                       timestamp=datetime.now(timezone.utc).isoformat())
        temporary = self.path.with_suffix('.' + self.run_id + '.tmp')
        try:
            temporary.write_bytes(json.dumps(payload, indent=2).encode())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def __enter__(self):
        with _local_lock:
            if self.key in _local_keys:
                raise AutomationBusy()
            _local_keys.add(self.key)
        try:
            self._acquire_kernel()  # OS ownership, not a saved PID.
        except BaseException:
            with _local_lock:
                _local_keys.discard(self.key)
            raise
        self.active = True
        self.owner_thread = threading.current_thread()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                try:
                    prior = json.loads(self.path.read_text(encoding='utf-8'))
                    self.stale_recovered |= prior.get('state') == 'ACTIVE'
                except (ValueError, OSError):
                    self.stale_recovered = True
            # Unique per-process nonce plus durable per-run UUID; PID reuse cannot
            # steal a live kernel mutex or authorize recovery from this metadata.
            self.process_token = _PROCESS_TOKEN
            self._write('ACTIVE')
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        try:
            if self.active:
                self._write('RELEASED')
        finally:
            self.active = False
            if self.handle is not None:
                if os.name == 'nt':
                    api, handle = self.handle
                    api.ReleaseMutex(handle)
                    api.CloseHandle(handle)
                else:
                    self.handle.close()
                self.handle = None
            with _local_lock:
                _local_keys.discard(self.key)


_PROCESS_TOKEN = uuid4().hex


@contextmanager
def mutation_ownership(manager, *, folder=None):
    namespace = fleet_namespace(manager.namespace)
    current = _owner.get()
    if current is not None:
        if (not current.active or current.namespace != namespace
                or current.owner_thread is None or not current.owner_thread.is_alive()):
            raise SafetyError('Automation ownership token is stale or belongs to another fleet.')
        yield current
        return
    data = folder or getattr(manager, 'data_dir', None) or manager.store.path.parent
    with AutomationLease(namespace, data) as lease:
        token = _owner.set(lease)
        try:
            yield lease
        finally:
            _owner.reset(token)


def exclusive_automation(function):
    @wraps(function)
    def owned(manager, *args, **kwargs):
        folder = args[0] if args and isinstance(args[0], Path) else None
        outer = _owner.get() is None
        with mutation_ownership(manager, folder=folder):
            if outer and hasattr(manager.store, 'recover_interrupted'):
                manager.store.recover_interrupted(manager.namespace)
            return function(manager, *args, **kwargs)
    return owned


def exclusive_command(function):
    @wraps(function)
    def owned(manager, *args, **kwargs):
        with mutation_ownership(manager):
            return function(manager, *args, **kwargs)
    return owned


def ownership_evidence():
    lease=_owner.get()
    if lease is None or not lease.active:
        raise SafetyError('No active exclusive automation ownership.')
    return dict(run_id=lease.run_id,pid=os.getpid(),process_token=lease.process_token,
                namespace=lease.namespace,guard='OS_KERNEL_MUTEX',state='ACTIVE',
                stale_recovered=lease.stale_recovered,record=str(lease.path))

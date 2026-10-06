"""No LDPlayer config replacement/rollback/name mutation transport is exposed."""
import threading

_lock = threading.Lock()
_attempts = 0


def name_write_attempts():
    with _lock:
        return _attempts


def reject_name_write(message):
    global _attempts
    with _lock:
        _attempts += 1
    raise ValueError(message)


def guard_command(command, args):
    if command not in {'list2', 'launch', 'quit', 'adb'} or any(
            str(arg).casefold().split('=', 1)[0] in {'--name', '--title', 'statussettings.playername'} for arg in args):
        reject_name_write('LDPlayer command blocked: instance names are read-only; allowlist required.')

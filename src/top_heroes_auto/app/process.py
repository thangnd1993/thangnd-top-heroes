"""The single subprocess boundary. No shell interpolation or unbounded waits."""

import locale
import os
import subprocess

from top_heroes_auto.ldplayer.name_safety import guard_command


class CommandError(RuntimeError):
    pass


class Process:
    def run(self, args: list[str], timeout: int = 20) -> bytes:
        executable = args[0].replace("\\", "/").rsplit("/", 1)[-1].casefold() if args else ""
        if executable in {"ldconsole.exe", "dnconsole.exe", "ldconsole", "dnconsole"}:
            try:
                guard_command(args[1] if len(args) > 1 else '', args[2:])
                command = args[1]
                rest = args[2:]
                if command == 'list2':
                    valid = not rest
                else:
                    valid = (len(rest) == (4 if command == 'adb' else 2) and rest[0] == '--index'
                             and rest[1].isascii() and rest[1].isdigit()
                             and (command != 'adb' or rest[2] == '--command'))
                if not valid:
                    raise ValueError('Explicit indexed LDPlayer command shape required; no target fallback.')
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                timeout=timeout,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CommandError(f"Không thực thi được lệnh: {exc}") from exc
        if result.returncode:
            raise CommandError(f"Lệnh thất bại ({result.returncode}): {decode(result.stderr)[:500]}")
        return result.stdout


def decode(data: bytes) -> str:
    for encoding in dict.fromkeys(["utf-8-sig", locale.getpreferredencoding(False), "mbcs"]):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise CommandError("Không giải mã được dữ liệu CLI; không suy đoán tên hoặc index.")

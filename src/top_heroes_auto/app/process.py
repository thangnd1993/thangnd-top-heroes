"""The single subprocess boundary. No shell interpolation or unbounded waits."""

import locale
import os
import subprocess


class CommandError(RuntimeError):
    pass


class Process:
    def run(self, args: list[str], timeout: int = 20) -> bytes:
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

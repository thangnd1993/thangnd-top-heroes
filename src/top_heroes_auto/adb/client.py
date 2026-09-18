import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from top_heroes_auto.app.process import Process, decode
from top_heroes_auto.automation.guard import SafetyError


@dataclass(frozen=True)
class Target:
    index: int
    name: str
    serial: str
    boot_id: str


def valid_boot_id(value: str) -> str:
    try:
        parsed = UUID(value)
        if parsed.int == 0 or str(parsed) != value.lower():
            raise ValueError()
        return str(parsed)
    except (ValueError, AttributeError) as exc:
        raise SafetyError("Không xác minh được Android boot ID.") from exc


def validate_serial(serial: str) -> str:
    if not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9._:\-]+", serial):
        raise SafetyError("ADB target bắt buộc phải được chỉ định rõ.")
    if serial.startswith("-"):
        raise SafetyError("ADB serial không hợp lệ.")
    return serial


def validate_package(package: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", package):
        raise SafetyError("Tên gói Android không hợp lệ.")
    return package


class ADB:
    def __init__(self, executable: str, process: Process):
        self.executable, self.process = executable, process

    def devices(self) -> dict[str, str]:
        output = decode(self.process.run([self.executable, "devices"]))
        devices = {}
        for line in output.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[1] in ("device", "offline", "unauthorized"):
                serial = validate_serial(fields[0])
                if serial in devices:
                    raise SafetyError("ADB trả về serial trùng lặp.")
                devices[serial] = fields[1]
        return devices

    def start_server(self):
        """Idempotently start only the bundled ADB server; never restart it."""
        return decode(self.process.run([self.executable, "start-server"]))

    def _target(self, serial: str, *args: str) -> bytes:
        return self.process.run([self.executable, "-s", validate_serial(serial), *args])

    def boot_id(self, serial: str) -> str:
        return valid_boot_id(
            decode(self._target(serial, "shell", "cat", "/proc/sys/kernel/random/boot_id")).strip()
        )

    def connect(self, endpoint: str):
        # Only an explicit loopback endpoint, never guessed from the index.
        if not re.fullmatch(r"127\.0\.0\.1:[0-9]{1,5}", endpoint):
            raise SafetyError("Chỉ kết nối địa chỉ ADB loopback được chỉ định rõ.")
        if not 1 <= int(endpoint.rsplit(":", 1)[1]) <= 65535:
            raise SafetyError("Cổng ADB không hợp lệ.")
        return decode(self.process.run([self.executable, "connect", endpoint]))

    def _shell(self, serial: str, *args: str) -> str:
        return decode(self._target(serial, "shell", *args)).strip()

    def _capture(self, serial: str) -> bytes:
        data = self._target(serial, "exec-out", "screencap", "-p")
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise SafetyError("ADB không trả về ảnh PNG hợp lệ.")
        return data

    def _read_apk(self, serial: str, remote: str) -> bytes:
        path = PurePosixPath(remote)
        if (
            not re.fullmatch(r"/[A-Za-z0-9_./=\-]+/base\.apk", remote)
            or not path.is_absolute()
            or ".." in path.parts
        ):
            raise SafetyError("Đường dẫn APK không hợp lệ.")
        data = self._target(serial, "exec-out", "cat", remote)
        if not data.startswith(b"PK"):
            raise SafetyError("ADB không trả về APK hợp lệ.")
        return data

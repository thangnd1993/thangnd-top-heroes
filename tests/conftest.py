import pytest

from top_heroes_auto.app.service import Manager
from top_heroes_auto.ldplayer.client import Installation, LDPlayer
from top_heroes_auto.storage.store import Store

BOOT = "ce068632-fc3e-4090-a8d7-ae8d9fe353f5"


class FakeProcess:
    def __init__(self):
        self.calls = []
        self.listing = "0,Main-Thang,1,2,1,101,102\n7,Farm-007,3,4,1,201,202\n8,Farm-008,0,0,0,-1,-1\n"
        self.serial = "emulator-5568"
        self.device_boot = BOOT
        self.cli_boot = BOOT
        self.auto_lifecycle = True
        self.devices_output = "List of devices attached\nemulator-5568\tdevice\n"
        self.hook = None

    def run(self, args, timeout=20):
        self.calls.append(args)
        if self.hook:
            self.hook(args)
        if args[1:] == ["list2"]:
            return self.listing.encode()
        if args[1] == "adb":
            assert args[2:4] == ["--index", "7"]
            return (self.serial if args[-1] == "get-serialno" else self.cli_boot).encode()
        if args[1:] == ["devices"]:
            return self.devices_output.encode()
        if args[1:] == ["start-server"]:
            return b""
        if args[1:] == ["kill-server"]:
            return b""
        if args[1] == "connect":
            return f"connected to {args[2]}".encode()
        if args[1] == "-s":
            if args[-1] == "/proc/sys/kernel/random/boot_id":
                return self.device_boot.encode()
            if "screencap" in args:
                return b"\x89PNG\r\n\x1a\nmock-png"
            if "exec-out" in args and "cat" in args:
                return b"PKmock-apk"
            if "pm" in args and "path" in args:
                return b"package:/data/app/com.example.game-AbCd123==/base.apk\n"
            return b"package:com.example.game\n"
        if args[0].endswith("aapt.exe"):
            return b"application-label:'Th\xe1\xbb\x9di \xc4\x90\xe1\xba\xa1i Anh H\xc3\xb9ng'\n"
        if args[1] in ("launch", "quit", "reboot"):
            assert args[2:] == ["--index", "7"]
            if self.auto_lifecycle:
                row = "7,Farm-007,3,4,1,201,202" if args[1] == "launch" else "7,Farm-007,0,0,0,-1,-1"
                self.listing = (
                    "\n".join(row if line.startswith("7,") else line for line in self.listing.splitlines())
                    + "\n"
                )
            return b""
        raise AssertionError(f"Unexpected command: {args}")


@pytest.fixture
def rig(tmp_path):
    store = Store(tmp_path / "config.sqlite3")
    process = FakeProcess()
    ld = LDPlayer(Installation(tmp_path / "ldconsole.exe", tmp_path / "adb.exe"), process)
    manager = Manager(ld, store, tmp_path)
    manager.refresh()
    manager.protect(0, True)
    manager.select(7, True)
    process.calls.clear()
    return manager, process, store

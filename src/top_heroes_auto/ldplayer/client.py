import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from top_heroes_auto.app.process import Process, decode


@dataclass(frozen=True)
class Instance:
    index: int
    name: str
    android_started: bool
    pid: int
    vbox_pid: int
    width: int | None = None
    height: int | None = None
    dpi: int | None = None
    adb_serial: str | None = None

    @property
    def running(self) -> bool:
        return self.pid > 0 or self.vbox_pid > 0 or self.android_started


def parse_list2(output: str) -> tuple[Instance, ...]:
    """Official list2: index,title,top_hwnd,bind_hwnd,android,pid,vbox_pid.

    Split numeric suffix from the right so commas inside instance titles survive.
    Unknown layouts fail closed instead of silently misidentifying an instance.
    """
    result = []
    seen = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            prefix, top, bind, android, pid, vbox = line.rsplit(",", 5)
            index, name = prefix.split(",", 1)
            index, top, bind, android, pid, vbox = map(int, (index, top, bind, android, pid, vbox))
            if index < 0 or index in seen or not name.strip() or android not in (0, 1):
                raise ValueError("index/name/state invalid")
            if top < 0 or bind < 0 or pid < -1 or vbox < -1:
                raise ValueError("invalid process values")
        except ValueError as exc:
            raise ValueError(f"Không đọc được list2 an toàn: {line!r}") from exc
        seen.add(index)
        result.append(Instance(index, name, bool(android), pid, vbox))
    return tuple(result)


@dataclass(frozen=True)
class Installation:
    console: Path
    adb: Path

    @property
    def namespace(self) -> str:
        return str(self.console.resolve()).casefold()


def inspect_folder(folder: Path) -> Installation | None:
    for name in ("ldconsole.exe", "dnconsole.exe"):
        console, adb = folder / name, folder / "adb.exe"
        if console.is_file() and adb.is_file():
            return Installation(console.resolve(), adb.resolve())
    return None


def discover(saved: str = "") -> Installation | None:
    if os.name != "nt":
        return None
    candidates = [Path(saved)] if saved else []
    for root in (
        Path("C:/LDPlayer"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "LDPlayer",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "LDPlayer",
    ):
        candidates.extend((root, root / "LDPlayer9", root / "LDPlayer4"))
    for binary in ("ldconsole.exe", "dnconsole.exe"):
        location = shutil.which(binary)
        if location:
            candidates.append(Path(location).parent)
    import winreg

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(
                    hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0, winreg.KEY_READ | view
                ) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, i)) as child:
                                name = str(winreg.QueryValueEx(child, "DisplayName")[0])
                                if "ldplayer" in name.casefold() or "雷电" in name:
                                    candidates.append(Path(winreg.QueryValueEx(child, "InstallLocation")[0]))
                        except OSError:
                            continue
            except OSError:
                continue
    for folder in candidates:
        found = inspect_folder(folder)
        if found:
            return found
    return None


class LDPlayer:
    def __init__(self, installation: Installation, process: Process):
        self.installation, self.process = installation, process

    def list_instances(self) -> tuple[Instance, ...]:
        return parse_list2(decode(self.process.run([str(self.installation.console), "list2"])))

    def _indexed(self, command: str, index: int, *args: str) -> bytes:
        if type(index) is not int or index < 0:
            raise ValueError("Index bắt buộc, không fallback.")
        return self.process.run([str(self.installation.console), command, "--index", str(index), *args])

    def boot_id(self, index: int) -> str:
        return decode(
            self._indexed("adb", index, "--command", "shell cat /proc/sys/kernel/random/boot_id")
        ).strip()

import os
import re
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
    """Parse legacy and current LDPlayer ``list2`` layouts.

    Split numeric suffix from the right so commas inside instance titles survive.
    Unknown layouts fail closed instead of silently misidentifying an instance.
    """
    result = []
    seen = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            fields = None
            for numeric_fields in (8, 5):
                prefix, *tail = line.rsplit(",", numeric_fields)
                try:
                    index, name = prefix.split(",", 1)
                    parsed = tuple(map(int, (index, *tail)))
                except ValueError:
                    continue
                fields = name, *parsed
                break
            if fields is None:
                raise ValueError("unrecognized list2 layout")
            name, index, top, bind, android, pid, vbox, *display = fields
            if index < 0 or index in seen or not name.strip() or android not in (0, 1, 2):
                raise ValueError("index/name/state invalid")
            if top < 0 or bind < 0 or pid < -1 or vbox < -1:
                raise ValueError("invalid process values")
            if display:
                width, height, dpi = display
                if width <= 0 or height <= 0 or dpi <= 0:
                    raise ValueError("invalid display values")
            else:
                width = height = dpi = None
        except ValueError as exc:
            raise ValueError(f"Không đọc được list2 an toàn: {line!r}") from exc
        seen.add(index)
        # State 2 is emitted by LDPlayer 9 while Android is still booting.  It
        # proves the instance is running through its PID, but is not ADB-ready.
        result.append(Instance(index, name, android == 1, pid, vbox, width, height, dpi))
    return tuple(result)


def parse_indexed_adb_serial(output: str) -> str:
    """Parse only the serial explicitly named by LDPlayer's indexed ADB command."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) == 1 and re.fullmatch(r"[A-Za-z0-9._:\-]+", lines[0]):
        return lines[0]
    if len(lines) == 1:
        match = re.fullmatch(r"(?:adb\.exe: |error: )?device '([A-Za-z0-9._:\-]+)' not found", lines[0])
        if match:
            return match.group(1)
    raise ValueError("LDPlayer không cung cấp đúng một ADB serial cho instance được chỉ định.")


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


def display_icon_folder(value: str) -> Path | None:
    """Return an executable's folder from an Uninstall ``DisplayIcon`` value.

    The registry value can quote a path with spaces, follow it with an icon
    index (`,0`), or append executable arguments.  Only accept an executable
    path; ``inspect_folder`` subsequently verifies its LDPlayer peers.
    """
    text = value.strip()
    if not text:
        return None
    if text.startswith('"'):
        closing_quote = text.find('"', 1)
        if closing_quote <= 1:
            return None
        executable = text[1:closing_quote]
    else:
        executable = text.split(",", 1)[0].strip()
        suffix = executable.casefold().find(".exe")
        if suffix >= 0:
            executable = executable[: suffix + 4]
    path = Path(executable)
    return path.parent if path.suffix.casefold() == ".exe" else None


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
                                    try:
                                        location = str(winreg.QueryValueEx(child, "InstallLocation")[0]).strip()
                                    except OSError:
                                        location = ""
                                    if location:
                                        candidates.append(Path(location))
                                    else:
                                        # LDPlayer 9 commonly leaves InstallLocation blank but
                                        # registers its executable in DisplayIcon.  Use its parent
                                        # folder rather than failing discovery or guessing a drive.
                                        try:
                                            icon = str(winreg.QueryValueEx(child, "DisplayIcon")[0])
                                            folder = display_icon_folder(icon)
                                            if folder:
                                                candidates.append(folder)
                                        except OSError:
                                            continue
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

    def adb_serial(self, index: int) -> str:
        return parse_indexed_adb_serial(
            decode(self._indexed("adb", index, "--command", "get-serialno"))
        )

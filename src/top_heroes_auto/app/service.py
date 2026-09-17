"""Only this execution layer may dispatch UI-requested device actions."""

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.adb.client import ADB, Target, valid_boot_id, validate_package, validate_serial
from top_heroes_auto.app.process import decode
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError, create_snapshot, require_selected
from top_heroes_auto.ldplayer.client import Instance, LDPlayer
from top_heroes_auto.storage.store import Store

log = logging.getLogger("top_heroes_auto")


class Manager:
    START_TIMEOUT = 120.0
    STOP_TIMEOUT = 60.0
    POLL_INTERVAL = 1.0
    ADB_RESOLVE_TIMEOUT = 30.0

    def __init__(self, ld: LDPlayer, store: Store, data_dir: Path):
        self.ld, self.store, self.data_dir = ld, store, data_dir
        self.adb = ADB(str(ld.installation.adb), ld.process)
        self.namespace = ld.installation.namespace
        self._lock = threading.RLock()
        self._active: RunSnapshot | None = None

    def refresh(self):
        with self._lock:
            instances = self.ld.list_instances()
            self.store.merge(self.namespace, instances)
            log.info("Đọc danh sách LDPlayer: %s giả lập (chỉ đọc).", len(instances))
            return instances

    def list_readonly(self):
        """Read the live Multi list without changing persisted instance metadata."""
        with self._lock:
            return self.ld.list_instances()

    def select(self, index: int, selected: bool):
        with self._lock:
            self.store.select(self.namespace, index, selected)

    def protect(self, index: int, protected: bool):
        with self._lock:
            self.store.protect(self.namespace, index, protected)

    def query(self, index: int) -> Instance:
        """Read-only lifecycle query; even protected instances may be listed."""
        if type(index) is not int or index < 0:
            raise SafetyError("Index không hợp lệ; không fallback về index 0.")
        matches = [instance for instance in self.refresh() if instance.index == index]
        if len(matches) != 1:
            raise SafetyError("Không tìm thấy đúng giả lập được chỉ định.")
        return matches[0]

    def _wait_state(self, index: int, *, started: bool):
        timeout = self.START_TIMEOUT if started else self.STOP_TIMEOUT
        deadline = time.monotonic() + timeout
        while True:
            instance = self._check(index)
            ready = instance.running and instance.android_started if started else not instance.running
            if ready:
                return instance
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                state = "Android khởi động" if started else "giả lập dừng"
                raise SafetyError(f"[#{index}] Hết thời gian chờ {state}; hủy riêng thao tác này.")
            time.sleep(min(self.POLL_INTERVAL, remaining))

    def _stop(self, index: int):
        instance = self._check(index)
        if instance.running:
            log.info("[%s / #%s] Dừng đúng instance bằng index", instance.name, index)
            self.ld._indexed("quit", index)
        self._wait_state(index, started=False)

    def _start(self, index: int):
        instance = self._check(index)
        if not instance.running:
            log.info("[%s / #%s] Khởi động đúng instance bằng index (chưa cần ADB)", instance.name, index)
            self.ld._indexed("launch", index)
        log.info("[%s / #%s] Chờ Android sẵn sàng", instance.name, index)
        self._wait_state(index, started=True)

    def _check(self, index: int):
        if self._active is None or self._active.namespace != self.namespace:
            raise SafetyError("Không có hàng đợi thao tác đang hoạt động.")
        current = self.ld.list_instances()
        self.store.merge(self.namespace, current)
        return require_selected(self.store, self._active, current, index)

    def _resolve(self, index: int) -> Target:
        instance = self._check(index)
        if not instance.android_started:
            raise SafetyError("Android chưa sẵn sàng; không thể xác minh ADB.")
        deadline = time.monotonic() + self.ADB_RESOLVE_TIMEOUT
        while True:
            self._check(index)
            # This serial comes from LDPlayer's documented --index mechanism,
            # never from a port formula or the first global adb device.
            try:
                serial = validate_serial(self.ld.adb_serial(index))
            except ValueError as exc:
                raise SafetyError(
                    "LDPlayer không cung cấp đúng một ADB serial cho instance được chỉ định."
                ) from exc
            devices = self.adb.devices()
            if devices.get(serial) == "device":
                expected = valid_boot_id(self.ld.boot_id(index))
                self._check(index)
                if self.adb.boot_id(serial) != expected:
                    raise SafetyError("ADB target không khớp Android boot ID của LDPlayer index.")
                self._check(index)
                if valid_boot_id(self.ld.boot_id(index)) != expected:
                    raise SafetyError("Android đã khởi động lại trong lúc xác minh.")
                log.info("[%s / #%s] Đã xác minh ADB %s", instance.name, index, serial)
                return Target(index, instance.name, serial, expected)
            if time.monotonic() >= deadline:
                raise SafetyError(
                    f"LDPlayer xác định ADB {serial} cho #{index}, nhưng target không sẵn sàng; "
                    "kiểm tra ADB debugging của đúng instance."
                )
            time.sleep(self.POLL_INTERVAL)

    def execute(self, index: int, action: str, package: str = "", values: tuple = ()):
        """One explicit manual action = one short-lived immutable queue.

        Selection edits use the same lock. Revocation before dispatch is checked again.
        No background automation queue or concurrency runner exists in Phase 1.
        """
        allowed = {
            "verify",
            "launch",
            "quit",
            "reboot",
            "packages",
            "third_party_packages",
            "package_badging",
            "launcher_activity",
            "open_game",
            "close_game",
            "screenshot",
            "tap",
            "swipe",
            "keyevent",
            "harmless",
        }
        if action not in allowed:
            raise SafetyError("Thao tác không được hỗ trợ.")
        with self._lock:
            current = self.refresh()
            snapshot = create_snapshot(self.store, self.namespace, current)
            # Restrict membership to the exact UI target, not every selected instance.
            self._active = RunSnapshot(self.namespace, tuple(m for m in snapshot.members if m[0] == index))
            try:
                instance = self._check(index)
                # Lifecycle dispatch targets the verified LDPlayer index. A stopped
                # Android cannot supply ADB identity, so never resolve before launch.
                if action == "quit":
                    self._stop(index)
                    return f"[{instance.name} / #{index}] Giả lập đã dừng."
                if action == "reboot":
                    # Explicit stop -> observed stopped -> start; never reuse a
                    # pre-restart Target or call the opaque CLI reboot command.
                    self._stop(index)
                if action in {"launch", "reboot"}:
                    self._start(index)
                target = self._resolve(index)
                self._check(index)
                # Revalidate explicit transport immediately before sending the action.
                if self.adb.boot_id(target.serial) != target.boot_id:
                    raise SafetyError("ADB target đã thay đổi; hủy thao tác.")
                self._check(index)
                log.info("[%s / #%s] Thao tác: %s", instance.name, index, action)
                if action == "verify":
                    return f"Đã xác minh ADB: {target.serial}"
                if action == "harmless":
                    return self.adb._shell(target.serial, "echo", "phase1-diagnostic")
                if action in {"launch", "reboot"}:
                    return f"[{instance.name} / #{index}] Android sẵn sàng; đã xác minh ADB: {target.serial}"
                if action == "packages":
                    return self.adb._shell(target.serial, "pm", "list", "packages")
                if action == "third_party_packages":
                    return self.adb._shell(target.serial, "pm", "list", "packages", "-3")
                if action == "package_badging":
                    package = validate_package(package)
                    paths = [
                        line.removeprefix("package:").strip()
                        for line in self.adb._shell(target.serial, "pm", "path", package).splitlines()
                        if line.startswith("package:") and line.strip().endswith("/base.apk")
                    ]
                    if len(paths) != 1:
                        raise SafetyError("Không xác định được đúng một base APK của ứng dụng.")
                    aapt = self.ld.installation.console.parent / "aapt.exe"
                    if not aapt.is_file():
                        raise SafetyError("LDPlayer không cung cấp aapt.exe để xác minh app label.")
                    folder = self.data_dir / "diagnostics" / "apk-metadata"
                    folder.mkdir(parents=True, exist_ok=True)
                    local = folder / f"instance-{index}-{package}.apk"
                    try:
                        local.write_bytes(self.adb._read_apk(target.serial, paths[0]))
                        return decode(self.ld.process.run([str(aapt), "dump", "badging", str(local)]))
                    finally:
                        local.unlink(missing_ok=True)
                if action == "launcher_activity":
                    package = validate_package(package)
                    return self.adb._shell(
                        target.serial,
                        "cmd",
                        "package",
                        "resolve-activity",
                        "--brief",
                        "-a",
                        "android.intent.action.MAIN",
                        "-c",
                        "android.intent.category.LAUNCHER",
                        package,
                    )
                if action in {"open_game", "close_game"}:
                    package = validate_package(package)
                    if action == "open_game":
                        return self.adb._shell(
                            target.serial,
                            "monkey",
                            "-p",
                            package,
                            "-c",
                            "android.intent.category.LAUNCHER",
                            "1",
                        )
                    return (
                        self.adb._shell(target.serial, "am", "force-stop", package)
                        or "Đã gửi lệnh đóng game."
                    )
                if action == "screenshot":
                    data = self.adb._capture(target.serial)
                    folder = self.data_dir / "screenshots"
                    folder.mkdir(parents=True, exist_ok=True)
                    path = folder / f"instance-{index}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S-%f}Z.png"
                    path.write_bytes(data)
                    return path
                if action in {"tap", "swipe", "keyevent"}:
                    count = {"tap": 2, "swipe": 5, "keyevent": 1}[action]
                    if len(values) != count or any(type(v) is not int or v < 0 for v in values):
                        raise SafetyError("Tham số input không hợp lệ.")
                    return self.adb._shell(target.serial, "input", action, *(str(v) for v in values))
            except Exception:
                log.exception("[#%s] Hủy thao tác %s", index, action)
                raise
            finally:
                self._active = None

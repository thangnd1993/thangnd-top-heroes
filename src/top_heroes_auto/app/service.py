"""Only this execution layer may dispatch UI-requested device actions."""

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.adb.client import ADB, Target, valid_boot_id, validate_package, validate_serial
from top_heroes_auto.app.process import CommandError, decode
from top_heroes_auto.automation.guard import (
    RunSnapshot,
    SafetyError,
    create_snapshot,
    require_run_member,
    require_selected,
)
from top_heroes_auto.ldplayer.client import Instance, LDPlayer
from top_heroes_auto.storage.store import Store

log = logging.getLogger("top_heroes_auto")


LIFECYCLE_NOT_ATTEMPTED = "NOT_ATTEMPTED"
LIFECYCLE_EXTERNAL = "EXTERNAL"
LIFECYCLE_OWNED = "OWNED"
LIFECYCLE_UNKNOWN = "UNKNOWN"


class TransportResolutionError(SafetyError):
    """ADB transport availability failed without an account identity failure."""


@dataclass
class LifecycleDispatch:
    action: str
    attempted: bool = False
    completed: bool = False
    outcome: str = LIFECYCLE_NOT_ATTEMPTED
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "attempted": self.attempted,
            "completed": self.completed,
            "outcome": self.outcome,
            "error": self.error,
        }


@dataclass
class LifecycleAttempt:
    index: int
    action: str
    target_name: str | None = None
    pre_running: bool | None = None
    ownership: str = LIFECYCLE_NOT_ATTEMPTED
    failure_stage: str | None = None
    error: str | None = None
    dispatches: list[LifecycleDispatch] = field(default_factory=list)

    @property
    def dispatch_attempted(self) -> bool:
        return any(item.attempted for item in self.dispatches)

    @property
    def ownership_uncertain(self) -> bool:
        return self.ownership == LIFECYCLE_UNKNOWN

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "action": self.action,
            "target_name": self.target_name,
            "pre_running": self.pre_running,
            "ownership": self.ownership,
            "ownership_uncertain": self.ownership_uncertain,
            "dispatch_attempted": self.dispatch_attempted,
            "dispatches": [item.as_dict() for item in self.dispatches],
            "failure_stage": self.failure_stage,
            "error": self.error,
        }


class Manager:
    START_TIMEOUT = 120.0
    STOP_TIMEOUT = 60.0
    POLL_INTERVAL = 1.0
    ADB_RESOLVE_TIMEOUT = 30.0

    @staticmethod
    def _local_endpoint(serial: str) -> str | None:
        """Map only LDPlayer's reported emulator serial to its adjacent ADB TCP port.

        The endpoint is still untrusted until its Android boot ID matches the
        instance-scoped LDPlayer channel.
        """
        match = re.fullmatch(r"emulator-([0-9]{4,5})", serial)
        if not match:
            return None
        port = int(match.group(1)) + 1
        return f"127.0.0.1:{port}" if port <= 65535 else None

    def __init__(self, ld: LDPlayer, store: Store, data_dir: Path):
        self.ld, self.store, self.data_dir = ld, store, data_dir
        self.adb = ADB(str(ld.installation.adb), ld.process)
        self.namespace = ld.installation.namespace
        self._lock = threading.RLock()
        self._active: RunSnapshot | None = None
        self._last_lifecycle_attempt: LifecycleAttempt | None = None

    @property
    def last_lifecycle_attempt(self) -> LifecycleAttempt | None:
        """Return the latest indexed launch/reboot attempt for reporting.

        The object is updated only while the Manager lock is held. Callers use
        its serialized snapshot immediately after an exception or successful
        lifecycle operation; non-lifecycle actions intentionally do not erase
        it so recovery can persist the launch outcome before cleanup.
        """

        return self._last_lifecycle_attempt

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
        attempt = self._last_lifecycle_attempt
        if attempt is not None:
            if attempt.target_name is None:
                attempt.target_name = instance.name
            if attempt.pre_running is None:
                attempt.pre_running = instance.running
        if not instance.running:
            # Start the bundled daemon before Android boots so LDPlayer can
            # register its indexed emulator transport. This is idempotent and
            # never kills/restarts a shared ADB server.
            dispatch = LifecycleDispatch("launch")
            if attempt is not None:
                attempt.dispatches.append(dispatch)
                attempt.failure_stage = "pre_dispatch"
            try:
                self.adb.start_server()
                log.info("[%s / #%s] Khởi động đúng instance bằng index (chưa cần ADB)", instance.name, index)
                # Mark immediately before the indexed command. If the process
                # raises after writing to LDPlayer, ownership is UNKNOWN and
                # callers must never infer a safe quit from the state delta.
                dispatch.attempted = True
                dispatch.outcome = LIFECYCLE_UNKNOWN
                if attempt is not None:
                    attempt.ownership = LIFECYCLE_UNKNOWN
                    attempt.failure_stage = "indexed_dispatch"
                self.ld._indexed("launch", index)
            except Exception as exc:
                dispatch.error = str(exc)
                if attempt is not None:
                    attempt.error = str(exc)
                raise
            dispatch.completed = True
            dispatch.outcome = "DISPATCHED"
            if attempt is not None:
                attempt.failure_stage = "post_dispatch_wait"
        log.info("[%s / #%s] Chờ Android sẵn sàng", instance.name, index)
        try:
            started = self._wait_state(index, started=True)
        except Exception as exc:
            if attempt is not None:
                attempt.error = str(exc)
                if attempt.dispatch_attempted:
                    attempt.ownership = LIFECYCLE_UNKNOWN
                    attempt.failure_stage = "post_dispatch_wait"
            raise
        return started

    def _check(self, index: int):
        if self._active is None or self._active.namespace != self.namespace:
            raise SafetyError("Không có hàng đợi thao tác đang hoạt động.")
        current = self.ld.list_instances()
        self.store.merge(self.namespace, current)
        if self._active.immutable:
            return require_run_member(self.store, self._active, current, index)
        return require_selected(self.store, self._active, current, index)

    def _resolve(self, index: int) -> Target:
        instance = self._check(index)
        if not instance.android_started:
            raise SafetyError("Android chưa sẵn sàng; không thể xác minh ADB.")
        self.adb.start_server()
        deadline = time.monotonic() + self.ADB_RESOLVE_TIMEOUT
        recovered_server = False
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
            try:
                # Strategy B is authoritative identity, even when global
                # enumeration has not registered the transport yet.
                expected = valid_boot_id(self.ld.adb_command(
                    index, "shell cat /proc/sys/kernel/random/boot_id"
                ))
            except (CommandError, SafetyError, ValueError):
                expected = None
            candidates = [serial]
            endpoint = self._local_endpoint(serial)
            if endpoint and expected and devices.get(serial) != "device":
                # Strategy C: connect only the endpoint implied by the serial
                # LDPlayer itself reported. Acceptance still requires boot-ID
                # equality with the indexed channel.
                try:
                    before_connect = set(devices)
                    self.adb.connect(endpoint)
                    devices = self.adb.devices()
                    unexpected = set(devices) - before_connect - {endpoint}
                    if unexpected:
                        raise SafetyError("ADB connect trả về target mới không rõ nguồn gốc.")
                    candidates.append(endpoint)
                except SafetyError:
                    raise
                except CommandError:
                    pass
            target_serial = next((item for item in candidates if devices.get(item) == "device"), None)
            if target_serial and expected:
                self._check(index)
                if self.adb.boot_id(target_serial) != expected:
                    raise SafetyError("ADB target không khớp Android boot ID của LDPlayer index.")
                self._check(index)
                if (
                    valid_boot_id(
                        self.ld.adb_command(index, "shell cat /proc/sys/kernel/random/boot_id")
                    )
                    != expected
                ):
                    raise SafetyError("Android đã khởi động lại trong lúc xác minh.")
                log.info("[%s / #%s] Đã xác minh ADB %s", instance.name, index, target_serial)
                return Target(index, instance.name, target_serial, expected)
            if time.monotonic() >= deadline:
                # Shared-daemon recovery is allowed once, and only when no
                # other Android device is present and no other LDPlayer is
                # running. It is never the normal first strategy.
                others_running = any(
                    item.index != index and item.running for item in self.ld.list_instances()
                )
                if not recovered_server and not devices and not others_running:
                    recovered_server = True
                    self.adb.restart_server()
                    deadline = time.monotonic() + self.ADB_RESOLVE_TIMEOUT
                    continue
                raise TransportResolutionError(
                    f"LDPlayer xác định ADB {serial} cho #{index}, nhưng target không sẵn sàng; "
                    "kiểm tra ADB debugging của đúng instance."
                )
            time.sleep(self.POLL_INTERVAL)

    def capture_verified(self, index: int, snapshot: RunSnapshot | None = None) -> tuple[Target, bytes]:
        """Capture exactly one PNG through a freshly verified explicit target."""
        with self._lock:
            current = self.refresh()
            immutable_snapshot = snapshot is not None
            snapshot = snapshot or create_snapshot(self.store, self.namespace, current)
            self._active = RunSnapshot(
                self.namespace,
                tuple(member for member in snapshot.members if member[0] == index),
                immutable_snapshot,
            )
            try:
                target = self._resolve(index)
                self._check(index)
                if self.adb.boot_id(target.serial) != target.boot_id:
                    raise SafetyError("ADB target đã thay đổi; hủy chụp màn hình.")
                self._check(index)
                return target, self.adb._capture(target.serial)
            except Exception:
                log.exception("[#%s] Hủy capture đã xác minh", index)
                raise
            finally:
                self._active = None

    def execute(
        self, index: int, action: str, package: str = "", values: tuple = (), snapshot: RunSnapshot | None = None,
        *, observed_target: Target | None = None,
    ):
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
        if observed_target is not None and action not in {"tap", "swipe", "keyevent"}:
            raise SafetyError("Screenshot-bound identity is only valid for evidence-guarded input.")
        with self._lock:
            if action in {"launch", "reboot"}:
                self._last_lifecycle_attempt = LifecycleAttempt(index=index, action=action)
            current = self.refresh()
            immutable_snapshot = snapshot is not None
            snapshot = snapshot or create_snapshot(self.store, self.namespace, current)
            # Restrict membership to the exact UI target, not every selected instance.
            self._active = RunSnapshot(
                self.namespace,
                tuple(m for m in snapshot.members if m[0] == index),
                immutable_snapshot,
            )
            try:
                instance = self._check(index)
                attempt = self._last_lifecycle_attempt
                if attempt is not None and attempt.action == action:
                    attempt.target_name = instance.name
                    attempt.pre_running = instance.running
                    if action == "launch" and instance.running:
                        # A running target existed before this invocation. A
                        # later transport/identity failure must not turn it
                        # into an owned launch or authorize cleanup.
                        attempt.ownership = LIFECYCLE_EXTERNAL
                        attempt.failure_stage = None
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
                try:
                    target = self._resolve(index)
                except TransportResolutionError:
                    if action not in {"launch", "reboot"}:
                        raise
                    # A manual launch on an already-running external instance
                    # must not stop/relaunch it merely because ADB is late.
                    attempt = self._last_lifecycle_attempt
                    if action == "launch" and attempt is not None and attempt.pre_running:
                        raise
                    # LDPlayer occasionally reaches Android-ready without
                    # creating its per-instance NAT/ADB listener. Retry one
                    # exact-target lifecycle only; never restart shared ADB.
                    log.warning("[#%s] ADB chưa đăng ký; thử lại đúng instance một lần", index)
                    self._stop(index)
                    self._start(index)
                    try:
                        target = self._resolve(index)
                    except TransportResolutionError:
                        attempt = self._last_lifecycle_attempt
                        if attempt is not None and attempt.dispatch_attempted:
                            attempt.ownership = LIFECYCLE_UNKNOWN
                            attempt.failure_stage = "resolve_transport_retry"
                            attempt.error = "ADB transport remained unavailable after scoped retry"
                        # Preserve the existing bounded transport cleanup, but
                        # do not treat identity/selection failures as transport
                        # failures below.
                        self._stop(index)
                        raise
                    except Exception as exc:
                        attempt = self._last_lifecycle_attempt
                        if attempt is not None and attempt.dispatch_attempted:
                            attempt.ownership = LIFECYCLE_UNKNOWN
                            attempt.failure_stage = "resolve_retry"
                            attempt.error = str(exc)
                        # The indexed launch may have reached an unknown
                        # identity. Never issue an index-only quit after a
                        # boot/name/selection or other non-transport failure.
                        raise
                self._check(index)
                # Revalidate explicit transport immediately before sending the action.
                if self.adb.boot_id(target.serial) != target.boot_id:
                    raise SafetyError("ADB target đã thay đổi; hủy thao tác.")
                self._check(index)
                if observed_target is not None:
                    if target != observed_target:
                        raise SafetyError("Current ADB identity differs from the action's screenshot.")
                    # Visual actions must respect a live selection revocation,
                    # even when a queue snapshot captured earlier membership.
                    require_selected(self.store, self._active, self.ld.list_instances(), index)
                if action in {"launch", "reboot"}:
                    attempt = self._last_lifecycle_attempt
                    if attempt is not None and attempt.dispatch_attempted:
                        # Ownership is confirmed only after the indexed start,
                        # current selection, and explicit ADB boot identity all
                        # pass. A later identity failure must remain UNKNOWN so
                        # recovery cannot issue an index-only quit.
                        attempt.ownership = LIFECYCLE_OWNED
                        attempt.failure_stage = None
                        attempt.error = None
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

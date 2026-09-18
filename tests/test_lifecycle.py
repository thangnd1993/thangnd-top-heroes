"""Lifecycle regression tests use a real Manager and a simulated CLI/ADB boundary."""

import pytest

from top_heroes_auto.automation.guard import SafetyError

STOPPED = "0,Main-Thang,1,2,1,101,102\n7,Farm-007,0,0,0,-1,-1\n"
RUNNING = "0,Main-Thang,1,2,1,101,102\n7,Farm-007,3,4,1,201,202\n"
NEW_BOOT = "bb068632-fc3e-4090-a8d7-ae8d9fe353f5"
ONLY_TARGET_RUNNING = "7,Farm-007,3,4,1,201,202\n"


def assert_only_target_seven(calls):
    for call in calls:
        assert "quitall" not in call and "reboot" not in call and "kill-server" not in call
        if "--index" in call:
            assert call[call.index("--index") + 1] == "7"
        if call[0].endswith("adb.exe") and call[1] not in ("devices", "start-server"):
            if call[1] == "connect":
                assert call[2] == "127.0.0.1:5569"
            else:
                assert call[1] == "-s" and call[2]


def test_stopped_launch_needs_no_existing_adb_and_resolves_after_launch(rig):
    manager, process, _ = rig
    process.listing = STOPPED
    process.serial = ""
    process.devices_output = "List of devices attached\n"
    launched = False

    def hook(args):
        nonlocal launched
        if args[1] == "launch":
            launched = True
            process.serial = "emulator-5568"
            process.devices_output = "List of devices attached\nemulator-5568\tdevice\n"
        if args[1] in ("adb", "devices", "-s"):
            assert launched, "No ADB command is allowed before launch"

    process.hook = hook
    assert "emulator-5568" in manager.execute(7, "launch")
    commands = [call[1] for call in process.calls if call[1] != "list2"]
    assert commands[:2] == ["start-server", "launch"]
    assert_only_target_seven(process.calls)
    assert manager._active is None


def test_waits_for_android_before_resolving(rig, monkeypatch):
    manager, process, _ = rig
    process.listing = STOPPED
    process.auto_lifecycle = False
    polls = 0
    launched = False
    monkeypatch.setattr("top_heroes_auto.app.service.time.sleep", lambda _: None)

    def hook(args):
        nonlocal polls, launched
        if args[1] == "launch":
            launched = True
            process.listing = RUNNING.replace(",1,201,202", ",0,201,202")
        if args[1] == "list2" and launched:
            polls += 1
            if polls == 3:
                process.listing = RUNNING
        if args[1] in ("adb", "devices", "-s"):
            assert polls >= 3

    process.hook = hook
    manager.execute(7, "launch")
    assert polls >= 3


def test_restart_discards_previous_target_and_resolves_new_serial_and_boot(rig):
    manager, process, _ = rig
    assert "emulator-5568" in manager.execute(7, "verify")
    process.calls.clear()

    def hook(args):
        if args[1] == "quit":
            process.serial = ""
            process.devices_output = "List of devices attached\n"
        if args[1] == "launch":
            process.serial = "127.0.0.1:6123"
            process.device_boot = process.cli_boot = NEW_BOOT
            process.devices_output = "List of devices attached\n127.0.0.1:6123\tdevice\n"

    process.hook = hook
    assert "127.0.0.1:6123" in manager.execute(7, "reboot")
    commands = [call[1] for call in process.calls if call[1] != "list2"]
    assert commands[:3] == ["quit", "start-server", "launch"]
    assert all("emulator-5568" not in call for call in process.calls)
    assert any(call[-1] == "get-serialno" for call in process.calls)
    assert_only_target_seven(process.calls)


def test_restart_waits_for_stop_before_launch(rig, monkeypatch):
    manager, process, _ = rig
    process.auto_lifecycle = False
    quitting = False
    polls = 0
    monkeypatch.setattr("top_heroes_auto.app.service.time.sleep", lambda _: None)

    def hook(args):
        nonlocal quitting, polls
        if args[1] == "quit":
            quitting = True
        if args[1] == "list2" and quitting:
            polls += 1
            if polls == 3:
                process.listing = STOPPED
        if args[1] == "launch":
            assert polls >= 3 and process.listing == STOPPED
            quitting = False
            process.listing = RUNNING

    process.hook = hook
    manager.execute(7, "reboot")
    assert_only_target_seven(process.calls)


def test_failed_resolution_is_local_no_cleanup_of_other_instances(rig):
    manager, process, store = rig
    process.listing = STOPPED
    process.devices_output = "List of devices attached\n"
    manager.ADB_RESOLVE_TIMEOUT = 0
    with pytest.raises(SafetyError, match="ADB"):
        manager.execute(7, "launch")
    assert manager._active is None
    assert_only_target_seven(process.calls)
    assert not any(call[1] == "reboot" for call in process.calls)
    assert sum(call[1] == "quit" for call in process.calls) == 2
    assert not manager.query(7).running
    assert process.listing.splitlines()[0] == STOPPED.splitlines()[0]
    assert store.metadata(manager.namespace, 0).protected
    # Failure does not poison the manager; an explicit retry can start and verify it.
    process.devices_output = "List of devices attached\nemulator-5568\tdevice\n"
    assert "emulator-5568" in manager.execute(7, "launch")


def test_launch_recovers_once_when_first_boot_has_no_adb_listener(rig):
    manager, process, _ = rig
    manager.ADB_RESOLVE_TIMEOUT = 0
    process.listing = STOPPED
    process.devices_output = "List of devices attached\n"
    launches = 0

    def hook(args):
        nonlocal launches
        if args[1] == "launch":
            launches += 1
            if launches == 2:
                process.devices_output = "List of devices attached\nemulator-5568\tdevice\n"

    process.hook = hook
    assert "emulator-5568" in manager.execute(7, "launch")
    assert launches == 2
    assert sum(call[1] == "quit" for call in process.calls) == 1
    assert_only_target_seven(process.calls)


def test_resolver_never_falls_back_to_first_or_multiple_adb_devices(rig):
    manager, process, _ = rig
    manager.ADB_RESOLVE_TIMEOUT = 0
    process.serial = "emulator-5568"
    process.devices_output = "List of devices attached\nemulator-5554\tdevice\n127.0.0.1:6123\tdevice\n"
    with pytest.raises(SafetyError, match="emulator-5568"):
        manager.execute(7, "verify")
    forbidden = (["-s", "emulator-5554"], ["-s", "127.0.0.1:6123"])
    assert not any(call[1:3] in forbidden for call in process.calls)


def test_resolver_rejects_candidate_with_unmatched_boot_identity(rig):
    manager, process, _ = rig
    process.device_boot = NEW_BOOT
    with pytest.raises(SafetyError, match="không khớp"):
        manager.execute(7, "verify")


def test_resolver_connects_verified_endpoint_when_global_serial_is_missing(rig):
    manager, process, _ = rig
    process.listing = ONLY_TARGET_RUNNING
    process.devices_output = "List of devices attached\n"

    def hook(args):
        if args[1] == "connect":
            assert args[2] == "127.0.0.1:5569"
            process.devices_output = "List of devices attached\n127.0.0.1:5569\tdevice\n"

    process.hook = hook
    result = manager.execute(7, "verify")
    assert "127.0.0.1:5569" in result
    assert any(call[1:] == ["connect", "127.0.0.1:5569"] for call in process.calls)


def test_connected_endpoint_boot_mismatch_is_rejected(rig):
    manager, process, _ = rig
    process.listing = ONLY_TARGET_RUNNING
    process.devices_output = "List of devices attached\n"
    process.device_boot = NEW_BOOT

    def hook(args):
        if args[1] == "connect":
            process.devices_output = "List of devices attached\n127.0.0.1:5569\tdevice\n"

    process.hook = hook
    with pytest.raises(SafetyError, match="không khớp"):
        manager.execute(7, "verify")


def test_connect_rejects_multiple_new_targets(rig):
    manager, process, _ = rig
    process.listing = ONLY_TARGET_RUNNING
    process.devices_output = "List of devices attached\n"

    def hook(args):
        if args[1] == "connect":
            process.devices_output = (
                "List of devices attached\n"
                "127.0.0.1:5569\tdevice\n"
                "emulator-9998\tdevice\n"
            )

    process.hook = hook
    with pytest.raises(SafetyError, match="không rõ nguồn gốc"):
        manager.execute(7, "verify")


def test_shared_adb_restart_requires_no_devices_and_no_other_running_instance(rig):
    manager, process, _ = rig
    manager.ADB_RESOLVE_TIMEOUT = 0
    process.devices_output = "List of devices attached\n"
    with pytest.raises(SafetyError):
        manager.execute(7, "verify")
    assert not any(call[1] == "kill-server" for call in process.calls)


def test_shared_adb_restart_allowed_once_under_safe_preconditions(rig):
    manager, process, _ = rig
    manager.ADB_RESOLVE_TIMEOUT = 0
    process.listing = ONLY_TARGET_RUNNING
    process.devices_output = "List of devices attached\n"
    kills = 0

    def hook(args):
        nonlocal kills
        if args[1] == "kill-server":
            kills += 1
        if args[1] == "start-server" and kills:
            process.devices_output = "List of devices attached\nemulator-5568\tdevice\n"

    process.hook = hook
    assert "emulator-5568" in manager.execute(7, "verify")
    assert kills == 1


@pytest.mark.parametrize("action", ["launch", "reboot"])
@pytest.mark.parametrize("guard", ["protected", "unchecked"])
def test_stopped_lifecycle_still_requires_whitelist(rig, action, guard):
    manager, process, _ = rig
    process.listing = STOPPED
    if guard == "protected":
        manager.protect(7, True)
    else:
        manager.select(7, False)
    with pytest.raises(SafetyError):
        manager.execute(7, action)
    assert all(call[1] == "list2" for call in process.calls)


@pytest.mark.parametrize("index", [None, False, -1, "7", 88])
def test_launch_never_falls_back_to_zero(rig, index):
    manager, process, _ = rig
    with pytest.raises(SafetyError):
        manager.execute(index, "launch")
    assert all(call[1] == "list2" for call in process.calls)


@pytest.mark.parametrize("action", ["launch", "reboot"])
def test_start_timeout_never_resolves_adb_or_sends_game_commands(rig, monkeypatch, action):
    manager, process, _ = rig
    process.listing = STOPPED
    process.auto_lifecycle = False
    monkeypatch.setattr(manager, "START_TIMEOUT", 0)
    with pytest.raises(SafetyError, match="Hết thời gian"):
        manager.execute(7, action)
    assert all(call[1] in ("list2", "start-server", "launch") for call in process.calls)
    assert manager._active is None


def test_stop_timeout_prevents_restart_launch(rig, monkeypatch):
    manager, process, _ = rig
    process.auto_lifecycle = False
    monkeypatch.setattr(manager, "STOP_TIMEOUT", 0)
    with pytest.raises(SafetyError, match="Hết thời gian"):
        manager.execute(7, "reboot")
    assert all(call[1] in ("list2", "quit") for call in process.calls)


@pytest.mark.parametrize("change", ["protect", "unselect", "rename", "remove"])
def test_identity_or_permission_change_between_stop_start_blocks_launch(rig, change):
    manager, process, store = rig
    process.auto_lifecycle = False

    def hook(args):
        if args[1] == "quit":
            process.listing = STOPPED
            if change == "protect":
                store.protect(manager.namespace, 7, True)
            elif change == "unselect":
                store.select(manager.namespace, 7, False)
            elif change == "rename":
                process.listing = STOPPED.replace("Farm-007", "Replacement")
            else:
                process.listing = STOPPED.splitlines()[0]

    process.hook = hook
    with pytest.raises(SafetyError):
        manager.execute(7, "reboot")
    assert all(call[1] in ("list2", "quit") for call in process.calls)


def test_stop_and_query_do_not_need_adb(rig):
    manager, process, _ = rig
    process.serial = ""
    process.devices_output = ""
    manager.execute(7, "quit")
    assert not manager.query(7).running
    assert manager.query(0).name == "Main-Thang"  # Read-only query is allowed.
    assert all(call[1] in ("list2", "quit") for call in process.calls)


@pytest.mark.parametrize(
    "action", ["screenshot", "tap", "swipe", "keyevent", "packages", "open_game", "close_game"]
)
def test_adb_operations_on_stopped_instance_never_autolaunch(rig, action):
    manager, process, _ = rig
    process.listing = STOPPED
    with pytest.raises(SafetyError, match="Android"):
        manager.execute(7, action, "com.example.game")
    assert all(call[1] == "list2" for call in process.calls)

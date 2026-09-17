import subprocess
from pathlib import Path

import pytest

from top_heroes_auto.adb.client import valid_boot_id, validate_package
from top_heroes_auto.app.process import CommandError, Process
from top_heroes_auto.automation.guard import SafetyError, create_snapshot, require_selected
from top_heroes_auto.ldplayer.client import (
    Instance,
    display_icon_folder,
    inspect_folder,
    parse_indexed_adb_serial,
    parse_list2,
)
from top_heroes_auto.storage.store import Store


def test_list2_real_layout_names_and_state():
    rows = parse_list2("0,Main Thắng ★,0,0,0,-1,-1\r\n7,Farm, số 7 & test,42,56,1,123,456\n")
    assert rows[0].name == "Main Thắng ★"
    assert not rows[0].running
    assert rows[1].name == "Farm, số 7 & test"
    assert rows[1].running and rows[1].android_started
    assert rows[1].width is None and rows[1].adb_serial is None


def test_list2_current_layout_includes_resolution_and_dpi():
    rows = parse_list2("4,3-Chíp,0,0,0,-1,-1,1280,720,240\n")
    assert rows == (Instance(4, "3-Chíp", False, -1, -1, 1280, 720, 240),)


def test_starting_is_running_without_android():
    assert parse_list2("8,Farm,0,0,0,123,-1")[0].running


def test_transitional_android_state_is_running_but_not_ready():
    instance = parse_list2("4,3-Chíp,1,2,2,123,-1,1280,720,240")[0]
    assert instance.running and not instance.android_started


@pytest.mark.parametrize(
    "text",
    ["garbage", "0,x,0,0,3,1,1", "-1,x,0,0,0,-1,-1", "0,,0,0,0,-1,-1", "0,x,0,0,0,-1,-1\n0,y,0,0,0,-1,-1"],
)
def test_bad_list_fails_closed(text):
    with pytest.raises(ValueError):
        parse_list2(text)


def test_empty_list():
    assert parse_list2("\n") == ()


@pytest.mark.parametrize(
    "output",
    [
        "emulator-5562\n",
        "error: device 'emulator-5562' not found\n",
        "adb.exe: device 'emulator-5562' not found\n",
    ],
)
def test_indexed_adb_serial_uses_only_ldplayer_authoritative_output(output):
    assert parse_indexed_adb_serial(output) == "emulator-5562"


@pytest.mark.parametrize("output", ["", "one\ntwo\n", "error: no devices", "device '-d' not found"])
def test_indexed_adb_serial_fails_closed_without_one_safe_candidate(output):
    with pytest.raises(ValueError):
        parse_indexed_adb_serial(output)


def test_discovery_requires_console_and_adb(tmp_path):
    (tmp_path / "dnconsole.exe").touch()
    assert inspect_folder(tmp_path) is None
    (tmp_path / "adb.exe").touch()
    assert inspect_folder(tmp_path).console.name == "dnconsole.exe"


@pytest.mark.parametrize(
    "value",
    [
        '"D:\\LDPlayer\\LDPlayer9\\dnplayer.exe",0',
        '"D:\\LDPlayer\\LDPlayer9\\dnplayer.exe" --background',
        "D:\\LDPlayer\\LDPlayer9\\dnplayer.exe,0",
    ],
)
def test_display_icon_folder_when_registry_install_location_is_blank(value):
    assert display_icon_folder(value) == Path("D:/LDPlayer/LDPlayer9")


@pytest.mark.parametrize("value", ["", '"D:\\LDPlayer\\broken.exe', "D:\\LDPlayer\\not-an-exe.dll,0"])
def test_display_icon_folder_rejects_malformed_or_non_executable_paths(value):
    assert display_icon_folder(value) is None


def test_persistence_and_new_defaults(rig, tmp_path):
    manager, _, store = rig
    store.set("package", "com.test.game")
    store2 = Store(tmp_path / "config.sqlite3")
    assert store2.get("package") == "com.test.game"
    assert store2.metadata(manager.namespace, 7).selected
    assert store2.metadata(manager.namespace, 0).protected
    new = Instance(12, "New", False, -1, -1)
    store2.merge(manager.namespace, (new,))
    assert not store2.metadata(manager.namespace, 12).selected


def test_protected_cannot_be_selected(rig):
    manager, _, store = rig
    with pytest.raises(ValueError):
        manager.select(0, True)
    assert not store.metadata(manager.namespace, 0).selected
    manager.protect(7, True)
    assert not store.metadata(manager.namespace, 7).selected


def test_snapshot_selected_only_immutable_and_revocation(rig):
    manager, _, store = rig
    current = manager.refresh()
    snapshot = create_snapshot(store, manager.namespace, current)
    assert snapshot.members == ((7, "Farm-007"),)
    manager.select(7, False)
    assert snapshot.members == ((7, "Farm-007"),)
    with pytest.raises(SafetyError):
        require_selected(store, snapshot, current, 7)
    assert create_snapshot(store, manager.namespace, current).members == ()


def test_rename_remove_reappear_reset_selection_preserve_protection(rig):
    manager, process, store = rig
    process.listing = process.listing.replace("Farm-007", "Replacement")
    manager.refresh()
    assert not store.metadata(manager.namespace, 7).selected
    manager.protect(7, True)
    process.listing = ""
    manager.refresh()
    process.listing = "7,New,0,0,0,-1,-1"
    manager.refresh()
    assert store.metadata(manager.namespace, 7).protected
    assert not store.metadata(manager.namespace, 7).selected


def test_installations_do_not_share_whitelist(rig):
    manager, _, store = rig
    store.merge("different-install", manager.refresh())
    assert not store.metadata("different-install", 7).selected


@pytest.mark.parametrize("index", [None, -1, False, "0", 999, 0])
def test_no_fallback_or_protected_dispatch(rig, index):
    manager, process, _ = rig
    with pytest.raises(SafetyError):
        manager.execute(index, "screenshot")
    assert all(call[1] == "list2" for call in process.calls)
    assert manager._active is None


@pytest.mark.parametrize(
    "action",
    [
        "launch",
        "quit",
        "reboot",
        "packages",
        "open_game",
        "close_game",
        "screenshot",
        "verify",
        "tap",
        "swipe",
        "keyevent",
    ],
)
def test_unchecked_blocks_every_action(rig, action):
    manager, process, _ = rig
    manager.select(7, False)
    with pytest.raises(SafetyError):
        manager.execute(7, action, "com.example.game")
    assert all(call[1] == "list2" for call in process.calls)


def test_adb_mismatch_blocks_action(rig):
    manager, process, _ = rig
    process.device_boot = "bb068632-fc3e-4090-a8d7-ae8d9fe353f5"
    with pytest.raises(SafetyError):
        manager.execute(7, "screenshot")
    assert not any("screencap" in call for call in process.calls)


@pytest.mark.parametrize("state", ["offline", "unauthorized", "missing"])
def test_device_not_ready(rig, state):
    manager, process, _ = rig
    manager.ADB_RESOLVE_TIMEOUT = 0
    process.devices_output = f"List of devices attached\nemulator-5568\t{state}\n"
    with pytest.raises(SafetyError):
        manager.execute(7, "packages")
    assert not any("pm" in call for call in process.calls)


def test_read_only_refresh(rig):
    manager, process, _ = rig
    manager.refresh()
    assert [call[1:] for call in process.calls] == [["list2"]]


def test_capture_correct_target_and_path(rig):
    manager, process, _ = rig
    path = manager.execute(7, "screenshot")
    assert path.read_bytes().startswith(b"\x89PNG")
    capture = next(call for call in process.calls if "screencap" in call)
    assert capture[1:] == ["-s", "emulator-5568", "exec-out", "screencap", "-p"]
    assert all("quitall" not in call for call in process.calls)


def test_package_badging_reads_only_verified_base_apk(rig):
    manager, process, _ = rig
    (manager.ld.installation.console.parent / "aapt.exe").touch()
    output = manager.execute(7, "package_badging", "com.example.game")
    assert "Thời Đại Anh Hùng" in output
    read = next(call for call in process.calls if "exec-out" in call)
    assert read[1:] == ["-s", "emulator-5568", "exec-out", "cat", "/data/app/mock/base.apk"]
    assert not list((manager.data_dir / "diagnostics" / "apk-metadata").glob("*.apk"))


@pytest.mark.parametrize(
    "action,part",
    [
        ("quit", "quit"),
        ("reboot", "launch"),
        ("packages", "pm"),
        ("open_game", "monkey"),
        ("close_game", "force-stop"),
    ],
)
def test_guarded_dispatch(rig, action, part):
    manager, process, _ = rig
    manager.execute(7, action, "com.example.game")
    assert any(part in call for call in process.calls)


def test_protect_during_verification_aborts(rig):
    manager, process, store = rig

    def hook(args):
        if args[1:] == ["devices"]:
            store.protect(manager.namespace, 7, True)

    process.hook = hook
    with pytest.raises(SafetyError):
        manager.execute(7, "screenshot")
    assert not any("screencap" in call for call in process.calls)


@pytest.mark.parametrize("serial", ["", None, "-d", "a b", "x;echo"])
def test_adb_requires_explicit_safe_target(rig, serial):
    manager, process, _ = rig
    with pytest.raises(SafetyError):
        manager.adb._target(serial, "shell", "echo", "test")
    assert process.calls == []


@pytest.mark.parametrize("package", ["", "x;reboot", "com.test && reboot", "-p", "com.test/Activity"])
def test_package_validation(package):
    with pytest.raises(SafetyError):
        validate_package(package)


@pytest.mark.parametrize("value", ["", "error: no devices", "00000000-0000-0000-0000-000000000000"])
def test_invalid_boot_id(value):
    with pytest.raises(SafetyError):
        valid_boot_id(value)


def test_process_subprocess_mock(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, b"ok", b"")

    monkeypatch.setattr(subprocess, "run", run)
    assert Process().run(["console", "list2"]) == b"ok"
    assert calls[0][1]["timeout"] == 20
    assert "shell" not in calls[0][1]


def test_process_timeout(monkeypatch):
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, 20)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(CommandError):
        Process().run(["adb", "devices"])


@pytest.mark.parametrize(
    "action",
    [
        "launch",
        "quit",
        "reboot",
        "packages",
        "open_game",
        "close_game",
        "screenshot",
        "verify",
        "tap",
        "swipe",
        "keyevent",
    ],
)
def test_protected_blocks_every_action_at_execution_layer(rig, action):
    manager, process, _ = rig
    with pytest.raises(SafetyError):
        manager.execute(0, action, "com.example.game")
    assert all(call[1] == "list2" for call in process.calls)


@pytest.mark.parametrize("action,values", [("tap", (4, 5)), ("swipe", (4, 5, 6, 7, 300)), ("keyevent", (4,))])
def test_guarded_input_abstraction(rig, action, values):
    manager, process, _ = rig
    manager.execute(7, action, values=values)
    assert process.calls[-1][1:] == [
        "-s",
        "emulator-5568",
        "shell",
        "input",
        action,
        *(str(v) for v in values),
    ]


def test_transport_changes_just_before_action(rig):
    manager, process, _ = rig
    count = 0

    def hook(args):
        nonlocal count
        if args[1:3] == ["-s", process.serial] and args[-1] == "/proc/sys/kernel/random/boot_id":
            count += 1
            if count == 2:
                process.device_boot = "bb068632-fc3e-4090-a8d7-ae8d9fe353f5"

    process.hook = hook
    with pytest.raises(SafetyError):
        manager.execute(7, "screenshot")
    assert not any("screencap" in call for call in process.calls)

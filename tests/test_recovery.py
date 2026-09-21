from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from top_heroes_auto.app.recovery_cli import (
    DiagnosticRecoveryPort,
    RecoveryFailure,
    run_home_recovery,
)
from top_heroes_auto.automation.actions import SafeInputService
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.recovery import (
    HomeRecoveryEngine,
    RecoveryObservation,
    RecoveryResult,
    RecoveryStatus,
)
from top_heroes_auto.vision.image_normalizer import ScreenshotInvalid
from top_heroes_auto.vision.models import (
    AnchorEvidence,
    BoundingBox,
    CapturedScreen,
    ScreenDetection,
    ScreenState,
)
from top_heroes_auto.vision.screenshot import ScreenshotService


def detection(state: ScreenState, evidence=()):
    return ScreenDetection(
        state,
        1.0 if state != ScreenState.UNKNOWN else 0.0,
        tuple(evidence),
        datetime.now(timezone.utc).isoformat(),
        None,
        1.0,
    )


class Port:
    def __init__(self, *states):
        self.states = list(states)
        self.observations = 0
        self.launches = 0

    def observe(self, step):
        self.observations += 1
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return RecoveryObservation(detection(state), Path(f"{step:03d}.png"), "emulator-5568")

    def launch_game(self):
        self.launches += 1


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class BlankDuringLoadingPort(Port):
    def observe(self, step):
        if step == 2:
            self.observations += 1
            raise ScreenshotInvalid("Image is blank or effectively uniform.")
        return super().observe(step)


class BlankPort(Port):
    def observe(self, step):
        self.observations += 1
        raise ScreenshotInvalid("Image is blank or effectively uniform.")


def test_already_game_home_short_circuits_without_input():
    port = Port(ScreenState.GAME_HOME)
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.ALREADY_HOME
    assert result.actions == []
    assert port.observations == 1


def test_android_home_launches_once_then_waits_for_game_home():
    port = Port(ScreenState.ANDROID_HOME, ScreenState.GAME_LOADING, ScreenState.GAME_HOME)
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert result.states_seen == ["ANDROID_HOME", "GAME_LOADING", "GAME_HOME"]
    assert result.actions == ["launch_game", "wait"]
    assert port.launches == 1


def test_game_loading_waits_without_input_and_times_out():
    clock = Clock()
    port = Port(ScreenState.GAME_LOADING)
    result = HomeRecoveryEngine(
        loading_timeout=3,
        loading_interval=2,
        max_duration=20,
        clock=clock,
        sleep=clock.sleep,
    ).ensure_game_home(port)
    assert result.status == RecoveryStatus.LOADING_TIMEOUT
    assert port.launches == 0
    assert result.actions == ["wait", "wait"]


def test_transient_unknown_after_verified_loading_waits_without_input():
    port = Port(
        ScreenState.ANDROID_HOME,
        ScreenState.GAME_LOADING,
        ScreenState.UNKNOWN,
        ScreenState.UNKNOWN,
        ScreenState.GAME_HOME,
    )
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert result.actions == ["launch_game", "wait", "wait", "wait"]
    assert port.launches == 1


def test_launch_opens_bounded_loading_window_before_loading_anchor_appears():
    port = Port(
        ScreenState.ANDROID_HOME,
        ScreenState.UNKNOWN,
        ScreenState.UNKNOWN,
        ScreenState.GAME_HOME,
    )
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert result.actions == ["launch_game", "wait", "wait"]
    assert port.launches == 1


def test_unknown_loading_transition_is_still_bounded_by_loading_timeout():
    clock = Clock()
    port = Port(ScreenState.GAME_LOADING, ScreenState.UNKNOWN)
    result = HomeRecoveryEngine(
        loading_timeout=3,
        loading_interval=2,
        max_duration=20,
        clock=clock,
        sleep=clock.sleep,
    ).ensure_game_home(port)
    assert result.status == RecoveryStatus.LOADING_TIMEOUT
    assert result.actions == ["wait", "wait"]
    assert port.launches == 0


def test_blank_frame_after_verified_loading_waits_without_input():
    port = BlankDuringLoadingPort(ScreenState.GAME_LOADING, ScreenState.GAME_HOME)
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert result.states_seen == ["GAME_LOADING", "UNKNOWN", "GAME_HOME"]
    assert result.actions == ["wait", "wait"]
    assert port.launches == 0


def test_blank_frame_before_verified_loading_fails_closed():
    port = BlankPort(ScreenState.UNKNOWN)
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.ADB_ERROR
    assert result.actions == []
    assert port.launches == 0


def test_unknown_confirms_with_new_screenshot_then_fails_closed():
    port = Port(ScreenState.UNKNOWN)
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.UNKNOWN_SCREEN
    assert port.observations == 2
    assert result.actions == []
    assert port.launches == 0


def test_failed_launch_postcondition_is_bounded():
    port = Port(ScreenState.ANDROID_HOME)
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.ACTION_FAILED
    assert port.launches == 1
    assert port.observations == 2


def test_cancellation_prevents_next_capture_or_action():
    port = Port(ScreenState.ANDROID_HOME)
    result = HomeRecoveryEngine().ensure_game_home(port, cancelled=lambda: True)
    assert result.status == RecoveryStatus.CANCELLED
    assert port.observations == 0
    assert port.launches == 0


def test_max_steps_bounds_recovery():
    port = Port(ScreenState.GAME_LOADING)
    result = HomeRecoveryEngine(max_steps=2, loading_interval=0, sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert port.observations == 2


def test_max_duration_bounds_recovery():
    clock = Clock()
    port = Port(ScreenState.GAME_LOADING)
    result = HomeRecoveryEngine(
        max_steps=20,
        max_duration=3,
        loading_timeout=99,
        loading_interval=2,
        clock=clock,
        sleep=clock.sleep,
    ).ensure_game_home(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert port.observations == 2


def test_detected_target_maps_device_center_and_dispatches_once():
    calls = []
    evidence = AnchorEvidence(
        "popup-close",
        ScreenState.POPUP_GENERIC,
        0.99,
        0.9,
        True,
        BoundingBox(100, 100, 20, 20),
        BoundingBox(200, 300, 40, 20),
    )
    service = SafeInputService(4, "3-Chíp", lambda action, values: calls.append((action, values)))
    service.tap_detected_target(detection(ScreenState.POPUP_GENERIC, (evidence,)), "popup-close")
    assert calls == [("tap", (220, 310))]


@pytest.mark.parametrize("state", [ScreenState.UNKNOWN, ScreenState.POPUP_GENERIC])
def test_tap_requires_verified_evidence_and_never_clicks_blindly(state):
    calls = []
    service = SafeInputService(4, "3-Chíp", lambda action, values: calls.append((action, values)))
    with pytest.raises(SafetyError, match="DO NOT TAP"):
        service.tap_detected_target(detection(state), "missing")
    assert calls == []


def test_run_owned_instance_is_started_and_cleaned_up(rig, tmp_path):
    manager, process, _ = rig
    process.listing = "0,Queen,0,0,0,-1,-1\n7,Farm-007,0,0,0,-1,-1\n"
    manager.refresh()

    class AlreadyHome:
        def ensure_game_home(self, port, cancelled):
            return RecoveryResult(RecoveryStatus.ALREADY_HOME, adb_target="emulator-5568")

    result, report, started = run_home_recovery(
        manager,
        tmp_path,
        7,
        "Farm-007",
        engine=AlreadyHome(),
    )
    assert result.status == RecoveryStatus.ALREADY_HOME
    assert started
    assert report.is_file()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["cleanup_performed"] is True
    assert payload["started_by_run"] is True
    lifecycle = [call[1] for call in process.calls if len(call) > 1 and call[1] in {"launch", "quit"}]
    assert lifecycle == ["launch", "quit"]


def test_recovery_report_failure_cleans_only_instance_started_by_run(rig, tmp_path, monkeypatch):
    manager, process, _ = rig
    process.listing = "0,Queen,0,0,0,-1,-1\n7,Farm-007,0,0,0,-1,-1\n"
    manager.refresh()

    class AlreadyHome:
        def ensure_game_home(self, port, cancelled):
            return RecoveryResult(RecoveryStatus.ALREADY_HOME, adb_target="emulator-5568")

    original_write_text = Path.write_text

    def fail_report(path, data, *args, **kwargs):
        if path.name == "report.json":
            raise OSError("recovery report unavailable")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report)
    with pytest.raises(RecoveryFailure, match="recovery report unavailable") as raised:
        run_home_recovery(
            manager,
            tmp_path,
            7,
            "Farm-007",
            cleanup_owned=False,
            engine=AlreadyHome(),
        )
    assert raised.value.started_by_run
    assert raised.value.cleanup_attempted
    assert raised.value.cleanup_succeeded
    lifecycle = [call[1] for call in process.calls if len(call) > 1 and call[1] in {"launch", "quit"}]
    assert lifecycle == ["launch", "quit"]


def test_recovery_report_failure_does_not_stop_externally_running_instance(rig, tmp_path, monkeypatch):
    manager, process, _ = rig
    process.listing = "0,Queen,0,0,0,-1,-1\n7,Farm-007,3,4,1,201,202\n"
    manager.refresh()

    class AlreadyHome:
        def ensure_game_home(self, port, cancelled):
            return RecoveryResult(RecoveryStatus.ALREADY_HOME, adb_target="emulator-5568")

    original_write_text = Path.write_text

    def fail_report(path, data, *args, **kwargs):
        if path.name == "report.json":
            raise OSError("recovery report unavailable")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report)
    with pytest.raises(RecoveryFailure, match="recovery report unavailable") as raised:
        run_home_recovery(
            manager,
            tmp_path,
            7,
            "Farm-007",
            cleanup_owned=False,
            engine=AlreadyHome(),
        )
    assert not raised.value.started_by_run
    assert not raised.value.cleanup_attempted
    assert not raised.value.cleanup_succeeded
    lifecycle = [call[1] for call in process.calls if len(call) > 1 and call[1] in {"launch", "quit"}]
    assert lifecycle == []


def test_recovery_report_failure_with_uncertain_owned_cleanup_is_not_retryable(
    rig, tmp_path, monkeypatch
):
    manager, process, _ = rig
    process.listing = "0,Queen,0,0,0,-1,-1\n7,Farm-007,0,0,0,-1,-1\n"
    manager.refresh()

    class AlreadyHome:
        def ensure_game_home(self, port, cancelled):
            return RecoveryResult(RecoveryStatus.ALREADY_HOME, adb_target="emulator-5568")

    original_write_text = Path.write_text
    original_execute = manager.execute

    def fail_report(path, data, *args, **kwargs):
        if path.name == "report.json":
            raise OSError("recovery report unavailable")
        return original_write_text(path, data, *args, **kwargs)

    def fail_quit(index, action, *args, **kwargs):
        if action == "quit":
            raise RuntimeError("quit dispatch uncertain")
        return original_execute(index, action, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report)
    monkeypatch.setattr(manager, "execute", fail_quit)
    with pytest.raises(RecoveryFailure, match="quit dispatch uncertain") as raised:
        run_home_recovery(
            manager,
            tmp_path,
            7,
            "Farm-007",
            cleanup_owned=False,
            engine=AlreadyHome(),
        )
    assert raised.value.started_by_run
    assert raised.value.cleanup_attempted
    assert not raised.value.cleanup_succeeded
    lifecycle = [call[1] for call in process.calls if len(call) > 1 and call[1] in {"launch", "quit"}]
    assert lifecycle == ["launch"]


def test_protected_recovery_is_rejected_before_mutation(rig, tmp_path):
    manager, process, _ = rig
    process.listing = process.listing.replace("Main-Thang", "Queen")
    manager.refresh()
    manager.protect(7, True)
    process.calls.clear()
    with pytest.raises(SafetyError, match="selected and not Protected"):
        run_home_recovery(manager, tmp_path, 7, "Farm-007")
    assert not any(call[1] in {"launch", "quit", "-s"} for call in process.calls if len(call) > 1)


def test_recovery_observation_uses_explicit_adb_target(rig, tmp_path, monkeypatch):
    manager, process, _ = rig
    image = np.full((720, 1280, 3), 80, dtype=np.uint8)
    captured = CapturedScreen(
        7,
        "Farm-007",
        "emulator-5568",
        "ce068632-fc3e-4090-a8d7-ae8d9fe353f5",
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        tmp_path / "capture.png",
    )
    monkeypatch.setattr(ScreenshotService, "take", lambda *args, **kwargs: captured)
    monkeypatch.setattr(
        "top_heroes_auto.vision.detector.ScreenDetector.detect",
        lambda self, screen: detection(ScreenState.GAME_HOME),
    )
    snapshot = RunSnapshot(manager.namespace, ((7, "Farm-007"),), True)
    port = DiagnosticRecoveryPort(manager, snapshot, 7, "Farm-007", tmp_path)
    observation = port.observe(1)
    assert observation.adb_target == "emulator-5568"
    screenshot_call = next(call for call in process.calls if "screencap" in call)
    assert screenshot_call[1:3] == ["-s", "emulator-5568"]

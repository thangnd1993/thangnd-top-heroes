"""Final diagnostic evidence can settle loading only within original bounds."""

from dataclasses import replace
from pathlib import Path

import pytest
from test_recovery import detection

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.recovery import (
    RecoveryObservation,
    RecoveryResult,
    RecoveryStatus,
    RecoveryStep,
    confirm_final_home,
)
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def timeout():
    return RecoveryResult(
        RecoveryStatus.LOADING_TIMEOUT,
        steps=[RecoveryStep(10, ScreenState.UNKNOWN, 0, None)],
        actions=["launch_game", "wait"],
        adb_target="explicit",
        boot_id="same-boot",
        duration=100,
        error="Loading timeout",
    )


def final(state=ScreenState.GAME_HOME):
    return RecoveryObservation(detection(state), Path("final.png"), "explicit", "same-boot")


def confirm(result, observation, **kw):
    return confirm_final_home(result, observation, **dict(duration=104, max_duration=120, max_steps=30, **kw))


def test_current_final_home_settles_timeout_without_another_input():
    result = timeout()
    assert confirm(result, final())
    assert result.status == RecoveryStatus.SUCCESS and result.error is None
    assert result.states_seen == ["UNKNOWN", "GAME_HOME"]
    assert result.actions == ["launch_game", "wait", "verify_final_home"]
    assert result.duration == 104 and result.screenshots == ["final.png"]
    assert not confirm(result, final())  # No repeated final-check loop.


@pytest.mark.parametrize(
    "state",
    [
        ScreenState.UNKNOWN,
        ScreenState.GAME_LOADING,
        ScreenState.PROMO_LOADING,
        ScreenState.HOME_OVERLAY,
        ScreenState.POPUP_GENERIC,
    ],
)
def test_final_non_home_does_not_authorize_input_or_success(state):
    result = timeout()
    before = result.as_dict()
    assert not confirm(result, final(state))
    assert result.as_dict() == before


@pytest.mark.parametrize(
    "status",
    [
        RecoveryStatus.ADB_ERROR,
        RecoveryStatus.CANCELLED,
        RecoveryStatus.PROMO_BLOCKING,
        RecoveryStatus.UNKNOWN_SCREEN,
        RecoveryStatus.LIMIT_REACHED,
    ],
)
def test_other_failure_is_not_relabelled_by_final_home(status):
    result = timeout()
    result.status = status
    assert not confirm(result, final()) and result.status == status


@pytest.mark.parametrize(
    "change",
    [
        {"duration": 120},
        {"duration": 99},
        {"max_steps": 1},
        {"max_steps": 10},
        {"serial": "different"},
        {"boot": "different"},
        {"boot": None},
        {"screenshot": None},
    ],
)
def test_deadline_steps_identity_and_persisted_frame_are_required(change):
    result = timeout()
    observation = final()
    bounds = dict(duration=104, max_duration=120, max_steps=30)
    if "serial" in change:
        observation = replace(observation, adb_target=change["serial"])
    elif "boot" in change:
        observation = replace(observation, boot_id=change["boot"])
    elif "screenshot" in change:
        observation = replace(observation, screenshot=change["screenshot"])
    else:
        bounds.update(change)
    assert not confirm_final_home(result, observation, **bounds)
    assert result.status == RecoveryStatus.LOADING_TIMEOUT


def test_real_final_frame_independently_proves_home():
    p = Path(__file__).parent / "fixtures/phase7_resume/home-at-loading-deadline.png"
    c = ScreenshotService(lambda _: p.read_bytes()).take(Target(43, "offline", "explicit", "same-boot"))
    found = RecoveryScreenDetector().detect(c)
    assert found.state == ScreenState.GAME_HOME and found.confidence > 0.97
    assert len(found.evidence) >= 2 and all(a.matched for a in found.evidence)
    assert confirm(timeout(), RecoveryObservation(found, p, c.serial, c.boot_id))


@pytest.mark.parametrize("cancel_after_capture", [False, True])
def test_production_final_capture_settles_only_without_cancellation(
    rig, tmp_path, monkeypatch, cancel_after_capture
):
    from top_heroes_auto.app.recovery_cli import DiagnosticRecoveryPort, run_home_recovery

    manager, process, _ = rig
    process.listing = "0,Queen,0,0,0,-1,-1\n7,Farm-007,3,4,1,201,202\n"
    manager.refresh()
    cancelled = False
    captures = []

    class TimeoutEngine:
        max_duration = 120
        max_steps = 30

        def ensure_game_home(self, port, cancel):
            return timeout()

    def capture_final(port):
        nonlocal cancelled
        captures.append(True)
        port.started = port.clock() - 104
        cancelled = cancel_after_capture
        return final()

    monkeypatch.setattr(DiagnosticRecoveryPort, "persist_final", capture_final)
    result, path, started = run_home_recovery(
        manager, tmp_path, 7, "Farm-007", engine=TimeoutEngine(), cancelled=lambda: cancelled
    )
    assert path.is_file() and not started and len(captures) == 1
    assert result.status == (
        RecoveryStatus.LOADING_TIMEOUT if cancel_after_capture else RecoveryStatus.SUCCESS
    )
    assert not any(call[1] in ("launch", "quit", "adb", "-s") for call in process.calls)


def test_final_capture_returns_observation_once_and_resets_flag(tmp_path):
    from top_heroes_auto.app.recovery_cli import DiagnosticRecoveryPort

    port = object.__new__(DiagnosticRecoveryPort)
    port.folder = tmp_path
    port.diagnostic_samples = []
    observation = final()
    calls = []

    def observe(step):
        calls.append(step)
        assert port.final_sample
        return observation

    port.observe = observe
    assert port.persist_final() is observation
    assert calls == [0] and not port.final_sample

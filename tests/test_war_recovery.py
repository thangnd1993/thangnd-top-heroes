"""Saved empty War screen and fake recovery ports; no emulator access."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest
from test_recovery import Clock, Port, detection

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.recovery_cli import DiagnosticRecoveryPort
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.recovery import HomeRecoveryEngine, RecoveryStatus
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService
from top_heroes_auto.vision.war_recovery import war_back_point

ROOT = Path(__file__).parent / "fixtures/phase8"


def capture(name="war-empty-recovery"):
    fixture = ROOT / f"{name}.png" if name == "war-empty-recovery" else ROOT.parent / "phase7_resume" / f"{name}.png"
    return ScreenshotService(lambda _: fixture.read_bytes()).take(
        Target(43, "offline", "explicit", "boot"))


def test_saved_board_requires_four_unique_strict_anchors():
    frame = capture()
    found = RecoveryScreenDetector().detect(frame)
    assert found.state == ScreenState.WAR_EMPTY and found.confidence >= .98
    assert len(found.evidence) == 4 and all(e.matched for e in found.evidence)
    back = next(e for e in found.evidence if e.anchor_id == "war-back")
    assert war_back_point(frame, found) == back.device_box.center


@pytest.mark.parametrize("role", ["war-title", "war-tabs", "war-empty", "war-back"])
@pytest.mark.parametrize("mode", ["missing", "duplicate", "weak"])
def test_partial_weak_or_duplicate_board_is_not_recoverable(role, mode):
    frame = capture()
    detector = RecoveryScreenDetector()
    found = detector.detect(frame)
    box = next(e.normalized_box for e in found.evidence if e.anchor_id == role)
    image = frame.normalized.copy()
    patch = image[box.y:box.y+box.height, box.x:box.x+box.width].copy()
    if mode == "duplicate":
        image[100:100+box.height, 500:500+box.width] = patch
    else:
        image[box.y:box.y+box.height, box.x:box.x+box.width] = (
            cv2.GaussianBlur(patch, (15,15), 5) if mode == "weak" else 0)
    changed = replace(frame, normalized=image)
    result = detector.detect(changed)
    assert result.state == ScreenState.UNKNOWN
    with pytest.raises(SafetyError):
        war_back_point(changed, result)


def test_changing_counts_and_map_does_not_change_qualified_navigation():
    image = cv2.imread(str(ROOT / "war-empty-recovery.png"))
    # These are fixture transformations, never runtime action coordinates.
    image[300:550, 20:690] = 90
    image[700:1100, 20:690] = 80
    image[1205:1240, 480:640] = 80
    changed = ScreenshotService(lambda _: cv2.imencode('.png',image)[1].tobytes()).take(
        Target(81, "other-account", "explicit-other", "boot"))
    assert RecoveryScreenDetector().detect(changed).state == ScreenState.WAR_EMPTY


@pytest.mark.parametrize("name", ["home-at-loading-deadline", "member-two", "mail-eight", "shop-monthly-owned"])
def test_unrelated_saved_gameplay_cannot_authorize_bounty_back(name):
    frame = capture(name)
    found = RecoveryScreenDetector().detect(frame)
    assert found.state != ScreenState.WAR_EMPTY
    with pytest.raises(SafetyError):
        war_back_point(frame, found)


def test_conflicting_known_screen_cannot_authorize_back(monkeypatch):
    detector = RecoveryScreenDetector()
    monkeypatch.setattr(detector, '_detect_existing', lambda _: detection(ScreenState.GAME_HOME))
    assert detector.detect(capture()).state == ScreenState.UNKNOWN


class WarPort(Port):
    def __init__(self, *states):
        super().__init__(*states)
        self.back_frames = []

    def back_from_war(self, observation):
        assert observation.detection.state == ScreenState.WAR_EMPTY
        assert self.observations not in self.back_frames
        self.back_frames.append(self.observations)
        return (31, 701)


def engine(**kwargs):
    clock = Clock()
    return HomeRecoveryEngine(clock=clock, sleep=clock.sleep, **kwargs)


def test_recognized_board_one_back_fresh_home_and_success():
    port = WarPort(ScreenState.WAR_EMPTY, ScreenState.GAME_HOME)
    result = engine().ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert port.back_frames == [1] and port.observations == 2
    assert result.actions == ['back_from_war:31,701']


def test_persistent_board_stops_after_two_fresh_attempts():
    port = WarPort(ScreenState.WAR_EMPTY)
    result = engine().ensure_game_home(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert port.back_frames == [1, 2] and port.observations == 3


def test_changed_unknown_stops_back_and_never_restarts_loop():
    port = WarPort(ScreenState.WAR_EMPTY, ScreenState.UNKNOWN, ScreenState.WAR_EMPTY)
    result = engine().ensure_game_home(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED and port.back_frames == [1]


@pytest.mark.parametrize("state", [ScreenState.UNKNOWN, ScreenState.FREE_REWARD_PAGE, ScreenState.POPUP_GENERIC])
def test_arbitrary_state_never_gets_back(state):
    port = WarPort(state)
    assert engine().ensure_game_home(port).status != RecoveryStatus.SUCCESS
    assert not port.back_frames


def test_hanging_to_home_overlay_uses_existing_recovery_rules():
    port = WarPort(ScreenState.WAR_EMPTY, ScreenState.HOME_OVERLAY, ScreenState.HOME_OVERLAY, ScreenState.GAME_HOME)
    result = engine().ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS and port.back_frames == [1]
    assert port.dismissals == 1


def test_no_back_without_post_capture_budget_or_when_cancelled():
    port = WarPort(ScreenState.WAR_EMPTY)
    assert engine(max_steps=1).ensure_game_home(port).status == RecoveryStatus.LIMIT_REACHED
    assert not port.back_frames
    assert engine().ensure_game_home(port, cancelled=lambda: True).status == RecoveryStatus.CANCELLED
    assert not port.back_frames


def test_production_back_consumes_fresh_qualified_frame_once():
    frame = capture()
    found = RecoveryScreenDetector().detect(frame)
    target = Target(frame.index, frame.name, frame.serial, frame.boot_id)
    port = object.__new__(DiagnosticRecoveryPort)
    port.index, port.name, port.snapshot = frame.index, frame.name, "snapshot"
    calls = []
    port.manager = SimpleNamespace(execute=lambda *a, **kw: calls.append((a,kw)))
    port._overlay_frame = target, frame, found
    obs = SimpleNamespace(detection=found)
    point = port.back_from_war(obs)
    assert calls == [((frame.index, 'tap'), dict(values=point, snapshot='snapshot', observed_target=target))]
    assert port._after_overlay and port._overlay_frame is None
    with pytest.raises(SafetyError):
        port.back_from_war(obs)
    assert len(calls) == 1


def test_uncertain_back_transport_never_retries():
    port = WarPort(ScreenState.WAR_EMPTY)
    calls = []
    def fail(observation):
        calls.append(observation)
        raise OSError("Transport outcome uncertain")
    port.back_from_war = fail
    assert engine().ensure_game_home(port).status == RecoveryStatus.ACTION_FAILED
    assert len(calls) == 1 and port.observations == 1


def test_recovered_external_session_continues_pending_flow_without_lifecycle(rig, tmp_path):
    from test_instance_pipeline import setup

    from top_heroes_auto.app.automation_fleet import execute_instance
    from top_heroes_auto.app.instance_session import InstanceSession
    manager, process, _ = rig
    process.listing = "0,Queen,0,0,0,-1,-1\n7,Farm-007,3,4,1,201,202\n"
    manager.refresh()
    before = manager.store.metadata(manager.namespace, 7).selected
    calls = []
    registry, _, _ = setup(calls)
    port = WarPort(ScreenState.WAR_EMPTY, ScreenState.GAME_HOME)
    def recover(*a, **kw):
        return engine().ensure_game_home(port), tmp_path/'recovery.json', False
    def session(*a, **kw):
        return InstanceSession(*a, **kw, recovery_runner=recover)
    prior = dict(recovery_ok=False, rewards={
        'one':dict(result='SUCCESS', journal='VERIFIED', claim_id=91),
        'two':dict(result='UNKNOWN'),
        'three':dict(result='NOT_AVAILABLE')})
    result = execute_instance(manager,tmp_path,dict(index=7,name='Farm-007',persistent_identity='disk'),
        tmp_path/'account',registry,prior=prior,session_factory=session,identity_reader=lambda *a:'disk')
    assert result['result'] == 'COMPLETE' and calls == [(7,'feature-one',('two',))]
    assert port.back_frames == [1] and result['cleanup'] == 'NOT_REQUIRED'
    assert not result['session']['started_by_run'] and result['selection_restored']
    assert manager.store.metadata(manager.namespace,7).selected == before
    assert manager.query(7).running
    assert not any(c[1] in ('launch','quit') for c in process.calls)


def test_deadline_after_back_still_captures_but_never_sends_another_input():
    port = WarPort(ScreenState.WAR_EMPTY)
    result = engine(max_duration=2).ensure_game_home(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert port.back_frames == [1] and port.observations == 2


def test_low_overall_confidence_cannot_authorize_navigation():
    frame = capture()
    found = RecoveryScreenDetector().detect(frame)
    with pytest.raises(SafetyError):
        war_back_point(frame, replace(found, confidence=.5))

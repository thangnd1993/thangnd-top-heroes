"""Qualified saved World views and fake ports; no real lifecycle or gameplay."""
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
from top_heroes_auto.vision.world_recovery import world_return_point

ROOT = Path(__file__).parent / 'fixtures/phase8'


def capture(name='world-map-one'):
    return ScreenshotService(lambda _: (ROOT/(name+'.png')).read_bytes()).take(
        Target(43, 'offline', 'explicit', 'boot'))


@pytest.mark.parametrize('name', ['world-map-one', 'world-map-two'])
def test_saved_world_requires_independent_current_hud_controls(name):
    frame = capture(name)
    found = RecoveryScreenDetector().detect(frame)
    assert found.state == ScreenState.GAME_WORLD and found.confidence >= .99
    assert len(found.evidence) == 4 and all(e.matched for e in found.evidence)
    castle = next(e.device_box for e in found.evidence if e.anchor_id == 'world-return-castle')
    assert world_return_point(frame, found) == castle.center


@pytest.mark.parametrize('role', ['world-return-label', 'world-return-castle', 'world-search', 'world-locator'])
@pytest.mark.parametrize('mode', ['missing', 'duplicate', 'weak'])
def test_partial_ambiguous_or_weak_world_cannot_authorize_input(role, mode):
    frame = capture()
    found = RecoveryScreenDetector().detect(frame)
    box = next(e.normalized_box for e in found.evidence if e.anchor_id == role)
    image = frame.normalized.copy()
    patch = image[box.y:box.y+box.height, box.x:box.x+box.width].copy()
    if mode == 'duplicate':
        image[100:100+box.height, 500:500+box.width] = patch
    else:
        image[box.y:box.y+box.height, box.x:box.x+box.width] = (
            cv2.GaussianBlur(patch, (15,15), 5) if mode == 'weak' else 0)
    changed = replace(frame, normalized=image)
    result = RecoveryScreenDetector().detect(changed)
    assert result.state != ScreenState.GAME_WORLD
    with pytest.raises(SafetyError):
        world_return_point(changed, result)


def test_current_controls_can_move_without_any_account_route():
    frame = capture()
    found = RecoveryScreenDetector().detect(frame)
    image = frame.normalized.copy()
    for evidence in found.evidence:
        b = evidence.normalized_box
        patch = image[b.y:b.y+b.height, b.x:b.x+b.width].copy()
        image[b.y:b.y+b.height, b.x:b.x+b.width] = 0
        image[b.y-10:b.y-10+b.height, b.x+10:b.x+10+b.width] = patch
    changed = replace(frame, normalized=image, index=99, name='another-account')
    moved = RecoveryScreenDetector().detect(changed)
    assert moved.state == ScreenState.GAME_WORLD
    assert world_return_point(changed, moved) != world_return_point(frame, found)


def test_map_boss_chat_and_dynamic_numbers_are_not_anchors():
    image = cv2.imread(str(ROOT/'world-map-one.png'))
    image[250:775, 100:610] = 90
    image[1000:1040, 200:580] = 70
    frame = ScreenshotService(lambda _: cv2.imencode('.png',image)[1].tobytes()).take(
        Target(81, 'another-account', 'other-explicit', 'boot'))
    assert RecoveryScreenDetector().detect(frame).state == ScreenState.GAME_WORLD


@pytest.mark.parametrize('name', ['world-attack-confirmation', 'war-empty-recovery', 'task-grid-tall-fraction'])
def test_popup_paid_and_unrelated_states_never_authorize_return_city(name):
    frame = capture(name)
    found = RecoveryScreenDetector().detect(frame)
    assert found.state != ScreenState.GAME_WORLD
    with pytest.raises(SafetyError):
        world_return_point(frame, found)


def test_home_or_paid_relocation_words_do_not_replace_return_label():
    frame = capture()
    found = RecoveryScreenDetector().detect(frame)
    label = next(e.normalized_box for e in found.evidence if e.anchor_id == 'world-return-label')
    image = frame.normalized.copy()
    image[label.y:label.y+label.height,label.x:label.x+label.width] = 0
    cv2.putText(image,'Move City / WORLD',(500,400),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
    assert RecoveryScreenDetector().detect(replace(frame,normalized=image)).state != ScreenState.GAME_WORLD


def test_conflicting_known_state_remains_unknown(monkeypatch):
    detector = RecoveryScreenDetector()
    monkeypatch.setattr(detector, '_detect_existing', lambda _: detection(ScreenState.GAME_HOME))
    assert detector.detect(capture()).state == ScreenState.UNKNOWN


class WorldPort(Port):
    def __init__(self, *states):
        super().__init__(*states)
        self.inputs = []

    def observe(self, step):
        observed = super().observe(step)
        return replace(observed, boot_id='boot',
                       detection=replace(observed.detection, timestamp=f'fresh-{step}'))

    def return_from_world(self, observation):
        assert observation.detection.state == ScreenState.GAME_WORLD
        self.inputs.append(self.observations)
        return (653,1184)


def engine(**kwargs):
    clock = Clock()
    return HomeRecoveryEngine(clock=clock,sleep=clock.sleep,**kwargs)


def test_two_fresh_world_frames_one_input_then_fresh_home():
    port = WorldPort(ScreenState.GAME_WORLD, ScreenState.GAME_WORLD, ScreenState.GAME_HOME)
    result = engine().ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert port.inputs == [2] and port.observations == 3 and port.launches == 0


def test_persistent_world_never_retries_navigation():
    port = WorldPort(ScreenState.GAME_WORLD)
    result = engine().ensure_game_home(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert port.inputs == [2] and port.observations == 3


def test_intervening_unknown_breaks_stability():
    port = WorldPort(ScreenState.GAME_WORLD, ScreenState.UNKNOWN, ScreenState.GAME_WORLD)
    result = engine(max_steps=4).ensure_game_home(port)
    assert not port.inputs and result.status == RecoveryStatus.LIMIT_REACHED


def test_uncertain_navigation_is_consumed_once():
    port = WorldPort(ScreenState.GAME_WORLD)
    def fail(observation):
        port.inputs.append(port.observations)
        raise OSError('Uncertain transport')
    port.return_from_world = fail
    assert engine().ensure_game_home(port).status == RecoveryStatus.ACTION_FAILED
    assert port.inputs == [2] and port.observations == 2


@pytest.mark.parametrize('max_steps,max_duration', [(2,120),(30,2),(30,4)])
def test_bounds_preserve_capture_and_prevent_additional_input(max_steps,max_duration):
    port = WorldPort(ScreenState.GAME_WORLD)
    result = engine(max_steps=max_steps,max_duration=max_duration).ensure_game_home(port)
    assert result.status == RecoveryStatus.LIMIT_REACHED
    assert len(port.inputs) <= 1
    if port.inputs:
        assert port.observations == 3


def test_stale_confirmation_or_missing_boot_never_taps():
    for missing in (False,True):
        port = WorldPort(ScreenState.GAME_WORLD)
        obs = port.observe(0)
        if missing:
            obs = replace(obs,boot_id=None)
        port.observe = lambda _: obs
        assert engine().ensure_game_home(port).status == RecoveryStatus.UNKNOWN_SCREEN
        assert not port.inputs


def test_production_port_consumes_current_frame_even_when_dispatch_fails():
    frame = capture()
    found = RecoveryScreenDetector().detect(frame)
    calls = []
    def fail(*args,**kwargs):
        calls.append((args,kwargs))
        raise SafetyError('Live identity revoked')
    port = DiagnosticRecoveryPort.__new__(DiagnosticRecoveryPort)
    target = Target(frame.index,frame.name,frame.serial,frame.boot_id)
    port._overlay_frame = target,frame,found
    port._after_overlay = False
    port.manager = SimpleNamespace(execute=fail)
    port.index,port.name,port.snapshot = frame.index,frame.name,'snapshot'
    obs = SimpleNamespace(detection=found)
    with pytest.raises(SafetyError):
        port.return_from_world(obs)
    assert port._overlay_frame is None and port._after_overlay
    with pytest.raises(SafetyError):
        port.return_from_world(obs)
    assert len(calls) == 1
    args,kwargs = calls[0]
    assert args == (frame.index,'tap')
    assert kwargs == dict(values=world_return_point(frame,found),snapshot='snapshot',observed_target=target)


@pytest.mark.parametrize('state', [ScreenState.UNKNOWN, ScreenState.POPUP_GENERIC, ScreenState.FREE_REWARD_PAGE])
def test_unknown_and_unrelated_pages_send_no_world_input(state):
    port = WorldPort(state)
    assert engine().ensure_game_home(port).status != RecoveryStatus.SUCCESS
    assert not port.inputs and not port.launches


def test_home_fixture_cannot_authorize_return_city():
    path = ROOT.parent/'phase7_resume/home-at-loading-deadline.png'
    frame = ScreenshotService(lambda _: path.read_bytes()).take(Target(48,'offline','explicit','boot'))
    found = RecoveryScreenDetector().detect(frame)
    assert found.state != ScreenState.GAME_WORLD
    with pytest.raises(SafetyError):
        world_return_point(frame,found)


def test_external_instance_recovery_preserves_lifecycle_selection_and_prior_rewards(rig,tmp_path):
    from test_instance_pipeline import setup

    from top_heroes_auto.app.automation_fleet import execute_instance
    from top_heroes_auto.app.instance_session import InstanceSession
    manager,process,_ = rig
    process.listing = '0,Queen,0,0,0,-1,-1\n7,Farm-007,3,4,1,201,202\n'
    manager.refresh()
    before = manager.store.metadata(manager.namespace,7).selected
    calls = []
    registry,_,_ = setup(calls)
    port = WorldPort(ScreenState.GAME_WORLD,ScreenState.GAME_WORLD,ScreenState.GAME_HOME)
    def recover(*args,**kwargs):
        return engine().ensure_game_home(port),tmp_path/'recovery.json',False
    def session(*args,**kwargs):
        return InstanceSession(*args,**kwargs,recovery_runner=recover)
    prior = dict(recovery_ok=False,rewards={
        'one':dict(result='SUCCESS',journal='VERIFIED',claim_id=91),
        'two':dict(result='UNKNOWN'),
        'three':dict(result='NOT_AVAILABLE')})
    result = execute_instance(manager,tmp_path,dict(index=7,name='Farm-007',persistent_identity='disk'),
        tmp_path/'account',registry,prior=prior,session_factory=session,identity_reader=lambda *a:'disk')
    assert result['result'] == 'COMPLETE' and calls == [(7,'feature-one',('two',))]
    assert result['cleanup'] == 'NOT_REQUIRED' and result['selection_restored']
    assert not result['session']['started_by_run']
    assert manager.store.metadata(manager.namespace,7).selected == before and manager.query(7).running
    assert port.inputs == [2]
    assert not any(c[1] in ('launch','quit') for c in process.calls)

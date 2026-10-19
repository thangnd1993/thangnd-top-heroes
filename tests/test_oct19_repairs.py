from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from top_heroes_auto.app.service import TransportResolutionError
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.detector import ScreenDetector
from top_heroes_auto.vision.models import AnchorEvidence, NormalizedRect, ScreenState, VisualAnchor


def test_failed_required_variant_skips_work_without_hiding_competitor(monkeypatch, tmp_path):
    anchors = tuple(VisualAnchor(name, state, tmp_path / 'a.png', NormalizedRect(0, 0, 1, 1), .98)
                    for name, state in [('absent-title', ScreenState.GAME_HOME),
                                        ('unused-detail', ScreenState.GAME_HOME),
                                        ('present', ScreenState.GAME_LOADING)])
    calls = []
    def match(screen, anchor):
        calls.append(anchor.id)
        return AnchorEvidence(anchor.id, anchor.state, 1 if anchor.id == 'present' else 0,
                              .98, anchor.id == 'present')
    monkeypatch.setattr('top_heroes_auto.vision.detector.match_anchor', match)
    result = ScreenDetector(anchors).detect(SimpleNamespace(source_image=None))
    assert result.state == ScreenState.GAME_LOADING
    assert calls == ['absent-title', 'present']


def test_observed_input_probes_explicit_boot_once(rig):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    process.calls.clear()
    manager.execute(7, 'tap', values=(100, 100), observed_target=target)
    probes = [c for c in process.calls if c[1:3] == ['-s', target.serial]
              and c[-1].endswith('boot_id')]
    assert len(probes) == 1
    assert len([c for c in process.calls if 'input' in c]) == 1


def test_unbound_serial_is_not_even_probed(rig):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    process.calls.clear()
    with pytest.raises(SafetyError):
        manager.execute(7, 'tap', values=(100, 100), observed_target=replace(target, serial='emulator-9998'))
    assert not any('emulator-9998' in c for c in process.calls)


@pytest.mark.parametrize('status', ['offline', None])
def test_resolution_reports_exact_stage_and_retains_owned_launch(rig, status):
    manager, process, _ = rig
    process.listing = process.listing.replace('7,Farm-007,3,4,1,201,202', '7,Farm-007,0,0,0,-1,-1')
    process.devices_output = 'List of devices attached\n' + (f'emulator-5568\t{status}\n' if status else '')
    manager.ADB_RESOLVE_TIMEOUT = 0
    with pytest.raises(TransportResolutionError):
        manager.execute(7, 'launch', allow_lifecycle_retry=False)
    proof = manager.last_adb_resolution
    assert proof['android_ready'] is True
    assert proof['stage'] == 'TARGET_TRANSPORT_UNAVAILABLE'
    assert proof['samples'][-1]['transports']['emulator-5568'] == (status or 'ABSENT')
    assert manager.last_lifecycle_attempt.ownership == 'OWNED'
    assert not any('kill-server' in c for c in process.calls)


def test_failed_scoped_retry_keeps_lifecycle_proof_and_stops_only_owned_target(rig):
    manager, process, _ = rig
    process.listing = process.listing.replace('7,Farm-007,3,4,1,201,202', '7,Farm-007,0,0,0,-1,-1')
    process.devices_output = 'List of devices attached\n'
    manager.ADB_RESOLVE_TIMEOUT = 0
    with pytest.raises(TransportResolutionError):
        manager.execute(7, 'launch')
    attempt = manager.last_lifecycle_attempt
    assert attempt.ownership == 'OWNED' and attempt.failure_stage == 'resolve_transport_retry'
    assert len(attempt.dispatches) == 2
    quits = [c for c in process.calls if c[1] == 'quit']
    assert len(quits) == 2 and all(c[2:] == ['--index','7'] for c in quits)


def test_cleanup_proof_cannot_target_replacement_process(rig):
    manager, process, _ = rig
    from top_heroes_auto.automation.guard import create_snapshot
    current = manager.refresh()
    manager._active = create_snapshot(manager.store, manager.namespace, current)
    expected = next(i for i in current if i.index == 7)
    process.listing = process.listing.replace('201,202', '901,902')
    with pytest.raises(SafetyError, match='runtime changed'):
        manager._stop(7, expected=expected)
    assert not any(c[1]=='quit' for c in process.calls)


def test_current_paired_nested_tabs_are_navigation_only_and_move_with_screen():
    from top_heroes_auto.vision.event_nested_tabs import reward_task_strip
    image = cv2.imread('tests/fixtures/phase8/event-reward-task-strip.png')
    result = reward_task_strip(image)
    assert result['identity'] == 'nested:daily-tasks' and result['selected'] == 'rewards'
    assert 'navigation-only' in result['evidence']
    shifted = cv2.warpAffine(image, np.float32([[1,0,-3],[0,1,25]]),(720,1280))
    moved = reward_task_strip(shifted)
    assert moved['box'] == replace(result['box'], x=result['box'].x-3,y=result['box'].y+25)
    image[430:458,382:654] = 40
    assert reward_task_strip(image) is None


@pytest.mark.parametrize('fixture', ['paid-offer-one','home-event-before-animation','android-system-ui-blocker'])
def test_unrelated_or_paid_screen_is_not_nested_task_navigation(fixture):
    from top_heroes_auto.vision.event_nested_tabs import reward_task_strip
    assert reward_task_strip(cv2.imread(f'tests/fixtures/phase8/{fixture}.png')) is None


def test_expanded_calendar_requires_grid_dates_footer_and_no_green_claim():
    from top_heroes_auto.vision.dynamic_events import body_action_boxes, calendar_timeline
    im = cv2.imread('tests/fixtures/phase8/event-expanded-calendar.png')
    def reader(_):
        return [{'text':'10/16 10/17 10/19 10/20 10/21'}]
    assert calendar_timeline(im, body_action_boxes(im), reader=reader)
    assert not calendar_timeline(im, body_action_boxes(im), reader=lambda _: [])
    broken = im.copy()
    broken[1127:1150,120:600] = 40
    assert not calendar_timeline(broken, body_action_boxes(broken), reader=reader)
    cv2.rectangle(im,(450,565),(700,626),(45,180,75),-1)
    assert not calendar_timeline(im, body_action_boxes(im), reader=reader)


def test_unique_root_can_move_between_current_frames(monkeypatch,tmp_path):
    from test_event_reacquisition import NEW, port_for

    from top_heroes_auto.automation.dynamic_events import Control
    moved = replace(NEW, x=NEW.x-110,y=NEW.y+70)
    p, frame, old, sent, _, observation = port_for(monkeypatch,tmp_path,
        controls=(Control('moved',moved,('context',),'event'),))
    observe = p.observe
    def fresh():
        result = observe()
        p.navigation_image = cv2.warpAffine(p.navigation_image,
            np.float32([[1,0,-110],[0,1,70]]),(720,1280))
        return result
    p.observe = fresh
    p.navigate(frame,old)
    assert sent == [(observation,'tap',moved.center)]


def test_locked_mission_modal_returns_to_same_list_without_retry():
    from test_expedition_visit import Port, frame

    from top_heroes_auto.automation.dynamic_events import Control
    from top_heroes_auto.automation.expedition import finish_expedition
    from top_heroes_auto.vision.models import BoundingBox
    initial = frame('available','DISPATCHABLE',mission=True)
    class Locked(Port):
        def send_mission(self,f,c):
            if c.identity.endswith('quick-send'):
                result=super().send_mission(f,c)
                self.current=replace(self.current,parent=Control('current-back',BoundingBox(1,1,20,20),
                    ('paired-modal-close',),'parent'))
                return result
            self.calls.append(('locked',f.capture))
            return dict(result='ALREADY_ATTEMPTED',journal='RESERVED',mission_dispatched=False)
        def navigate(self,f,c):
            assert c is f.parent
            self.calls.append(('close',f.capture))
    port=Locked([initial,initial])
    result=finish_expedition(port,initial)
    assert result['modal_return']=='SUCCESS'
    assert result['blocked'][0]['reason']=='ALREADY_ATTEMPTED'
    assert [c[0] for c in port.calls]==['scroll','open','locked','close']


def test_expedition_cancellation_is_not_recoverable():
    from test_expedition_visit import Port, frame

    from top_heroes_auto.automation.expedition import finish_expedition
    port=Port([])
    def stop():
        raise SafetyError('cancelled')
    port.check_cancelled=stop
    with pytest.raises(SafetyError,match='cancelled'):
        finish_expedition(port,frame('x','DISPATCHABLE'))
    assert not port.calls


def test_session_check_reuses_fresh_disk_inventory_and_rejects_replacement(rig,tmp_path):
    from top_heroes_auto.app.instance_session import InstanceSession
    manager, process, _ = rig
    session=InstanceSession(manager,tmp_path,dict(index=7,name='display',
        persistent_identity='fixture-disk-7'),tmp_path)
    process.calls.clear()
    assert session.check().index == 7
    assert len([c for c in process.calls if c[1:] == ['list2']]) == 1
    manager.identity_reader=lambda console,index: 'replacement' if index==7 else f'fixture-disk-{index}'
    with pytest.raises((ValueError,SafetyError),match='IDENTITY_CHANGED'):
        session.check()
    assert not any('input' in c for c in process.calls)


def test_current_chapter_is_exit_only_and_never_free_claim():
    from top_heroes_auto.vision.event_chapter import chapter_navigation
    from top_heroes_auto.vision.models import BoundingBox
    im=cv2.imread('tests/fixtures/phase8/contribution-chapter.png')
    back=BoundingBox(34,1209,52,47)
    proof=chapter_navigation(im,back)
    assert proof['permission']=='KNOWN_BLOCKER_EXIT' and not proof['tabs']
    assert proof['back']==back
    assert 'UNQUALIFIED' in proof['blocking_reason']
    im[1076:1108,428:607]=40
    assert chapter_navigation(im,back) is None


def test_reordered_mission_proof_uses_unique_card_not_position():
    from test_mission_repair import evidence

    from top_heroes_auto.vision.relic_expedition import dispatch_transition
    before, old=evidence('relic-dispatch-before')
    after, new=evidence('relic-dispatch-running')
    shifted=cv2.warpAffine(after,np.float32([[1,0,0],[0,1,35]]),(720,1280))
    moved=[{**r,'row':replace(r['row'],y=r['row'].y+35)} for r in new]
    proof=dispatch_transition(before,shifted,old,moved)
    assert proof and all(r['current_row']['y']==r['row'].y+35 for r in proof)
    assert not dispatch_transition(before,shifted,old+old,moved)
    assert not dispatch_transition(before,shifted,old,moved+moved)


def test_recovery_reuses_only_target_binding_not_pixels(rig,tmp_path,monkeypatch):
    from top_heroes_auto.adb.client import Target
    from top_heroes_auto.app.recovery_cli import DiagnosticRecoveryPort
    from top_heroes_auto.automation.guard import bound_snapshot
    manager,_,store=rig
    target=Target(7,'display','emulator-5568','boot','fixture-disk-7')
    seen=[]
    payload=cv2.imencode('.png',np.zeros((720,1280,3),np.uint8))[1].tobytes()
    def capture(index,snapshot,*,observed_target=None):
        seen.append(observed_target)
        return target,payload
    monkeypatch.setattr(manager,'capture_verified',capture)
    port=DiagnosticRecoveryPort(manager,bound_snapshot(store,manager.namespace,((7,'display'),),True),
                                7,'display',tmp_path)
    from top_heroes_auto.vision.image_normalizer import ScreenshotInvalid
    for step in (1,2):
        with pytest.raises(ScreenshotInvalid):
            port.observe(step)
    assert seen==[None,target]


def test_production_chapter_exposes_only_verified_exit(tmp_path, monkeypatch):
    from pathlib import Path

    from top_heroes_auto.adb.client import Target
    from top_heroes_auto.app import dynamic_event_port as module
    from top_heroes_auto.vision.fixed_rewards import EventNavigationDetector
    from top_heroes_auto.vision.screenshot import ScreenshotService

    payload=Path('tests/fixtures/phase8/contribution-chapter.png').read_bytes()
    captured=ScreenshotService(lambda _:payload).take(Target(7,'display','explicit','boot','disk'),tmp_path)
    observed=EventNavigationDetector().observe(captured)
    assert observed.page=='UNKNOWN' and observed.box('back') is not None
    port=object.__new__(module.DynamicEventPort)
    port.transport=SimpleNamespace(observe=lambda:observed)
    port.session=SimpleNamespace(target={'persistent_identity':'disk'},manager=SimpleNamespace(
        namespace='n',store=SimpleNamespace(reward_claims=lambda *a:[])),index=7)
    port.current=None
    port.entered='current-event'
    port.task_context=cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    monkeypatch.setattr(module,'read_words',lambda _:[])
    frame=port.observe()
    assert frame.page=='event:contribution-chapter'
    assert not frame.coverage_known and not frame.controls
    assert frame.parent.box==observed.box('back')
    assert 'CHAPTER_MATERIAL_ACTION_AND_CONTRIBUTION_UNQUALIFIED' in frame.blocked


@pytest.mark.parametrize('find_running', [True, False])
def test_mission_postcondition_searches_bounded_current_list_without_resending(find_running):
    from test_mission_repair import evidence

    from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
    from top_heroes_auto.automation.dynamic_events import Control, EventFrame
    from top_heroes_auto.vision.models import BoundingBox

    before,old=evidence('relic-dispatch-before')
    after,new=evidence('relic-dispatch-running')
    scroll=Control('task-list-vertical',BoundingBox(200,400,200,500),('qualified',),'scroll')
    origin=EventFrame('before',(7,'disk','explicit','boot'),'event:personal-tasks','before',
        controls=(scroll,),mission_states=({'state':'DISPATCHABLE'},),coverage_known=True)
    confirm=replace(origin,capture='confirm',page='event:relic-expedition:confirm')
    target=replace(scroll,identity='relic-expedition-confirm-send',kind='mission')
    port=object.__new__(DynamicEventPort)
    port.dispatch_origin=(origin,before,old)
    port.check_cancelled=lambda:None
    calls=[]
    count=0
    def observe():
        nonlocal count
        count+=1
        port.navigation_image,port.mission_rows=(after,new) if find_running and count>1 else (before,old)
        return replace(origin,capture=f'current-{count}',fingerprint=f'viewport-{count}')
    port.observe=observe
    port.scroll_missions=lambda frame,reverse:calls.append((frame.capture,reverse))
    proof=port._mission_postcondition(confirm,target)
    assert len(proof)==(2 if find_running else 0)
    assert len(calls)==(1 if find_running else 3)
    assert count==(3 if find_running else 4)
    assert all(not reverse for _,reverse in calls)

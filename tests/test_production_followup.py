"""Saved blockers and production boundaries; no device or gameplay access."""
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.recovery import HomeRecoveryEngine, RecoveryObservation, RecoveryStatus
from top_heroes_auto.vision.fixed_rewards import EventNavigationDetector, FixedRewardDetector
from top_heroes_auto.vision.idle_panel_recovery import idle_panel_close_point
from top_heroes_auto.vision.models import ScreenDetection, ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.relic_expedition import mission_list_surface, mission_rows
from top_heroes_auto.vision.screenshot import ScreenshotService

ROOT = Path('tests/fixtures/phase8')


def capture(image):
    return ScreenshotService(lambda _: cv2.imencode('.png', image)[1].tobytes()).take(
        Target(23, 'display-only', 'explicit', 'boot'))


def surface(image):
    return mission_list_surface(image, cv2.imread('assets/tasks/phase8/personal-task-tab.png'))


def test_saved_single_row_keeps_independent_container():
    image = cv2.imread(str(ROOT/'relic-partial-rows.png'))
    proof = surface(image)
    assert proof and 'continuous-list-rim' in proof['evidence']
    image[500:1030, 40:680] = (230, 210, 180)  # No recognizable individual card.
    assert surface(image)['box'] == proof['box']


def test_full_card_view_uses_current_panel_tab_and_footer_without_rows():
    image = cv2.imread(str(ROOT/'relic-full-card-panel.png'))
    proof = surface(image)
    assert proof and 'continuous-feature-panel-rim' in proof['evidence']
    box = proof['box']
    assert box.y > 468 and box.y+box.height < 1062
    assert box.x+box.width < 530  # All current right-column claim controls.
    for top in (505, 674, 843):
        image[top:top+135, 35:505] = (230, 210, 180)
    assert surface(image)['box'] == box
    moved = np.zeros_like(image)
    moved[8:] = image[:-8]
    assert surface(moved)['box'].y == box.y+8


def test_conflicting_inner_rims_do_not_fall_back_to_outer_panel():
    image = cv2.imread(str(ROOT/'relic-full-card-panel.png'))
    image[480:1050, 30:690] = (230, 210, 180)
    assert surface(image) is None


@pytest.mark.parametrize('region', [(0,130,350,190), (0,410,720,472),
                                   (0,500,30,1020), (690,500,720,1020),
                                   (480,1050,720,1160), (250,1050,470,1160)])
def test_full_card_panel_requires_both_sides_context_and_free_paid_footer(region):
    image = cv2.imread(str(ROOT/'relic-full-card-panel.png'))
    x,y,r,b = region
    image[y:b,x:r] = 0
    assert surface(image) is None


@pytest.mark.parametrize('region', [(0,130,350,190), (0,410,720,472),
                                   (0,500,30,1020), (690,500,720,1020),
                                   (480,1050,720,1160)])
def test_missing_page_or_container_boundary_cannot_swipe(region):
    image = cv2.imread(str(ROOT/'relic-partial-rows.png'))
    x,y,r,b = region
    image[y:b,x:r] = 0
    assert surface(image) is None


def test_small_go_fallback_is_unavailable_only_and_requires_agreement():
    image = cv2.imread(str(ROOT/'relic-partial-rows.png'))
    template = cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    def reader(crop):
        return [] if crop.shape[0] < 150 else [{'text':'Den'}]
    assert [r['state'] for r in mission_rows(image,template,reader=reader)] == ['DISPATCHABLE']
    def conflict(crop):
        return [] if crop.shape[0] < 150 else [{'text':'Den' if crop.shape[0] < 250 else 'Nhận'}]
    assert [r['state'] for r in mission_rows(image,template,reader=conflict)] == ['UNKNOWN']


def test_scroll_reacquires_container_even_with_no_recognized_rows():
    proof = surface(cv2.imread(str(ROOT/'relic-partial-rows.png')))
    control = Control('task-list-vertical',proof['box'],proof['evidence'],'scroll')
    frame = EventFrame('fresh',(23,'disk','explicit','boot'),'event:relic:personal-tasks','view',
                       (control,),coverage_known=True)
    port = object.__new__(DynamicEventPort)
    port.current = frame
    port.observe = lambda: frame
    calls=[]
    port.transport=SimpleNamespace(last=object(), dispatch=lambda *a:calls.append(a))
    port.scroll_missions(frame,reverse=True)
    assert len(calls)==1 and calls[0][1]=='swipe'
    assert port.current is None
    with pytest.raises(SafetyError,match='current'):
        port.scroll_missions(frame,reverse=True)


def test_idle_panel_authorizes_only_current_close_then_fresh_home():
    image = cv2.imread(str(ROOT/'idle-panel-full.png'))
    screen = capture(image)
    detected = RecoveryScreenDetector().detect(screen)
    assert detected.state == ScreenState.IDLE_REWARD_PANEL
    point = idle_panel_close_point(screen,detected)
    assert point[1] > image.shape[0]*.9
    home = ScreenDetection(ScreenState.GAME_HOME,1,(),'fresh-home',None,0)
    states=iter([detected,home])
    calls=[]
    port=SimpleNamespace(observe=lambda _: RecoveryObservation(next(states),None,'explicit','boot'),
        close_idle_panel=lambda _: calls.append(point) or point)
    result=HomeRecoveryEngine(sleep=lambda _:None).ensure_game_home(port)
    assert result.status==RecoveryStatus.SUCCESS and calls==[point]
    assert all('claim' not in a for a in result.actions)


def test_idle_panel_then_adventure_returns_home_without_reward_input():
    detector=RecoveryScreenDetector()
    panel=detector.detect(capture(cv2.imread(str(ROOT/'idle-panel-full.png'))))
    adventure=detector.detect(capture(cv2.imread(str(ROOT/'idle-adventure-return.png'))))
    assert adventure.state==ScreenState.IDLE_ENTRY_AVAILABLE
    home=ScreenDetection(ScreenState.GAME_HOME,1,(),'fresh-home',None,0)
    frames=iter([panel,adventure,home])
    calls=[]
    port=SimpleNamespace(observe=lambda _:RecoveryObservation(next(frames),None,'explicit','boot'),
        close_idle_panel=lambda _:calls.append('close') or (360,1221),
        back_from_idle_adventure=lambda _:calls.append('back') or (61,1223))
    result=HomeRecoveryEngine(sleep=lambda _:None).ensure_game_home(port)
    assert result.status==RecoveryStatus.SUCCESS and calls==['close','back']


def test_nested_timings_report_exclusive_time_without_double_count(monkeypatch):
    from top_heroes_auto.automation import timing
    clock=iter([0.,2.,5.,10.])
    monkeypatch.setattr(timing.time,'perf_counter',lambda:next(clock))
    timing.reset()
    with timing.measure('outer'), timing.measure('inner'):
        pass
    report=timing.snapshot()
    assert report['outer']['seconds']==10
    assert report['outer']['exclusive_seconds']==7
    assert report['inner']['exclusive_seconds']==3


@pytest.mark.parametrize('defect',['title','close','duplicate'])
def test_idle_partial_or_duplicate_close_is_not_navigation_permission(defect):
    image=cv2.imread(str(ROOT/'idle-panel-full.png'))
    if defect=='title':
        image[100:200,175:560]=0
    elif defect=='close':
        image[1183:1260,320:400]=0
    else:
        image[1183:1260,100:180]=image[1183:1260,320:400].copy()
    assert RecoveryScreenDetector().detect(capture(image)).state != ScreenState.IDLE_REWARD_PANEL


def test_saved_dragons_90_is_wait_only_loading_not_advertisement():
    detected=RecoveryScreenDetector().detect(capture(cv2.imread(str(ROOT/'loading-dragons-90.png'))))
    assert detected.state==ScreenState.GAME_LOADING
    assert {'loading-help','loading-repair','loading-progress-bar'} <= {e.anchor_id for e in detected.evidence}


@pytest.mark.parametrize('name',['relic-partial-rows','idle-panel-full','loading-dragons-90',
                                'home-new-ribbon-artwork','relic-send-confirm'])
def test_event_navigation_keeps_full_recovery_veto_and_exact_current_controls(name):
    screen=capture(cv2.imread(str(ROOT/(name+'.png'))))
    old,new=FixedRewardDetector().observe(screen),EventNavigationDetector().observe(screen)
    assert new.overlay.state==old.overlay.state
    assert new.page==('home' if old.page=='home' else 'UNKNOWN')
    for role in ('back','home-shop-entry'):
        assert new.anchors[role]==old.anchors[role]


def test_cached_template_is_immutable_and_invalidates_replacement(tmp_path):
    from top_heroes_auto.vision.template_cache import read_template
    path=tmp_path/'template.png'
    cv2.imwrite(str(path),np.full((20,20,3),32,np.uint8))
    first=read_template(path)
    assert read_template(path) is first
    with pytest.raises(ValueError):
        first[0,0]=0
    cv2.imwrite(str(path),np.full((21,20,3),128,np.uint8))
    assert read_template(path).shape != first.shape
    path.unlink()
    with pytest.raises(FileNotFoundError):
        read_template(path)


@pytest.mark.parametrize('change',['protected','disk','runtime','boot','serial'])
def test_grouped_readonly_probe_still_blocks_changed_target(rig,change):
    manager,process,store=rig
    observed,_=manager.capture_verified(7)
    def hook(args):
        if args[-1]=='get-serialno':
            if change=='protected':
                store.protect(manager.namespace,7,True)
            elif change=='disk':
                manager.identity_reader=lambda *a:'replacement'
            elif change=='runtime':
                process.listing=process.listing.replace('201,202','301,302')
            elif change=='boot':
                process.cli_boot='11111111-1111-4111-8111-111111111111'
            else:
                process.serial='emulator-6000'
    process.hook=hook
    process.calls.clear()
    with pytest.raises((SafetyError,ValueError)):
        manager.capture_verified(7,observed_target=observed)
    assert not any('screencap' in c or 'input' in c for c in process.calls)


def test_two_global_devices_are_not_indexed_ambiguity(rig):
    manager,process,_=rig
    process.devices_output+='emulator-6000\tdevice\n'
    observed,_=manager.capture_verified(7)
    assert observed.serial=='emulator-5568'
    assert not any('-s' in c and 'emulator-6000' in c for c in process.calls)

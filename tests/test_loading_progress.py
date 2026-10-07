"""Saved loading evidence and bounded capture-only progression policy."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.recovery import (
    HomeRecoveryEngine,
    RecoveryObservation,
    RecoveryResult,
    RecoveryStatus,
    RecoveryStep,
    wait_for_final_loading_progress,
)
from top_heroes_auto.vision.loading_progress import loading_progress_evidence
from top_heroes_auto.vision.models import ScreenDetection, ScreenState
from top_heroes_auto.vision.screenshot import ScreenshotService


def screen(image=None):
    data=(Path('tests/fixtures/phase8/loading-progress.png').read_bytes() if image is None
          else cv2.imencode('.png',image)[1].tobytes())
    return ScreenshotService(lambda _:data).take(Target(23,'fixture','emulator-6000','boot'))


def detection(state,evidence=()):
    return ScreenDetection(state,1,evidence,'fixture',None,0)


def test_saved_progress_qualified_without_season_or_percent_template():
    evidence=loading_progress_evidence(screen())
    assert len(evidence)==3 and all(e.score>=.98 for e in evidence)
    image=cv2.imread('tests/fixtures/phase8/loading-progress.png')
    image[320:1000]=0  # seasonal artwork has no role
    image[1105:1140,320:410]=image[1105:1140,200:290]  # percentage changes
    assert len(loading_progress_evidence(screen(image)))==3


def test_missing_or_duplicate_utility_labels_rejected():
    image=cv2.imread('tests/fixtures/phase8/loading-progress.png')
    missing=image.copy()
    missing[83:101,8:107]=0
    assert not loading_progress_evidence(screen(missing))
    duplicate=image.copy()
    duplicate[130:148,110:209]=image[83:101,8:107]
    assert not loading_progress_evidence(screen(duplicate))
    assert not loading_progress_evidence(screen(cv2.imread('tests/fixtures/phase8/home-new-ribbon-artwork.png')))


def test_final_proven_phase_progress_waits_only_then_home():
    clock=[126.0]
    engine=HomeRecoveryEngine(clock=lambda:clock[0],sleep=lambda duration:clock.__setitem__(0,clock[0]+duration))
    progress=detection(ScreenState.GAME_LOADING,loading_progress_evidence(screen()))
    final=RecoveryObservation(progress,Path('final.png'),'emulator-6000','boot')
    result=RecoveryResult(RecoveryStatus.LOADING_TIMEOUT,
        steps=[RecoveryStep(8,ScreenState.GAME_LOADING,1,None)],
        adb_target='emulator-6000',boot_id='boot',duration=120)
    observations=iter([final,replace(final,detection=detection(ScreenState.GAME_HOME))])
    port=SimpleNamespace(started=0,clock=lambda:clock[0],observe=lambda _:next(observations))
    assert wait_for_final_loading_progress(result,final,port,engine)
    assert result.status==RecoveryStatus.SUCCESS
    assert result.actions==['qualified_loading_progress','wait','wait']


def test_stalled_progress_has_one_absolute_bounded_window():
    clock=[150.0]
    engine=HomeRecoveryEngine(clock=lambda:clock[0],sleep=lambda d:clock.__setitem__(0,clock[0]+d))
    final=RecoveryObservation(detection(ScreenState.GAME_LOADING,loading_progress_evidence(screen())),
                              Path('final.png'),'emulator-6000','boot')
    result=RecoveryResult(RecoveryStatus.LOADING_TIMEOUT,
        steps=[RecoveryStep(8,ScreenState.GAME_LOADING,1,None)],adb_target='emulator-6000',boot_id='boot')
    port=SimpleNamespace(started=0,clock=lambda:clock[0],observe=lambda _:final)
    assert not wait_for_final_loading_progress(result,final,port,engine)
    assert clock[0]==180 and result.status==RecoveryStatus.LOADING_TIMEOUT
    assert not wait_for_final_loading_progress(result,final,port,engine)
    assert clock[0]==180


def test_engine_only_extends_on_a_new_proven_stage():
    progress=detection(ScreenState.GAME_LOADING,loading_progress_evidence(screen()))
    clock=[0.0]
    engine=HomeRecoveryEngine(max_duration=12,loading_timeout=9,loading_interval=5,
        clock=lambda:clock[0],sleep=lambda d:clock.__setitem__(0,clock[0]+d))
    states=iter([detection(ScreenState.GAME_LOADING),progress,progress,detection(ScreenState.GAME_HOME)])
    port=SimpleNamespace(observe=lambda _:RecoveryObservation(next(states),None,'explicit','boot'))
    result=engine.ensure_game_home(port)
    assert result.status==RecoveryStatus.SUCCESS and result.duration==15
    assert result.actions.count('qualified_loading_progress')==1
    # The same unchanged progress screen from the start proves no advancement.
    clock[0]=0
    port=SimpleNamespace(observe=lambda _:RecoveryObservation(progress,None,'explicit','boot'))
    result=engine.ensure_game_home(port)
    assert result.status!=RecoveryStatus.SUCCESS
    assert 'qualified_loading_progress' not in result.actions


def test_saved_frame_production_recovery_detector_classifies_loading():
    from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
    assert RecoveryScreenDetector().detect(screen()).state==ScreenState.GAME_LOADING


@pytest.mark.parametrize('name', ['loading-zero', 'loading-sixty'])
def test_partial_fill_is_loading_not_unknown_and_keeps_existing_wait_bound(name):
    from top_heroes_auto.vision.loading_progress import progressing_stage
    from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector

    image=cv2.imread('tests/fixtures/phase8/'+name+'.png')
    detected=RecoveryScreenDetector().detect(screen(image))
    assert progressing_stage(detected)
    assert any(e.anchor_id=='loading-progress-track-end' for e in detected.evidence)
    clock=[0.0]
    engine=HomeRecoveryEngine(max_duration=12,loading_timeout=9,loading_interval=5,
        clock=lambda:clock[0],sleep=lambda d:clock.__setitem__(0,clock[0]+d))
    port=SimpleNamespace(observe=lambda _:RecoveryObservation(detected,None,'explicit','boot'))
    result=engine.ensure_game_home(port)
    assert result.status!=RecoveryStatus.SUCCESS and clock[0]<=15
    assert 'qualified_loading_progress' not in result.actions
    assert all(a in {'qualified_loading_stage','wait'} for a in result.actions)


def test_track_rim_without_paired_labels_or_with_duplicate_is_not_loading():
    image=cv2.imread('tests/fixtures/phase8/loading-zero.png')
    missing=image.copy()
    missing[83:101,8:107]=0
    assert not loading_progress_evidence(screen(missing))
    duplicate=image.copy()
    duplicate[1108:1142,545:572]=image[1108:1142,645:672]
    assert not loading_progress_evidence(screen(duplicate))
    missing=image.copy()
    missing[1088:1180]=0
    assert not loading_progress_evidence(screen(missing))


def test_recovery_system_dialog_overrides_home_and_never_launches_or_dismisses(monkeypatch):
    from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector

    monkeypatch.setattr('top_heroes_auto.vision.recovery_detector.read_words',
        lambda _: [{'text': "System UI isn't responding Close app Wait"}])
    im=cv2.imread('tests/fixtures/phase8/android-system-ui-blocker.png')
    detected=RecoveryScreenDetector().detect(screen(im))
    assert detected.state==ScreenState.SYSTEM_BLOCKING
    clock=[0.0]
    engine=HomeRecoveryEngine(clock=lambda:clock[0],sleep=lambda _:pytest.fail('No wait on Android dialog'))
    # No input methods exist; calling any would fail this production-engine test.
    port=SimpleNamespace(observe=lambda _:RecoveryObservation(detected,None,'explicit','boot'))
    result=engine.ensure_game_home(port)
    assert result.status==RecoveryStatus.SYSTEM_BLOCKING and not result.actions
    assert 'SYSTEM_UI_NOT_RESPONDING' in result.error


def test_android_blocker_during_final_grace_is_reported_without_input():
    clock=[126.0]
    engine=HomeRecoveryEngine(clock=lambda:clock[0],sleep=lambda d:clock.__setitem__(0,clock[0]+d))
    loading=detection(ScreenState.GAME_LOADING,loading_progress_evidence(screen()))
    final=RecoveryObservation(loading,None,'explicit','boot')
    blocked=replace(final,detection=detection(ScreenState.SYSTEM_BLOCKING))
    result=RecoveryResult(RecoveryStatus.LOADING_TIMEOUT,
        steps=[RecoveryStep(8,ScreenState.GAME_LOADING,1,None)],adb_target='explicit',boot_id='boot')
    port=SimpleNamespace(started=0,clock=lambda:clock[0],observe=lambda _:blocked)
    assert not wait_for_final_loading_progress(result,final,port,engine)
    assert result.status==RecoveryStatus.SYSTEM_BLOCKING
    assert result.actions==['qualified_loading_progress','wait']

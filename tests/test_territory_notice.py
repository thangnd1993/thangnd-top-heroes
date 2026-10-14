"""Known territory announcement: paired text + close, no reward/Go permission."""
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.vision.models import ScreenDetection, ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def captured():
    payload=Path('tests/fixtures/phase8/territory-notice.png').read_bytes()
    return ScreenshotService(lambda _:payload).take(Target(26,'offline','explicit','boot'))


def test_only_stable_text_and_close_are_needed_not_timer_artwork_or_home_layout():
    screen=captured()
    detector=RecoveryScreenDetector()
    evidence=detector.detect(screen).evidence
    image=np.zeros_like(screen.normalized)
    for e in evidence:
        b=e.normalized_box
        image[b.y:b.y+b.height,b.x:b.x+b.width]=screen.normalized[b.y:b.y+b.height,b.x:b.x+b.width]
    result=detector.detect(replace(screen,normalized=image))
    assert result.state==ScreenState.EVENT_PROMO and result.confidence>=.98
    assert {e.anchor_id for e in result.evidence}=={
        'territory-notice-title','territory-notice-preparing','match-notice-close'}
    assert dismiss_overlay_bottom_left(screen,result)==(58,1203)


@pytest.mark.parametrize('role',['title','preparing','close'])
def test_duplicate_notice_control_fails_closed(role):
    screen=captured()
    detector=RecoveryScreenDetector()
    evidence=next(e for e in detector.detect(screen).evidence if e.anchor_id.endswith('-'+role))
    b=evidence.normalized_box
    image=screen.normalized.copy()
    crop=image[b.y:b.y+b.height,b.x:b.x+b.width].copy()
    # Synthetic duplicate elsewhere in the same frame; no account route/coordinate.
    dx=300 if b.x<600 else -300
    image[b.y:b.y+b.height,b.x+dx:b.x+dx+b.width]=crop
    assert detector.detect(replace(screen,normalized=image)).state!=ScreenState.EVENT_PROMO


def test_loading_conflict_cannot_authorize_notice_dismissal(monkeypatch):
    screen=captured()
    detector=RecoveryScreenDetector()
    monkeypatch.setattr(detector.detector,'detect',lambda _:
        ScreenDetection(ScreenState.GAME_LOADING,1,(),'now',None,0))
    assert detector.detect(screen).state==ScreenState.UNKNOWN


@pytest.mark.parametrize('fixture',['paid-offer-one','paid-offer-two','task-reward-list'])
def test_unrelated_purchase_or_task_page_does_not_become_territory_notice(fixture):
    image=cv2.imread(f'tests/fixtures/phase8/{fixture}.png')
    screen=ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
        Target(26,'offline','explicit','boot'))
    detected=RecoveryScreenDetector().detect(screen)
    assert not any(e.anchor_id.startswith('territory-notice') and e.matched for e in detected.evidence)

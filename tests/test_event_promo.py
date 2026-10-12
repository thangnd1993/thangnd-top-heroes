from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.vision.event_promo import event_promo_evidence
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def screen(image):
    return ScreenshotService(lambda _: cv2.imencode('.png',image)[1].tobytes()).take(
        Target(31,'fixture','explicit','boot'))


def fixture():
    return cv2.imread('tests/fixtures/phase8/dragons-event-promo.png')


@pytest.mark.parametrize('name', ['dragons-event-promo.png','dragons-event-promo-fresh.png',
    'event-promo-footer-raster.png','event-promo-covered-home.png'])
def test_current_promo_qualified_by_footer_not_artwork(name):
    image=cv2.imread(str(Path('tests/fixtures/phase8')/name))
    for im in (image, image.copy()):
        if im is not image:
            im[:1040]=0
        current=screen(im)
        result=RecoveryScreenDetector().detect(current)
        assert result.state==ScreenState.EVENT_PROMO and result.confidence>=.99
        point=dismiss_overlay_bottom_left(current,result)
        assert point==(58,1203)
        assert all(not (b.x <= point[0] <= b.x+b.width and b.y <= point[1] <= b.y+b.height)
                   for b in (e.device_box for e in result.evidence))


@pytest.mark.parametrize('kind', ['missing-go','missing-checkbox-label','duplicate','wrong-layout'])
def test_partial_duplicate_or_rearranged_footer_rejected(kind):
    image=fixture()
    if kind=='missing-go':
        image[1040:1140]=0
    elif kind=='missing-checkbox-label':
        image[1150:1210]=0
    elif kind=='duplicate':
        image[860:893,247:517]=image[1160:1193,247:517]
    else:
        image[800:833,247:517]=image[1160:1193,247:517]
        image[1150:1210]=0
    assert not event_promo_evidence(screen(image))


@pytest.mark.parametrize('name', ['loading-outlined-zero.png','home-new-ribbon-artwork.png'])
def test_loading_and_home_cannot_authorize_promo_input(name):
    image=cv2.imread(str(Path('tests/fixtures/phase8')/name))
    assert not event_promo_evidence(screen(image))


def test_two_different_render_variants_at_separate_positions_fail_closed():
    image=fixture()
    variant=cv2.imread('assets/tasks/phase8/event-promo/go-raster.png')
    image[1066:1107,70:140]=variant
    assert not event_promo_evidence(screen(image))


@pytest.mark.parametrize('state', [ScreenState.HOME_OVERLAY, ScreenState.GAME_LOADING, ScreenState.REWARD_RECEIPT])
def test_foreground_promo_compatible_only_with_known_covered_home(monkeypatch,state):
    current=screen(fixture())
    detector=RecoveryScreenDetector()
    original=detector._detect_existing(current)
    other=AnchorEvidence('other',state,.995,.98,True,device_box=BoundingBox(5,5,30,30))
    monkeypatch.setattr(detector,'_detect_existing',lambda _:replace(original,state=state,evidence=(other,)))
    result=detector.detect(current)
    assert result.state==(ScreenState.EVENT_PROMO if state==ScreenState.HOME_OVERLAY else ScreenState.UNKNOWN)
    if state==ScreenState.HOME_OVERLAY:
        assert dismiss_overlay_bottom_left(current,result)==(58,1203)

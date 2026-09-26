"""Known Shop receipt raster phase, from the original one-shot claim114 evidence."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.automation.overlays import OverlayBudget
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.fixed_rewards import FixedRewardDetector
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.screenshot import ScreenshotService


@pytest.fixture(scope='module')
def detector():
    return FixedRewardDetector()


@pytest.fixture(scope='module')
def frame():
    path = Path(__file__).parent/'fixtures/phase6_finalization/permanent-receipt-raster.png'
    raw = cv2.rotate(cv2.imread(str(path)), cv2.ROTATE_90_COUNTERCLOCKWISE)
    return ScreenshotService(lambda _:cv2.imencode('.png',raw)[1].tobytes()).take(
        Target(19,'unrelated-offline-account','explicit','fixture-boot'))


def test_current_receipt_raster_is_paired_unique_and_strict(detector,frame):
    anchor = next(a for a in detector.recovery.receipt_anchors if a.id == 'receipt-continue-dim')
    raw = unique_current_anchor(frame,anchor)
    assert .97 < raw.score < .98 and not raw.matched
    detection = detector.recovery.detect(frame)
    assert detection.state == ScreenState.REWARD_RECEIPT
    assert detection.confidence >= .98
    assert {e.anchor_id for e in detection.evidence} == {'receipt-title','receipt-continue-dim'}
    # A receipt is permission to dismiss only; it is not positive consumption proof.
    assert detector.availability(detector.observe(frame),'shop-permanent-privilege-gift')[0] == 'UNKNOWN'


@pytest.mark.parametrize('mutation',['missing_title','missing_continue','duplicate_continue','conflicting_continue'])
def test_partial_duplicate_and_conflicting_receipts_remain_unknown(detector,frame,mutation):
    detection = detector.recovery.detect(frame)
    boxes = {e.anchor_id:e.normalized_box for e in detection.evidence}
    pixels = frame.normalized.copy()
    box = boxes['receipt-title' if mutation == 'missing_title' else 'receipt-continue-dim']
    if mutation.startswith('missing'):
        pixels[box.y:box.y+box.height,box.x:box.x+box.width] = 0
    else:
        patch = pixels[box.y:box.y+box.height,box.x:box.x+box.width].copy()
        if mutation == 'conflicting_continue':
            anchor = next(a for a in detector.recovery.receipt_anchors if a.id == 'receipt-continue')
            patch = cv2.imread(str(anchor.template))
        h,w = patch.shape[:2]
        pixels[50:50+h,400:400+w] = patch
    assert detector.recovery.detect(replace(frame,normalized=pixels)).state == ScreenState.UNKNOWN


def test_current_receipt_search_uses_shifted_frame_boxes(detector,frame):
    matrix = cv2.getRotationMatrix2D((0,0),0,1)
    matrix[:,2] = 40,-25
    pixels = cv2.warpAffine(frame.normalized,matrix,frame.normalized_size)
    moved = detector.recovery.detect(replace(frame,normalized=pixels))
    original = detector.recovery.detect(frame)
    assert moved.state == ScreenState.REWARD_RECEIPT
    for a,b in zip(original.evidence,moved.evidence,strict=True):
        assert b.normalized_box.x == a.normalized_box.x+40
        assert b.normalized_box.y == a.normalized_box.y-25


def test_raster_receipt_dismisses_once_and_requires_fresh_observation(detector,frame,monkeypatch):
    port = FixedRewardPort.__new__(FixedRewardPort)
    port.detector = detector
    port.overlay_budget = OverlayBudget()
    before = detector.observe(frame)
    after = SimpleNamespace(page='shop-permanent',overlay=SimpleNamespace(state=ScreenState.UNKNOWN))
    events = []
    port.dispatch = lambda observation,action,point: events.append((observation is before,action,point))
    port.observe = lambda: (events.append('fresh'),after)[1]
    monkeypatch.setattr('top_heroes_auto.app.fixed_reward_port.time.sleep',lambda _:None)
    assert port.settle(before) is after
    assert events == [(True,'tap',(58,1203)),'fresh']

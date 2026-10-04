"""Real large-layout receipt is safe to dismiss, never sufficient to verify a claim."""
from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def captured():
    payload = (Path(__file__).parent/'fixtures/phase8/large-receipt.png').read_bytes()
    return ScreenshotService(lambda _: payload).take(Target(5, 'fixture', 'explicit', 'boot'))


def test_large_receipt_requires_unique_title_and_continue_in_safe_layout():
    screen = captured()
    detection = RecoveryScreenDetector().detect(screen)
    assert detection.state == ScreenState.REWARD_RECEIPT
    assert detection.confidence >= .96
    assert {e.anchor_id for e in detection.evidence} == {'large-receipt-title', 'large-receipt-continue'}
    assert dismiss_overlay_bottom_left(screen, detection) == (58, 1203)


@pytest.mark.parametrize('anchor', ['large-receipt-title', 'large-receipt-continue'])
def test_partial_receipt_is_not_dismissible(anchor):
    screen = captured()
    detector = RecoveryScreenDetector()
    evidence = next(e for e in detector.detect(screen).evidence if e.anchor_id == anchor)
    box = evidence.normalized_box
    damaged = screen.normalized.copy()
    damaged[box.y:box.y+box.height, box.x:box.x+box.width] = 0
    assert detector.detect(replace(screen, normalized=damaged)).state != ScreenState.REWARD_RECEIPT


def test_duplicate_title_fails_closed():
    screen = captured()
    detector = RecoveryScreenDetector()
    title = next(e for e in detector.detect(screen).evidence if e.anchor_id == 'large-receipt-title')
    b = title.normalized_box
    image = screen.normalized.copy()
    image[200:200+b.height, 300:300+b.width] = image[b.y:b.y+b.height, b.x:b.x+b.width].copy()
    assert detector.detect(replace(screen, normalized=image)).state != ScreenState.REWARD_RECEIPT


def test_moved_continue_is_not_a_safe_receipt_layout():
    screen = captured()
    detector = RecoveryScreenDetector()
    e = next(e for e in detector.detect(screen).evidence if e.anchor_id == 'large-receipt-continue')
    b = e.normalized_box
    image = screen.normalized.copy()
    crop = image[b.y:b.y+b.height, b.x:b.x+b.width].copy()
    image[b.y:b.y+b.height, b.x:b.x+b.width] = 0
    image[b.y:b.y+b.height, 500:500+b.width] = crop
    assert detector.detect(replace(screen, normalized=image)).state != ScreenState.REWARD_RECEIPT


def test_task_page_does_not_become_receipt():
    image = cv2.imread(str(Path(__file__).parent/'fixtures/phase8/task-reward-list.png'))
    screen = ScreenshotService(lambda _: cv2.imencode('.png', image)[1].tobytes()).take(
        Target(5, 'fixture', 'explicit', 'boot'))
    assert RecoveryScreenDetector().detect(screen).state != ScreenState.REWARD_RECEIPT


def test_known_match_notice_qualifies_dismissal_without_go_permission():
    payload = (Path(__file__).parent/'fixtures/phase8/match-notice.png').read_bytes()
    screen = ScreenshotService(lambda _: payload).take(Target(3, 'fixture', 'explicit', 'boot'))
    detector = RecoveryScreenDetector()
    detection = detector.detect(screen)
    assert detection.state == ScreenState.EVENT_PROMO
    assert detection.confidence >= .98
    assert dismiss_overlay_bottom_left(screen, detection) == (58, 1203)
    assert all('go' not in e.anchor_id for e in detection.evidence)
    for evidence in detection.evidence:
        b = evidence.normalized_box
        image = screen.normalized.copy()
        image[b.y:b.y+b.height, b.x:b.x+b.width] = 0
        assert detector.detect(replace(screen, normalized=image)).state != ScreenState.EVENT_PROMO

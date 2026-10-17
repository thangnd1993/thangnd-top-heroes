"""Actual startup blockers from normal packaged app run12; offline only."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.automation.recovery import HomeRecoveryEngine, RecoveryObservation, RecoveryStatus
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


@pytest.fixture(scope='module')
def detector():
    return RecoveryScreenDetector()


def capture(name):
    data = Path(f'tests/fixtures/recovery_notices/{name}.png').read_bytes()
    return ScreenshotService(lambda _: data).take(Target(99, 'offline', 'explicit', 'boot'))


@pytest.mark.parametrize('name', ['assistance-a', 'assistance-b', 'notice-battle-a', 'notice-battle-b'])
def test_current_account_variants_have_unique_notice_evidence(detector, name):
    screen = capture(name)
    result = detector.detect(screen)
    assistance = name.startswith('assistance')
    assert result.state == (ScreenState.LOGIN_ASSISTANCE if assistance else ScreenState.EVENT_PROMO)
    assert result.confidence >= .98
    assert len(result.evidence) == 3
    point = dismiss_overlay_bottom_left(screen, result)
    if assistance:
        close = next(e.device_box for e in result.evidence if e.anchor_id == 'match-notice-close')
        assert point == close.center  # Neither Thanks nor settings receives input.
        assert point[1] > screen.device_size[1] * .85
    else:
        assert point == (58, 1203)


@pytest.mark.parametrize('missing', ['title', 'banner', 'close'])
def test_partial_assistance_is_not_actionable(detector, missing):
    screen = capture('assistance-a')
    result = detector.detect(screen)
    evidence = next(e for e in result.evidence if e.anchor_id.endswith('-' + missing))
    b = evidence.normalized_box
    image = screen.normalized.copy()
    image[b.y:b.y+b.height, b.x:b.x+b.width] = 0
    assert detector.detect(replace(screen, normalized=image)).state != ScreenState.LOGIN_ASSISTANCE
    with pytest.raises(SafetyError):
        dismiss_overlay_bottom_left(screen, replace(result, evidence=tuple(
            e for e in result.evidence if e is not evidence)))


@pytest.mark.parametrize('role', ['title', 'banner', 'close'])
def test_duplicate_assistance_anchor_fails_closed(detector, role):
    screen = capture('assistance-a')
    result = detector.detect(screen)
    image = np.zeros_like(screen.normalized)
    for e in result.evidence:
        b = e.normalized_box
        image[b.y:b.y+b.height,b.x:b.x+b.width] = screen.normalized[b.y:b.y+b.height,b.x:b.x+b.width]
    e = next(e for e in result.evidence if e.anchor_id.endswith('-' + role))
    b = e.normalized_box
    dx = 220 if b.x < 800 else -220
    image[b.y:b.y+b.height,b.x+dx:b.x+dx+b.width] = screen.normalized[b.y:b.y+b.height,b.x:b.x+b.width]
    assert detector.detect(replace(screen, normalized=image)).state != ScreenState.LOGIN_ASSISTANCE


def test_conflicting_territory_phase_labels_fail_closed(detector):
    screen = capture('notice-battle-a')
    anchor = next(a for a in detector.territory_notice_anchors if a.id.endswith('-preparing'))
    # Reuse the qualified preparation glyphs from the previous real variant.
    data = Path('tests/fixtures/phase8/territory-notice.png').read_bytes()
    prior = ScreenshotService(lambda _:data).take(Target(98,'offline','explicit','boot'))
    box = unique_current_anchor(prior, anchor).normalized_box
    image = screen.normalized.copy()
    crop = prior.normalized[box.y:box.y+box.height,box.x:box.x+box.width]
    image[20:20+box.height,500:500+box.width] = crop
    assert detector.detect(replace(screen, normalized=image)).state == ScreenState.UNKNOWN


def test_assistance_loading_conflict_is_not_dismissed(detector, monkeypatch):
    screen = capture('assistance-a')
    detected = detector.detect(screen)
    monkeypatch.setattr(detector.detector, 'detect', lambda _:replace(
        detected, state=ScreenState.GAME_LOADING, evidence=tuple(
            e for e in detected.evidence if e.anchor_id != 'match-notice-close')))
    assert detector.detect(screen).state != ScreenState.LOGIN_ASSISTANCE


def test_stable_notice_dismissal_requires_fresh_home_and_is_bounded(detector):
    screen = capture('assistance-a')
    notice = detector.detect(screen)
    home = replace(notice, state=ScreenState.GAME_HOME, evidence=())

    class Port:
        def __init__(self, persistent=False):
            self.seen = 0
            self.taps = []
            self.persistent = persistent

        def observe(self, step):
            self.seen += 1
            state = notice if self.persistent or self.seen <= 2 else home
            return RecoveryObservation(state, Path(f'{step}.png'), 'explicit', 'boot')

        def dismiss_overlay(self, observation):
            point = dismiss_overlay_bottom_left(screen, observation.detection)
            self.taps.append(point)
            return point

    port = Port()
    engine = HomeRecoveryEngine(sleep=lambda _:None)
    assert engine.ensure_game_home(port).status == RecoveryStatus.SUCCESS
    assert len(port.taps) == 1 and port.seen == 3
    stuck = Port(persistent=True)
    assert engine.ensure_game_home(stuck).status == RecoveryStatus.PROMO_BLOCKING
    assert len(stuck.taps) == 2

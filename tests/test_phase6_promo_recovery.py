import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.phase6_promo_recovery import (
    GuardedPromoRecovery,
    PromoRecoveryFrame,
    PromoRecoveryStatus,
)
from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import CapturedScreen, ScreenDetection, ScreenState
from top_heroes_auto.vision.resources import template_folder

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "tasks" / "phase6" / "promo"
EVIDENCE_ROOT = Path(
    os.environ.get(
        "THA_PHASE6_EVIDENCE_ROOT",
        r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\vision\5-Emmmmm",
    )
)
TARGET = Target(2, "5-Emmmmm", "emulator-5558", "boot-2")


def _anchor():
    anchors = load_anchors(ASSETS)
    assert len(anchors) == 1
    return anchors[0]


def _screen(target, image, source):
    return CapturedScreen(
        target.index,
        target.name,
        target.serial,
        target.boot_id,
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        source_image=Path(source),
    )


def _frame(tmp_path, target=TARGET, *, popup=False, name="frame"):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    if popup:
        template = cv2.imread(str(_anchor().template), cv2.IMREAD_COLOR)
        assert template is not None
        height, width = template.shape[:2]
        image[355 : 355 + height, 1090 : 1090 + width] = template
    return PromoRecoveryFrame(target, _screen(target, image, tmp_path / f"{name}.png"))


def _home_detector(screen):
    stem = screen.source_image.stem if screen.source_image is not None else ""
    is_home = "home" in stem
    state = ScreenState.UNKNOWN if "unknown" in stem else ScreenState.GAME_LOADING
    return ScreenDetection(
        ScreenState.GAME_HOME if is_home else state,
        0.99,
        (),
        screen.timestamp,
        screen.source_image,
        0.1,
    )


class Port:
    def __init__(self, frames, *, back_error=None):
        self.frames = iter(frames)
        self.back_error = back_error
        self.back_calls = []

    def observe(self, tag):
        return next(self.frames)

    def back(self, frame):
        self.back_calls.append(frame.capture_id)
        if self.back_error:
            raise self.back_error


def _recovery(port):
    return GuardedPromoRecovery(
        port,
        _anchor(),
        _home_detector,
        destination_wait_seconds=0,
    )


def test_known_promo_dispatches_one_back_and_requires_fresh_home(tmp_path):
    port = Port(
        [
            _frame(tmp_path, popup=True, name="promo-before"),
            _frame(tmp_path, name="home-after"),
        ]
    )
    result = _recovery(port).run(2, "5-Emmmmm")

    assert result.status == PromoRecoveryStatus.SUCCESS
    assert result.attempted
    assert result.actions == ["keyevent:4"]
    assert len(port.back_calls) == 1
    assert result.before["anchor"]["anchor"] == "promo-stranger-title"
    assert result.after["detection"]["state"] == ScreenState.GAME_HOME.value


def test_missing_promo_is_not_present_and_sends_no_input(tmp_path):
    port = Port([_frame(tmp_path, name="home-before")])
    result = _recovery(port).run(2, "5-Emmmmm")

    assert result.status == PromoRecoveryStatus.NOT_PRESENT
    assert not result.attempted
    assert port.back_calls == []


def test_ambiguous_promo_never_dispatches(tmp_path):
    first = _frame(tmp_path, popup=True, name="promo-before")
    image = first.screen.normalized.copy()
    template = cv2.imread(str(_anchor().template), cv2.IMREAD_COLOR)
    assert template is not None
    height, width = template.shape[:2]
    image[355 : 355 + height, 1000 : 1000 + width] = template
    duplicate = PromoRecoveryFrame(TARGET, _screen(TARGET, image, tmp_path / "promo-duplicate.png"))

    port = Port([duplicate])
    result = _recovery(port).run(2, "5-Emmmmm")

    assert result.status == PromoRecoveryStatus.BLOCKED
    assert not result.attempted
    assert port.back_calls == []


def test_cancel_before_back_never_dispatches(tmp_path):
    port = Port([_frame(tmp_path, popup=True, name="promo-before")])
    result = _recovery(port).run(2, "5-Emmmmm", cancelled=lambda: True)

    assert result.status == PromoRecoveryStatus.CANCELLED
    assert not result.attempted
    assert port.back_calls == []


def test_boot_change_after_back_is_identity_failure_without_retry(tmp_path):
    changed = Target(2, "5-Emmmmm", TARGET.serial, "boot-changed")
    port = Port(
        [
            _frame(tmp_path, popup=True, name="promo-before"),
            _frame(tmp_path, changed, name="home-after"),
        ]
    )
    result = _recovery(port).run(2, "5-Emmmmm")

    assert result.status == PromoRecoveryStatus.IDENTITY_MISMATCH
    assert result.attempted
    assert len(port.back_calls) == 1


def test_back_dispatch_uncertain_is_terminal_and_not_retried(tmp_path):
    port = Port(
        [_frame(tmp_path, popup=True, name="promo-before")],
        back_error=RuntimeError("transport uncertain"),
    )
    result = _recovery(port).run(2, "5-Emmmmm")

    assert result.status == PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN
    assert result.attempted
    assert len(port.back_calls) == 1


def test_unknown_destination_stops_without_a_second_back(tmp_path):
    port = Port(
        [
            _frame(tmp_path, popup=True, name="promo-before"),
            _frame(tmp_path, name="unknown-after"),
            _frame(tmp_path, name="home-after-unused"),
        ]
    )
    result = _recovery(port).run(2, "5-Emmmmm")

    assert result.status == PromoRecoveryStatus.DESTINATION_UNVERIFIED
    assert result.attempted
    assert len(port.back_calls) == 1
    assert len(result.captures) == 2


def test_persistent_loading_is_bounded_without_input_retry(tmp_path):
    port = Port(
        [
            _frame(tmp_path, popup=True, name="promo-before"),
            _frame(tmp_path, name="loading-1"),
            _frame(tmp_path, name="loading-2"),
            _frame(tmp_path, name="loading-3"),
        ]
    )
    result = _recovery(port).run(2, "5-Emmmmm")

    assert result.status == PromoRecoveryStatus.DESTINATION_UNVERIFIED
    assert len(port.back_calls) == 1
    assert len(result.captures) == 4


def test_wrong_clone_never_dispatches(tmp_path):
    wrong = Target(2, "other", TARGET.serial, TARGET.boot_id)
    port = Port([_frame(tmp_path, wrong, popup=True, name="wrong-clone")])
    result = _recovery(port).run(2, "5-Emmmmm")

    assert result.status == PromoRecoveryStatus.IDENTITY_MISMATCH
    assert port.back_calls == []


@pytest.mark.skipif(not EVIDENCE_ROOT.exists(), reason="index-2 diagnostic captures are not available")
def test_saved_index2_promo_matches_and_rejects_other_surfaces():
    anchor = _anchor()

    def saved(stem):
        path = EVIDENCE_ROOT / f"{stem}.png"
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert image is not None
        return _screen(TARGET, image, path)

    positive = saved("20260921-173703-800199Z-phase6-20260922-promo-before")
    evidence = unique_current_anchor(positive, anchor)
    assert evidence.matched
    assert evidence.score >= anchor.threshold

    # The capture called fresh-home-before still contains the same popup; it
    # is therefore explicitly not treated as a Home negative.  The actual
    # post-Back Home frame is the valid semantic negative.
    overlay_home = saved("20260921-173502-952419Z-phase6-20260922-fresh-home-before")
    assert unique_current_anchor(overlay_home, anchor).matched

    # The same-account post-Back capture is independently recognized as Home;
    # it is the destination postcondition, not a prior coordinate authority.
    post_back = saved("20260921-173707-993954Z-phase6-20260922-promo-after")
    detection = ScreenDetector.from_folder(template_folder()).detect(post_back)
    assert detection.state == ScreenState.GAME_HOME
    assert detection.confidence >= 0.9

    for stem in (
        "20260921-173707-993954Z-phase6-20260922-promo-after",
        "20260921-173754-456023Z-phase6-20260922-shop-entry-before",
        "20260921-174127-641081Z-phase6-20260922-vip-current-before",
        "20260921-173850-589371Z-phase6-20260922-daily-info-after",
    ):
        assert not unique_current_anchor(saved(stem), anchor).matched, stem

    # No same-account loading capture was recorded in the index-2 survey.  A
    # synthetic loading-like blank frame remains a negative, never a live
    # source or action authority.
    loading = _screen(TARGET, np.zeros((720, 1280, 3), dtype=np.uint8), "loading-negative.png")
    assert not unique_current_anchor(loading, anchor).matched

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.recovery import (
    HomeRecoveryEngine,
    RecoveryObservation,
    RecoveryStatus,
)
from top_heroes_auto.vision.idle_detector import IdleRewardDetector
from top_heroes_auto.vision.models import CapturedScreen, ScreenDetection, ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService

FIXTURES = Path(__file__).parent / "fixtures" / "recovery_fleet"
QUEEN_LOADING = FIXTURES / "queen-con-loading-14-google-play.png"


def read_image(path: Path):
    return cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)


def screen_with(patch, position=(0, 0)):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    left, top = position
    height, width = patch.shape[:2]
    image[top : top + height, left : left + width] = patch
    return CapturedScreen(
        11,
        "offline-fixture",
        "explicit-serial",
        "boot-id",
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        device_size=(720, 1280),
        rotated_from_portrait=True,
    )


def saved_queen_loading_screen():
    return saved_recovery_screen(QUEEN_LOADING)


def saved_recovery_screen(path):
    payload = path.read_bytes()
    target = Target(3, "fixture", "emulator-fixture", "fixture-boot")
    return ScreenshotService(lambda serial: payload).take(target)


@pytest.mark.parametrize(
    ("fixture", "state", "positions"),
    [
        ("index11-loading.png", ScreenState.PROMO_LOADING, [(0, 0), (180, 80)]),
        ("index11-login-popup.png", ScreenState.POPUP_GENERIC, [(0, 0), (600, 120)]),
    ],
)
def test_index11_saved_states_are_detected_from_current_unique_anchors(fixture, state, positions):
    patch = read_image(FIXTURES / fixture)
    detector = RecoveryScreenDetector()
    for position in positions:
        result = detector.detect(screen_with(patch, position))
        assert result.state == state
        assert result.confidence >= 0.96
        assert result.evidence and all(item.matched for item in result.evidence)


def test_stranger_things_promo_title_without_loading_caption_stays_unknown():
    promo_title = read_image(
        Path(__file__).parents[1] / "assets" / "tasks" / "phase6" / "promo" / "promo-stranger-title.png"
    )
    result = RecoveryScreenDetector().detect(screen_with(promo_title, (400, 180)))

    assert result.state == ScreenState.UNKNOWN


def test_queen_saved_14_percent_splash_is_loading_from_unique_current_title():
    result = RecoveryScreenDetector().detect(saved_queen_loading_screen())

    assert result.state == ScreenState.PROMO_LOADING
    assert result.confidence == pytest.approx(0.962074, abs=0.002)
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.anchor_id == "stranger-loading-splash-title"
    assert evidence.matched
    assert evidence.normalized_box is not None
    assert evidence.device_box is not None


@pytest.mark.parametrize(
    "fixture",
    ["queen-con-loading-14-google-play.png", "queen-con-loading-65.png"],
)
def test_queen_loading_title_does_not_depend_on_progress_percentage(fixture):
    screen = saved_recovery_screen(FIXTURES / fixture)
    changed = screen.normalized.copy()
    # Replace the live-frame percentage area while leaving the loading artwork intact.
    changed[320:390, 130:185] = np.median(changed[310:318, 130:185], axis=0).astype(np.uint8)
    assert not np.array_equal(changed, screen.normalized)

    result = RecoveryScreenDetector().detect(replace(screen, normalized=changed))

    assert result.state == ScreenState.PROMO_LOADING
    assert result.evidence[0].matched


@pytest.mark.parametrize(
    "fixture",
    ["queen-con-loading-14-google-play.png", "queen-con-loading-65.png"],
)
def test_queen_promo_loading_variants_are_recognized_at_strict_confidence(fixture):
    screen = saved_recovery_screen(FIXTURES / fixture)
    result = RecoveryScreenDetector().detect(screen)

    assert result.state == ScreenState.PROMO_LOADING
    assert result.confidence >= 0.96
    assert len(result.evidence) == 1
    assert result.evidence[0].anchor_id == "stranger-loading-splash-title"
    assert result.evidence[0].matched
    assert result.evidence[0].normalized_box is not None


def test_unrelated_loading_is_not_misclassified_as_stranger_promo():
    logo = read_image(Path(__file__).parents[1] / "assets" / "templates" / "loading" / "hhgames-logo.png")
    result = RecoveryScreenDetector().detect(screen_with(logo, (420, 220)))

    assert result.state == ScreenState.GAME_LOADING
    assert all(item.anchor_id != "stranger-loading-splash-title" for item in result.evidence)


def test_promo_card_requires_both_unique_title_and_cta_and_idle_stays_unknown():
    assets = Path(__file__).parents[1] / "assets" / "tasks" / "phase6" / "promo"
    title = read_image(assets / "promo-stranger-title.png")
    cta = read_image(
        Path(__file__).parents[1] / "assets" / "tasks" / "phase6" / "promo-recovery" / "promo-stranger-cta.png"
    )
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[85 : 85 + title.shape[0], 900 : 900 + title.shape[1]] = title
    image[430 : 430 + cta.shape[0], 110 : 110 + cta.shape[1]] = cta
    screen = CapturedScreen(
        3,
        "fixture",
        "explicit-serial",
        "fixture-boot",
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        device_size=(1280, 720),
    )

    result = RecoveryScreenDetector().detect(screen)
    idle = IdleRewardDetector().detect(screen)

    assert result.state == ScreenState.EVENT_PROMO
    assert result.confidence >= 0.96
    assert {item.anchor_id for item in result.evidence} == {
        "promo-stranger-title",
        "promo-stranger-cta",
    }
    boxes = {item.anchor_id: item.normalized_box for item in result.evidence}
    assert (boxes["promo-stranger-title"].x, boxes["promo-stranger-title"].y) == (900, 85)
    assert (boxes["promo-stranger-cta"].x, boxes["promo-stranger-cta"].y) == (110, 430)
    assert idle.state == ScreenState.UNKNOWN

    shifted = cv2.warpAffine(
        image,
        np.float32([[1, 0, 35], [0, 1, -20]]),
        (image.shape[1], image.shape[0]),
    )
    shifted_screen = replace(screen, original=shifted, normalized=shifted)
    moved = RecoveryScreenDetector().detect(shifted_screen)

    assert moved.state == ScreenState.EVENT_PROMO
    moved_boxes = {item.anchor_id: item.normalized_box for item in moved.evidence}
    assert (moved_boxes["promo-stranger-title"].x, moved_boxes["promo-stranger-title"].y) == (935, 65)
    assert (moved_boxes["promo-stranger-cta"].x, moved_boxes["promo-stranger-cta"].y) == (145, 410)


def test_side_panel_like_cta_without_promo_title_is_not_a_known_promo():
    cta = read_image(
        Path(__file__).parents[1]
        / "assets"
        / "tasks"
        / "phase6"
        / "promo-recovery"
        / "promo-stranger-cta.png"
    )
    result = RecoveryScreenDetector().detect(screen_with(cta, (110, 430)))

    assert result.state != ScreenState.EVENT_PROMO
    assert result.state != ScreenState.PROMO_LOADING


def test_duplicate_promo_cta_fails_closed_as_ambiguous():
    assets = Path(__file__).parents[1] / "assets" / "tasks" / "phase6" / "promo"
    title = read_image(assets / "promo-stranger-title.png")
    cta = read_image(
        Path(__file__).parents[1] / "assets" / "tasks" / "phase6" / "promo-recovery" / "promo-stranger-cta.png"
    )
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[85 : 85 + title.shape[0], 900 : 900 + title.shape[1]] = title
    image[350 : 350 + cta.shape[0], 110 : 110 + cta.shape[1]] = cta
    image[350 : 350 + cta.shape[0], 700 : 700 + cta.shape[1]] = cta
    screen = CapturedScreen(
        3,
        "fixture",
        "explicit-serial",
        "fixture-boot",
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        device_size=(1280, 720),
    )

    assert RecoveryScreenDetector().detect(screen).state != ScreenState.EVENT_PROMO


def test_conflicting_screen_evidence_prevents_promo_classification():
    assets = Path(__file__).parents[1] / "assets" / "tasks" / "phase6" / "promo"
    title = read_image(assets / "promo-stranger-title.png")
    cta = read_image(
        Path(__file__).parents[1] / "assets" / "tasks" / "phase6" / "promo-recovery" / "promo-stranger-cta.png"
    )
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    image[85 : 85 + title.shape[0], 900 : 900 + title.shape[1]] = title
    image[430 : 430 + cta.shape[0], 110 : 110 + cta.shape[1]] = cta
    screen = CapturedScreen(
        3,
        "fixture",
        "explicit-serial",
        "fixture-boot",
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        device_size=(1280, 720),
    )
    detector = RecoveryScreenDetector()
    detector.detector.detect = lambda _screen: detected(ScreenState.GAME_HOME)

    result = detector.detect(screen)

    assert result.state == ScreenState.UNKNOWN
    assert result.confidence == 0


def test_queen_loading_title_bbox_is_found_at_its_current_frame_position():
    screen = saved_queen_loading_screen()
    initial = RecoveryScreenDetector().detect(screen)
    shifted = screen.normalized.copy()
    transform = np.float32([[1, 0, 40], [0, 1, -20]])
    shifted = cv2.warpAffine(shifted, transform, (shifted.shape[1], shifted.shape[0]))

    result = RecoveryScreenDetector().detect(replace(screen, normalized=shifted))

    assert result.state == ScreenState.PROMO_LOADING
    assert result.evidence[0].normalized_box.x == initial.evidence[0].normalized_box.x + 40
    assert result.evidence[0].normalized_box.y == initial.evidence[0].normalized_box.y - 20


def test_google_play_notice_during_loading_only_waits_and_never_dispatches_ui_input():
    detector = RecoveryScreenDetector()
    loading = detector.detect(saved_queen_loading_screen())
    assert loading.state == ScreenState.PROMO_LOADING

    port = SequencePort(
        [detected(ScreenState.ANDROID_HOME), loading, detected(ScreenState.GAME_HOME)]
    )
    clock = Clock()
    result = HomeRecoveryEngine(
        loading_timeout=90,
        loading_interval=5,
        action_settle=0,
        clock=clock,
        sleep=clock.sleep,
    ).ensure_game_home(port)

    assert result.status == RecoveryStatus.SUCCESS
    assert result.actions == ["launch_game", "wait"]
    assert port.launches == 1


def test_blurred_queen_loading_frame_below_anchor_confidence_stays_unknown():
    screen = saved_queen_loading_screen()
    blurred = cv2.GaussianBlur(screen.normalized, (0, 0), sigmaX=5)

    result = RecoveryScreenDetector().detect(replace(screen, normalized=blurred))

    assert result.state == ScreenState.UNKNOWN


def test_conflicting_loading_and_popup_evidence_remains_unknown():
    loading = read_image(FIXTURES / "index11-loading.png")
    popup = read_image(FIXTURES / "index11-login-popup.png")
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    canvas[0 : loading.shape[0], 0 : loading.shape[1]] = loading
    canvas[: popup.shape[0], 870:1280] = popup
    screen = CapturedScreen(
        11,
        "offline-fixture",
        "explicit-serial",
        "boot-id",
        canvas,
        canvas,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        device_size=(720, 1280),
        rotated_from_portrait=True,
    )

    assert RecoveryScreenDetector().detect(screen).state == ScreenState.UNKNOWN


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class SequencePort:
    def __init__(self, detections):
        self.detections = list(detections)
        self.launches = 0

    def observe(self, step):
        detection = self.detections.pop(0)
        return RecoveryObservation(detection, Path(f"{step}.png"), "emulator-5576")

    def launch_game(self):
        self.launches += 1


def detected(state):
    return ScreenDetection(
        state,
        1.0,
        (),
        datetime.now(timezone.utc).isoformat(),
        None,
        1.0,
    )


def test_index11_loading_then_known_popup_fails_closed_without_waiting_to_timeout():
    detector = RecoveryScreenDetector()
    loading = detector.detect(screen_with(read_image(FIXTURES / "index11-loading.png")))
    popup = detector.detect(screen_with(read_image(FIXTURES / "index11-login-popup.png")))
    port = SequencePort(
        [detected(ScreenState.ANDROID_HOME), loading, detected(ScreenState.UNKNOWN), popup]
    )
    clock = Clock()
    result = HomeRecoveryEngine(
        loading_timeout=90,
        loading_interval=5,
        action_settle=0,
        clock=clock,
        sleep=clock.sleep,
    ).ensure_game_home(port)

    assert result.status == RecoveryStatus.ACTION_FAILED
    assert "POPUP_GENERIC" in result.error
    assert result.actions == ["launch_game", "wait", "wait"]
    assert port.launches == 1
    assert clock.value == 10

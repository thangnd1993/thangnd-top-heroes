from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.automation.recovery import (
    HomeRecoveryEngine,
    RecoveryObservation,
    RecoveryStatus,
)
from top_heroes_auto.vision.models import CapturedScreen, ScreenDetection, ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector

FIXTURES = Path(__file__).parent / "fixtures" / "recovery_fleet"


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


@pytest.mark.parametrize(
    ("fixture", "state", "positions"),
    [
        ("index11-loading.png", ScreenState.GAME_LOADING, [(0, 0), (180, 80)]),
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

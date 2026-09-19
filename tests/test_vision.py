from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.vision_cli import _capture
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.debug import write_overlay
from top_heroes_auto.vision.detector import ScreenDetector
from top_heroes_auto.vision.image_normalizer import ImageNormalizer, ScreenshotInvalid
from top_heroes_auto.vision.models import BoundingBox, NormalizedRect, ScreenState, VisualAnchor
from top_heroes_auto.vision.screenshot import ScreenshotService
from top_heroes_auto.vision.stability import screen_stability

BOOT_ID = "ce068632-fc3e-4090-a8d7-ae8d9fe353f5"


def patterned(width=320, height=180, seed=7):
    rng = np.random.default_rng(seed)
    image = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    cv2.rectangle(image, (40, 30), (110, 90), (20, 220, 80), -1)
    cv2.circle(image, (240, 110), 25, (250, 40, 30), -1)
    return image


def png(image) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def screen(image=None, capture=None):
    target = Target(7, "Farm-007", "emulator-5568", BOOT_ID)
    image = patterned() if image is None else image
    return ScreenshotService(capture or (lambda _: png(image))).take(target)


def anchor(tmp_path: Path, state, name, image, region=(0, 0, 1, 1), threshold=0.95, required=True):
    path = tmp_path / f"{name}.png"
    assert cv2.imwrite(str(path), image)
    return VisualAnchor(name, state, path, NormalizedRect(*region), threshold, required)


def test_valid_screenshot_decode_and_normalize():
    captured = screen()
    assert captured.original_size == (320, 180)
    assert captured.normalized_size == (1280, 720)
    assert captured.normalized.shape[:2] == (720, 1280)


@pytest.mark.parametrize("payload", [b"not-png", b"\x89PNG\r\n\x1a\nbroken"])
def test_corrupt_screenshot_is_rejected(payload):
    with pytest.raises(ScreenshotInvalid, match="SCREENSHOT_INVALID"):
        ImageNormalizer().decode(payload)


def test_blank_screenshot_is_rejected():
    with pytest.raises(ScreenshotInvalid, match="blank"):
        ImageNormalizer().decode(png(np.zeros((180, 320, 3), dtype=np.uint8)))


def test_portrait_is_normalized_to_landscape():
    image = patterned(180, 320)
    decoded = ImageNormalizer().decode(png(image))
    assert decoded.shape[1] > decoded.shape[0]


def test_coordinate_conversion_round_trip():
    captured = screen(patterned(640, 360))
    box = BoundingBox(128, 72, 256, 144)
    assert box.normalized(1280, 720) == NormalizedRect(0.1, 0.1, 0.3, 0.3)
    assert captured.to_device_box(box) == BoundingBox(64, 36, 128, 72)


def test_exact_target_screenshot_dispatch(rig):
    manager, process, _ = rig
    target, payload = manager.capture_verified(7)
    assert target.serial == "emulator-5568"
    assert payload.startswith(b"\x89PNG")
    capture = next(call for call in process.calls if "screencap" in call)
    assert capture[1:3] == ["-s", "emulator-5568"]


def test_template_match_positive_and_negative(tmp_path):
    captured = screen()
    template = captured.normalized[120:260, 120:440]
    positive = anchor(tmp_path, ScreenState.GAME_HOME, "home", template)
    negative = anchor(tmp_path, ScreenState.GAME_LOADING, "loading", patterned(320, 140, 99))
    assert ScreenDetector((positive,)).detect(captured).state == ScreenState.GAME_HOME
    assert ScreenDetector((negative,)).detect(captured).state == ScreenState.UNKNOWN


def test_multiple_anchor_aggregation_and_threshold_boundary(tmp_path):
    captured = screen()
    first = anchor(tmp_path, ScreenState.GAME_HOME, "first", captured.normalized[100:180, 100:240], threshold=1.0)
    second = anchor(tmp_path, ScreenState.GAME_HOME, "second", captured.normalized[400:520, 800:980])
    result = ScreenDetector((first, second)).detect(captured)
    assert result.state == ScreenState.GAME_HOME
    assert len(result.evidence) == 2


def test_conflicting_state_evidence_fails_closed(tmp_path):
    captured = screen()
    template = captured.normalized[200:320, 300:500]
    home = anchor(tmp_path, ScreenState.GAME_HOME, "home", template)
    loading = anchor(tmp_path, ScreenState.GAME_LOADING, "loading", template)
    result = ScreenDetector((home, loading)).detect(captured)
    assert result.state == ScreenState.UNKNOWN
    assert len(result.evidence) == 2


def test_one_capture_can_evaluate_all_states(tmp_path):
    calls = []

    def capture(serial):
        calls.append(serial)
        return png(patterned())

    captured = screen(capture=capture)
    template = captured.normalized[100:220, 100:300]
    detector = ScreenDetector((anchor(tmp_path, ScreenState.ANDROID_HOME, "android", template),))
    detector.detect(captured)
    assert calls == ["emulator-5568"]


def test_debug_overlay_and_stability(tmp_path):
    captured = screen()
    template = captured.normalized[100:220, 100:300]
    result = ScreenDetector((anchor(tmp_path, ScreenState.ANDROID_HOME, "android", template),)).detect(captured)
    output = write_overlay(captured, result, tmp_path / "debug" / "overlay.png")
    assert output.is_file()
    stable, difference = screen_stability(captured, captured)
    assert stable and difference == 0


def test_protected_target_rejected_before_capture(rig, tmp_path):
    manager, process, _ = rig
    process.listing = process.listing.replace("Main-Thang", "Queen")
    manager.refresh()
    with pytest.raises(SafetyError, match="selected and not Protected"):
        _capture(manager, tmp_path, 0, "Queen", "protected")

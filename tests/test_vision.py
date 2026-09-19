from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.vision_cli import _capture, _write_detection_report
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.debug import write_overlay
from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.image_normalizer import ImageNormalizer, ScreenshotInvalid
from top_heroes_auto.vision.models import BoundingBox, NormalizedRect, ScreenState, VisualAnchor
from top_heroes_auto.vision.resources import idle_reward_template_folder
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


def test_screenshot_persists_to_unicode_folder(tmp_path):
    target = Target(4, "3-Chíp", "emulator-5562", BOOT_ID)
    captured = ScreenshotService(lambda _: png(patterned())).take(target, tmp_path / "3-Chíp", "trang-chủ")
    assert captured.source_image.is_file()
    assert captured.source_image.with_suffix(".json").is_file()


def test_detection_report_persists_unicode_as_utf8(tmp_path):
    target = Target(4, "3-Chíp", "emulator-5562", BOOT_ID)
    captured = ScreenshotService(lambda _: png(patterned())).take(target, tmp_path / "3-Chíp")
    report = _write_detection_report(captured, {"instance": {"name": "3-Chíp"}, "state": "UNKNOWN"})
    assert "3-Chíp" in report.read_text(encoding="utf-8")


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


def test_portrait_coordinate_conversion_returns_device_portrait_box():
    captured = screen(patterned(720, 1280))
    assert captured.rotated_from_portrait
    assert captured.device_size == (720, 1280)
    mapped = captured.to_device_box(BoundingBox(735, 410, 120, 115))
    assert mapped == BoundingBox(410, 425, 115, 120)


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


def test_alternative_variants_for_same_state_do_not_require_each_other(tmp_path):
    captured = screen()
    matching = anchor(
        tmp_path,
        ScreenState.GAME_LOADING,
        "landscape",
        captured.normalized[200:320, 300:500],
    )
    missing = VisualAnchor(
        "rotated",
        ScreenState.GAME_LOADING,
        tmp_path / "missing.png",
        NormalizedRect(0, 0, 1, 1),
        0.95,
        True,
        1.0,
        "rotated",
    )
    assert ScreenDetector((matching,)).detect(captured).state == ScreenState.GAME_LOADING
    # A second required variant is an alternative, not an additional AND precondition.
    negative_image = patterned(100, 60, 99)
    assert cv2.imwrite(str(missing.template), negative_image)
    assert ScreenDetector((matching, missing)).detect(captured).state == ScreenState.GAME_LOADING


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
    output = write_overlay(captured, result, tmp_path / "debug-Chíp" / "overlay.png")
    assert output.is_file()
    stable, difference = screen_stability(captured, captured)
    assert stable and difference == 0


def test_protected_target_rejected_before_capture(rig, tmp_path):
    manager, process, _ = rig
    process.listing = process.listing.replace("Main-Thang", "Queen")
    manager.refresh()
    with pytest.raises(SafetyError, match="selected and not Protected"):
        _capture(manager, tmp_path, 0, "Queen", "protected")


def test_repository_templates_load_and_have_unique_ids():
    anchors = load_anchors(Path("assets/templates"))
    assert {anchor.state for anchor in anchors} >= {
        ScreenState.ANDROID_HOME,
        ScreenState.GAME_LOADING,
        ScreenState.GAME_HOME,
    }
    assert len({anchor.id for anchor in anchors}) == len(anchors)
    assert all(anchor.template.is_file() for anchor in anchors)


def test_repository_templates_fail_closed_on_unrelated_image():
    result = ScreenDetector.from_folder(Path("assets/templates")).detect(screen(patterned(seed=2026)))
    assert result.state == ScreenState.UNKNOWN


@pytest.mark.parametrize(
    ("expected", "placements", "action_anchor", "device_center"),
    [
        (ScreenState.GAME_HOME, [("idle-adventure-portal", 770, 420)], "idle-adventure-portal", (465, 470)),
        (
            ScreenState.IDLE_ENTRY_AVAILABLE,
            [("idle-entry-available", 230, 10)],
            "idle-entry-available",
            (87, 957),
        ),
        (
            ScreenState.IDLE_ENTRY_AVAILABLE,
            [("idle-entry-available-open", 230, 10)],
            "idle-entry-available-open",
            (87, 957),
        ),
        (
            ScreenState.IDLE_ENTRY_NOT_AVAILABLE,
            [("idle-entry-not-available", 230, 10)],
            "idle-entry-not-available",
            (87, 957),
        ),
        (
            ScreenState.IDLE_REWARD_CLAIMABLE,
            [("idle-claim-button", 315, 240), ("idle-full-bar", 875, 200), ("idle-title", 1080, 175)],
            "idle-claim-button",
            (362, 915),
        ),
        (
            ScreenState.IDLE_REWARD_CLAIMED,
            [("idle-claimed-banner", 900, 60), ("idle-claimed-continue", 225, 230)],
            "idle-claimed-continue",
            (360, 1015),
        ),
    ],
)
def test_versioned_idle_reward_anchors_and_portrait_mapping(
    expected, placements, action_anchor, device_center
):
    folder = idle_reward_template_folder()
    canvas = patterned(1280, 720, seed=91)
    for name, x, y in placements:
        template = cv2.imread(str(folder / f"{name}.png"))
        height, width = template.shape[:2]
        canvas[y : y + height, x : x + width] = template
    portrait = cv2.rotate(canvas, cv2.ROTATE_90_COUNTERCLOCKWISE)
    captured = screen(portrait)
    result = ScreenDetector.from_folder(folder).detect(captured)
    assert result.state == expected
    if action_anchor:
        evidence = next(item for item in result.evidence if item.anchor_id == action_anchor)
        assert evidence.device_box.center == device_center


def test_idle_reward_templates_have_no_stamina_action_anchor():
    anchors = load_anchors(idle_reward_template_folder())
    assert len(anchors) == 9
    assert not any("hourglass" in anchor.id or "stamina" in anchor.id for anchor in anchors)
    assert not any(anchor.state == ScreenState.IDLE_REWARD_NOT_CLAIMABLE for anchor in anchors)


@pytest.mark.parametrize(
    ("filename", "expected", "action_anchor", "device_center"),
    [
        ("phase5-final-home.png", ScreenState.GAME_HOME, "idle-adventure-portal", (465, 470)),
        (
            "phase5-adventure-portal-result.png",
            ScreenState.IDLE_ENTRY_AVAILABLE,
            "idle-entry-available",
            (87, 957),
        ),
        (
            "phase5-adventure-second-run.png",
            ScreenState.IDLE_ENTRY_NOT_AVAILABLE,
            "idle-entry-not-available",
            (87, 957),
        ),
        (
            "phase5-idle-reward-screen.png",
            ScreenState.IDLE_REWARD_CLAIMABLE,
            "idle-claim-button",
            (362, 915),
        ),
        ("phase5-not-claimable.png", ScreenState.UNKNOWN, None, None),
        (
            "phase5-post-claim.png",
            ScreenState.IDLE_REWARD_CLAIMED,
            "idle-claimed-continue",
            (360, 1015),
        ),
    ],
)
def test_real_idle_reward_fixtures(filename, expected, action_anchor, device_center):
    fixture = Path("artifacts") / filename
    if not fixture.is_file():
        pytest.skip("Real-account full screenshot intentionally remains outside Git.")
    target = Target(4, "3-Chíp", "emulator-5562", BOOT_ID)
    captured = ScreenshotService(lambda _: fixture.read_bytes()).take(target)
    result = ScreenDetector.from_folder(idle_reward_template_folder()).detect(captured)
    assert result.state == expected
    if action_anchor:
        evidence = next(item for item in result.evidence if item.anchor_id == action_anchor)
        assert evidence.device_box.center == device_center

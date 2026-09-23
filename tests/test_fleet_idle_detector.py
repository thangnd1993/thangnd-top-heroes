from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.vision.idle_detector import IdleRewardDetector
from top_heroes_auto.vision.models import CapturedScreen, ScreenState
from top_heroes_auto.vision.resources import idle_reward_template_folder

FIXTURES = Path(__file__).parent / "fixtures" / "idle_reward_fleet"


def read_image(path: Path):
    return cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)


def screen_with(patches):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    for patch, (left, top) in patches:
        height, width = patch.shape[:2]
        image[top : top + height, left : left + width] = patch
    return CapturedScreen(
        3,
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
    ("index", "position"),
    [(3, (192, 0)), (8, (500, 250)), (10, (850, 450))],
)
def test_saved_fleet_unknown_frames_detect_unique_idle_chest_at_current_location(index, position):
    crop = read_image(FIXTURES / f"unknown-entry-{index}.png")
    result = IdleRewardDetector().detect(screen_with([(crop, position)]))

    assert result.state == ScreenState.IDLE_ENTRY_AVAILABLE
    assert result.confidence >= 0.95
    anchor = next(item for item in result.evidence if item.anchor_id == "idle-entry-available")
    assert anchor.matched
    # The chest is at local offset (103, 15) in each saved legacy-ROI crop.
    assert (anchor.normalized_box.x, anchor.normalized_box.y) == (position[0] + 103, position[1] + 15)


def test_saved_pooh_side_panel_does_not_hide_idle_entry():
    entry = read_image(FIXTURES / "unknown-entry-9.png")
    panel = read_image(FIXTURES / "pooh-auto-mode-overlay.png")
    result = IdleRewardDetector().detect(screen_with([(entry, (100, 0)), (panel, (900, 80))]))

    assert result.state == ScreenState.IDLE_ENTRY_AVAILABLE
    assert result.confidence >= 0.95
    assert any(item.anchor_id == "idle-entry-available" and item.matched for item in result.evidence)


def test_duplicate_chests_fail_closed_instead_of_choosing_one():
    crop = read_image(FIXTURES / "unknown-entry-3.png")
    result = IdleRewardDetector().detect(screen_with([(crop, (30, 20)), (crop, (800, 350))]))

    assert result.state == ScreenState.UNKNOWN
    anchor = next(item for item in result.evidence if item.anchor_id == "idle-entry-available")
    assert not anchor.matched


def test_low_confidence_chest_core_remains_unknown():
    crop = read_image(FIXTURES / "unknown-entry-3.png")
    # Replace most of the chest-core area with a neutral field, leaving only weak fragments.
    crop[15:130, 103:213] = (110, 110, 110)
    result = IdleRewardDetector().detect(screen_with([(crop, (300, 200))]))

    assert result.state == ScreenState.UNKNOWN


def test_conflicting_available_and_post_claim_chest_evidence_remains_unknown():
    available = read_image(idle_reward_template_folder() / "idle-entry-available-core.png")
    unavailable = read_image(idle_reward_template_folder() / "idle-entry-not-available-core.png")
    result = IdleRewardDetector().detect(
        screen_with([(available, (200, 100)), (unavailable, (750, 350))])
    )

    assert result.state == ScreenState.UNKNOWN

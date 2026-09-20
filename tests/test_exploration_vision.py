from dataclasses import replace

import cv2
import numpy as np

from top_heroes_auto.vision.exploration import content_fingerprint, red_dot_candidates, unique_current_anchor
from top_heroes_auto.vision.models import CapturedScreen, NormalizedRect, ScreenState, VisualAnchor


def captured(image):
    height, width = image.shape[:2]
    return CapturedScreen(4, "3-Chíp", "explicit", "boot", image, image, (width, height), (width, height), (1, 1))


def test_unique_anchor_moves_between_account_screens_and_rejects_duplicates(tmp_path):
    template = np.random.default_rng(8).integers(0, 255, (16, 18, 3), dtype=np.uint8)
    path = tmp_path / "anchor.png"
    path.write_bytes(cv2.imencode(".png", template)[1].tobytes())
    anchor = VisualAnchor("tavern", ScreenState.GAME_HOME, path, NormalizedRect(0, 0, 1, 1), 0.95)
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    image[10:26, 20:38] = template
    first = unique_current_anchor(captured(image), anchor)
    assert first.matched and first.device_box.center == (29, 18)
    moved = np.zeros_like(image)
    moved[70:86, 160:178] = template
    second = unique_current_anchor(replace(captured(moved), index=5, name="other"), anchor)
    assert second.matched and second.device_box.center == (169, 78)
    moved[10:26, 20:38] = template
    assert not unique_current_anchor(captured(moved), anchor).matched


def test_fingerprint_ignores_only_explicitly_excluded_regions():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    region = (NormalizedRect(0, 0.2, 1, 1),)
    before = content_fingerprint(captured(image), region)
    image[:10] = 255  # clock/header outside inspected content
    assert content_fingerprint(captured(image), region) == before
    image[50:60] = 255
    assert content_fingerprint(captured(image), region) != before


def test_red_dots_return_candidates_not_permissions():
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.circle(image, (70, 30), 8, (0, 0, 255), -1)
    dots = red_dot_candidates(captured(image), NormalizedRect(0, 0, 1, 1))
    assert len(dots) == 1
    assert dots[0].center == (70, 30)

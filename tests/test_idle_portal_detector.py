from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from test_idle_reward import detection

from top_heroes_auto.vision.idle_detector import IdleRewardDetector
from top_heroes_auto.vision.models import CapturedScreen, ScreenState
from top_heroes_auto.vision.resources import idle_reward_template_folder


def frame(*positions):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    core = cv2.imread(str(idle_reward_template_folder() / 'idle-adventure-portal-core.png'))
    for x, y in positions:
        image[y:y + 40, x:x + 40] = core
    return CapturedScreen(2, 'account', 'explicit', 'boot', image, image, (1280, 720),
                          (1280, 720), (1, 1), device_size=(720, 1280), rotated_from_portrait=True)


@pytest.mark.parametrize('position', [(170, 20), (1000, 500)])
def test_portal_moves_outside_old_account_roi(position):
    detector = IdleRewardDetector()
    detector.home_detector = SimpleNamespace(detect=lambda s: detection(ScreenState.GAME_HOME))
    screen = frame(position)
    result = detector.detect(screen)
    assert result.state == ScreenState.GAME_HOME
    anchor = next(e for e in result.evidence if e.anchor_id == 'idle-adventure-portal')
    assert anchor.matched and anchor.threshold == 0.9
    assert (anchor.normalized_box.x, anchor.normalized_box.y) == position
    assert anchor.device_box == screen.to_device_box(anchor.normalized_box)


@pytest.mark.parametrize('positions', [[], [(170, 20), (1000, 500)]])
def test_absent_or_duplicate_portals_do_not_choose_a_target(positions):
    detector = IdleRewardDetector()
    detector.home_detector = SimpleNamespace(detect=lambda s: detection(ScreenState.GAME_HOME))
    assert detector.detect(frame(*positions)).state == ScreenState.UNKNOWN


def test_portal_pixels_without_independent_home_are_blocked():
    detector = IdleRewardDetector()
    detector.home_detector = SimpleNamespace(detect=lambda s: detection(ScreenState.UNKNOWN))
    assert detector.detect(frame((170, 20))).state == ScreenState.UNKNOWN


def test_new_frame_does_not_reuse_previous_portal():
    detector = IdleRewardDetector()
    detector.home_detector = SimpleNamespace(detect=lambda s: detection(ScreenState.GAME_HOME))
    before = frame((170, 20))
    assert detector.detect(before).state == ScreenState.GAME_HOME
    assert detector.detect(replace(frame(), boot_id='new-boot')).state == ScreenState.UNKNOWN


def test_core_asset_is_exact_crop_not_painted_or_new_guessed_template():
    folder = idle_reward_template_folder()
    original = cv2.imread(str(folder / 'idle-adventure-portal.png'))
    core = cv2.imread(str(folder / 'idle-adventure-portal-core.png'))
    assert np.array_equal(original[27:67, 22:62], core)

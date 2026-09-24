from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.free_reward_tasks import _load_profile_details
from top_heroes_auto.app.vip_gift import gift_profile, gift_state
from top_heroes_auto.automation.phase6_visual import FrameRewardAdapter
from top_heroes_auto.vision.screenshot import ScreenshotService

ROOT = Path(__file__).resolve().parents[1]


def frame(name):
    payload = (ROOT / 'tests/fixtures/phase6_vip' / name).read_bytes()
    return ScreenshotService(lambda _: payload).take(Target(8, 'Soup', 'fixture', 'boot'))


def classify(captured):
    profile, _ = _load_profile_details('vip-reward')
    return gift_state(FrameRewardAdapter(gift_profile(profile)).observe(captured).screen)


def test_real_claimable_and_unavailable_states():
    assert classify(frame('index2-vip-claimable.png')) == 'FREE_CLAIMABLE'
    assert classify(frame('soup-vip-unavailable.png')) == 'NOT_AVAILABLE'


def test_weak_or_occluded_gift_unknown():
    captured = frame('soup-vip-unavailable.png')
    for patch in (np.zeros((117, 110, 3), dtype=np.uint8),
                  cv2.GaussianBlur(captured.normalized[598:715, 1028:1138], (21, 21), 8)):
        changed = captured.normalized.copy()
        changed[598:715, 1028:1138] = patch
        assert classify(replace(captured, normalized=changed)) == 'UNKNOWN'


def test_unrelated_badge_does_not_authorize_gift():
    captured = frame('soup-vip-unavailable.png')
    changed = captured.normalized.copy()
    badge = cv2.imread(str(ROOT / 'assets/tasks/phase6/vip-gift/gift-badge.png'))
    h, w = badge.shape[:2]
    changed[300:300+h, 700:700+w] = badge
    assert classify(replace(captured, normalized=changed)) != 'FREE_CLAIMABLE'


def test_duplicate_unavailable_gifts_unknown_and_search_not_account_coordinates():
    captured = frame('soup-vip-unavailable.png')
    changed = captured.normalized.copy()
    icon = changed[598:715, 1028:1138].copy()
    changed[400:517, 700:810] = icon
    assert classify(replace(captured, normalized=changed)) == 'UNKNOWN'
    changed[598:715, 1028:1138] = 0
    assert classify(replace(captured, normalized=changed)) == 'NOT_AVAILABLE'

"""Only stable Vip lettering authorizes navigation; no level/account routes."""
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.screenshot import ScreenshotService

ROOT = Path(__file__).resolve().parents[1]


def anchor():
    return next(a for a in load_anchors(ROOT/'assets/tasks/phase6/home') if a.id == 'home-vip-entry')


@pytest.mark.parametrize('name', ['index2-home.png', 'vip7-home.png'])
def test_same_stable_entry_on_different_levels(name):
    path = ROOT/'tests/fixtures/phase6_vip'/name
    screen = ScreenshotService(lambda _: path.read_bytes()).take(Target(73, 'irrelevant', 'emulator-5700', 'fixture'))
    result = unique_current_anchor(screen, anchor())
    assert result.matched and result.score >= .99
    assert result.device_box is not None


@pytest.mark.parametrize('count,expected', [(0, False), (1, True), (2, False)])
def test_moved_unique_lettering_and_duplicates(count, expected):
    a = anchor()
    image = np.zeros((720, 1280, 3), np.uint8)
    template = cv2.imread(str(a.template))
    h, w = template.shape[:2]
    for x, y in [(1120, 70), (1180, 150)][:count]:
        image[y:y+h, x:x+w] = template
    path = ROOT/'tests/fixtures/phase6_vip/vip7-home.png'
    screen = ScreenshotService(lambda _: path.read_bytes()).take(Target(41, 'other', 'emulator-5702', 'fixture'))
    result = unique_current_anchor(replace(screen, normalized=image), a)
    assert result.matched is expected


def test_vip_page_and_rewards_do_not_become_home_entry():
    path = ROOT/'tests/fixtures/phase6_vip/index2-vip-claimable.png'
    screen = ScreenshotService(lambda _: path.read_bytes()).take(Target(41, 'other', 'emulator-5702', 'fixture'))
    assert not unique_current_anchor(screen, anchor()).matched

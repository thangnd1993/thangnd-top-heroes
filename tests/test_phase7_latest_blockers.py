"""Second resume evidence; offline images only, no live account access."""
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.vision.fixed_rewards import FixedRewardDetector, claim_geometry
from top_heroes_auto.vision.guild_mail import GuildMailDetector, portrait
from top_heroes_auto.vision.screenshot import ScreenshotService

ROOT = Path(__file__).parent/'fixtures/phase7_resume'


def capture(name):
    return ScreenshotService(lambda _: (ROOT/f'{name}.png').read_bytes()).take(
        Target(43,'offline-random','explicit-fixture','boot'))


@pytest.mark.parametrize('name,count', [('mail-five',5),('mail-six',6)])
def test_numbered_mail_badge_is_complete_and_control_bound_without_ocr(name,count):
    detector = GuildMailDetector(number_reader=lambda *a,**kw:None)
    frame = detector.observe(capture(name))
    tabs = detector.mail_tabs(frame)
    assert tabs['guild']['count'] == count
    assert not tabs['guild']['selected']
    assert tabs['reports']['count'] is None  # Never read5 from57 or6 from60.
    assert tabs['war']['count'] == tabs['collection']['count'] == 0
    assert detector.availability(frame,'mail-guild').state == 'UNKNOWN'


@pytest.mark.skipif(sys.platform != 'win32',reason='Windows local OCR regression')
def test_white_digits_splitting_red_fill_still_require_agreed_count():
    detector = GuildMailDetector()
    frame = detector.observe(capture('member-59'))
    view = detector.availability(frame,'guild-gifts-member')
    assert view.state == 'AVAILABLE' and view.remaining == 59
    assert view.box == detector.control(frame,'gifts-quick','green')


def test_split_badge_with_conflicting_readings_is_unknown():
    readings = iter([59,9,59])
    detector = GuildMailDetector(number_reader=lambda *a,**kw:next(readings))
    frame = detector.observe(capture('member-59'))
    assert detector.availability(frame,'guild-gifts-member').state == 'UNKNOWN'


@pytest.mark.parametrize('name,reward', [
    ('shop-permanent-tilted','shop-permanent-privilege-gift'),
    ('shop-monthly-owned','shop-monthly-privilege-gift'),
])
def test_shop_animation_uses_current_paired_core_and_safe_geometry(name,reward):
    detector = FixedRewardDetector()
    frame = detector.observe(capture(name))
    state,core,badge = detector.availability(frame,reward)
    assert state == 'AVAILABLE' and core.score >= .98 and badge.score >= .98
    assert detector.selected_tab(frame,frame.page.removeprefix('shop-'))
    geometry = claim_geometry(frame,reward,core)
    assert geometry['inside_allowed'] and geometry['outside_forbidden']
    assert geometry['tap'] == list(core.device_box.center)
    # Remove only attention. The free core alone cannot authorize navigation/claim.
    image = frame.captured.normalized.copy()
    b = badge.normalized_box
    image[b.y-5:b.y+b.height+5,b.x-5:b.x+b.width+5] = 0
    changed = detector.observe(replace(frame.captured,normalized=image))
    assert detector.availability(changed,reward)[0] == 'UNKNOWN'


def test_monthly_video_without_selected_tab_never_authorizes_entry():
    detector = FixedRewardDetector()
    frame = detector.observe(capture('shop-monthly-owned'))
    image = portrait(frame.captured).copy()
    image[1170:,:] = 100
    captured = ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
        Target(81,'different-layout','explicit-fixture','boot'))
    assert detector.availability(detector.observe(captured),'shop-monthly-privilege-gift')[0] == 'UNKNOWN'


def test_large_pose_proposal_is_bounded_even_when_region_does_not_shrink(tmp_path):
    from top_heroes_auto.vision.gift_detector import unique_pose_anchor
    from top_heroes_auto.vision.models import NormalizedRect, ScreenState, VisualAnchor

    rng = np.random.default_rng(17)
    template = rng.integers(0,255,(150,150,3),dtype=np.uint8)
    image = np.zeros((720,1280,3),np.uint8)
    image[200:350,500:650] = template
    path = tmp_path/'core.png'
    path.write_bytes(cv2.imencode('.png',template)[1].tobytes())
    frame = ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
        Target(43,'offline-random','explicit-fixture','boot'))
    anchor = VisualAnchor('large-core',ScreenState.FREE_REWARD_PAGE,path,NormalizedRect(0,0,1,1),.98)
    found = unique_pose_anchor(frame,anchor)
    assert found.matched and found.score > .99
    assert abs(found.normalized_box.center[0]-575) <= 2


def test_duplicate_monthly_attention_cannot_rescue_animated_gift():
    detector = FixedRewardDetector()
    original = capture('shop-monthly-owned')
    frame = detector.observe(original)
    image = original.normalized.copy()
    box = frame.anchors['monthly-attention'].normalized_box
    patch = image[box.y-2:box.y+box.height+2,box.x-2:box.x+box.width+2].copy()
    image[box.y-2:box.y+box.height+2,box.x-80:box.x-80+patch.shape[1]] = patch
    changed = detector.observe(replace(original,normalized=image))
    assert detector.availability(changed,'shop-monthly-privilege-gift')[0] == 'UNKNOWN'

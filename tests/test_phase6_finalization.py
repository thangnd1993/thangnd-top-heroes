"""Real failed frames and strict seven-reward acceptance regressions, offline."""
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.vision.fixed_rewards import FixedRewardDetector, claim_geometry
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.screenshot import ScreenshotService

FIXTURES = Path(__file__).parent/'fixtures/phase6_finalization'


def captured(name, transform=lambda image:image):
    image = cv2.imread(str(FIXTURES/f'{name}.png'))
    payload = cv2.imencode('.png',transform(image))[1].tobytes()
    return ScreenshotService(lambda _:payload).take(Target(71,'different-account','explicit','boot'))


@pytest.fixture(scope='module')
def detector():
    return FixedRewardDetector()


def test_real_home_overlay_stable_hud_interiors(detector):
    c = captured('covered-home')
    result = detector.recovery.detect(c)
    assert result.state == ScreenState.HOME_OVERLAY
    assert result.confidence >= .98
    assert dismiss_overlay_bottom_left(c,result) == (58,1203)
    # Event artwork contributes no identity: replace it with unrelated sharp UI.
    def other_art(image):
        image[220:1050,100:540] = np.random.default_rng(73).integers(0,256,(830,440,3),dtype=np.uint8)
        return image
    assert detector.recovery.detect(captured('covered-home',other_art)).state == ScreenState.HOME_OVERLAY


def test_missing_home_corner_does_not_allow_generic_back(detector):
    def obscure(image):
        image[1090:,550:] = 0
        return image
    result = detector.recovery.detect(captured('covered-home',obscure))
    assert result.state == ScreenState.UNKNOWN


@pytest.mark.parametrize('route',['permanent','monthly'])
def test_real_clipped_selected_tab_and_rocking_gift(detector,route):
    obs = detector.observe(captured(f'{route}-clipped-tab'))
    assert obs.page == f'shop-{route}'
    assert detector.selected_tab(obs,route)
    reward = f'shop-{route}-privilege-gift'
    state,core,_ = detector.availability(obs,reward)
    assert state == 'AVAILABLE'
    geometry = claim_geometry(obs,reward,core)
    assert geometry['inside_allowed'] and geometry['outside_forbidden']
    assert geometry['confidence'] >= .96
    assert detector.availability(obs,'shop-weekly-card-gift')[0] == 'UNKNOWN'


@pytest.mark.parametrize('route',['permanent','monthly'])
def test_selected_other_tab_cannot_authorize_reward(detector,route):
    def deselect(image):
        image[1170:1195,125:405] = (65,100,140)
        return image
    obs = detector.observe(captured(f'{route}-clipped-tab',deselect))
    assert not detector.selected_tab(obs,route)
    assert detector.availability(obs,f'shop-{route}-privilege-gift')[0] == 'UNKNOWN'


@pytest.mark.parametrize('shift',[-50,-85])
def test_current_gift_bbox_moves_with_image_not_account(detector,shift):
    def move(image):
        gift=image[120:300,550:705].copy()
        image[120:300,450:710] = (80,110,130)
        image[120:300,550+shift:705+shift] = gift
        return image
    original=detector.observe(captured('monthly-clipped-tab'))
    moved=detector.observe(captured('monthly-clipped-tab',move))
    a=detector.availability(original,'shop-monthly-privilege-gift')
    b=detector.availability(moved,'shop-monthly-privilege-gift')
    assert a[0]==b[0]=='AVAILABLE'
    assert abs(b[1].device_box.x-a[1].device_box.x-shift)<=1


def test_duplicate_attention_does_not_rescue_pose_match(detector):
    def duplicate(image):
        image[140:166,460:483] = image[135:161,666:689].copy()
        return image
    obs=detector.observe(captured('monthly-clipped-tab',duplicate))
    assert detector.availability(obs,'shop-monthly-privilege-gift')[0]=='UNKNOWN'


def test_missing_or_changed_content_cannot_be_selected(detector):
    obs=detector.observe(captured('permanent-clipped-tab'))
    assert not detector.selected_tab(replace(obs,page='shop-weekly'),'monthly')



@pytest.mark.parametrize('route',['permanent','monthly'])
def test_new_selected_icon_variant_qualifies_current_page(detector,route):
    obs=detector.observe(captured(f'{route}-selected-icon'))
    assert detector.selected_tab(obs,route)
    state,core,_=detector.availability(obs,f'shop-{route}-privilege-gift')
    assert state=='AVAILABLE' and core.score>=.96
    assert claim_geometry(obs,f'shop-{route}-privilege-gift',core)['outside_forbidden']
    assert not detector.selected_tab(replace(obs,page='UNKNOWN'),route)


@pytest.mark.parametrize('route',['permanent','monthly'])
def test_duplicate_selected_icon_variant_fails_closed(detector,route):
    def duplicate(image):
        x=387 if route=='permanent' else 180
        image[1201:1244,490:490+(41 if route=='permanent' else 34)]=image[1201:1244,x:x+(41 if route=='permanent' else 34)]
        return image
    obs=detector.observe(captured(f'{route}-selected-icon',duplicate))
    assert not detector.selected_tab(obs,route)
    assert detector.availability(obs,f'shop-{route}-privilege-gift')[0]=='UNKNOWN'


def test_subpixel_alignment_uses_strict_current_icon_and_rejects_duplicate(detector):
    from top_heroes_auto.vision.fixed_rewards import portrait_region
    from top_heroes_auto.vision.subpixel import unique_subpixel_anchor
    anchor=replace(detector.anchors['permanent-tab'],expected_region=portrait_region(0,.9,1,1))
    c=captured('permanent-selected-icon')
    found=unique_subpixel_anchor(c,anchor)
    assert found.matched and found.score>=.98
    def duplicate(image):
        image[1201:1244,540:581]=image[1201:1244,387:428]
        return image
    assert not unique_subpixel_anchor(captured('permanent-selected-icon',duplicate),anchor).matched
    assert not unique_subpixel_anchor(captured('covered-home'),anchor).matched


def test_subpixel_does_not_supply_coordinates_without_a_match(detector):
    from top_heroes_auto.vision.fixed_rewards import portrait_region
    from top_heroes_auto.vision.subpixel import unique_subpixel_anchor
    anchor=replace(detector.anchors['monthly-tab'],expected_region=portrait_region(0,.9,1,1))
    result=unique_subpixel_anchor(captured('covered-home'),anchor)
    assert not result.matched and result.device_box is None


def test_notice_overlapping_tab_edge_uses_current_unique_card_variant(detector):
    obs=detector.observe(captured('monthly-tab-notice'))
    assert obs.page=='shop-weekly'  # Scroll does not select the newly visible tab.
    tab=obs.box('monthly-tab')
    assert tab is not None and tab.x>obs.box('back').x+obs.box('back').width
    assert obs.anchors['monthly-tab'].score>=.98
    assert detector.availability(obs,'shop-monthly-privilege-gift')[0]=='UNKNOWN'


def test_real_scrolled_tabs_subpixel_render_still_requires_page_selection(detector):
    obs=detector.observe(captured('scrolled-tabs'))
    assert obs.page=='shop-weekly'
    for route in ('permanent','monthly'):
        found=obs.anchors[f'{route}-tab']
        assert found.matched and found.score>=.98 and found.device_box
        assert not detector.selected_tab(obs,route)
        assert detector.availability(obs,f'shop-{route}-privilege-gift')[0]=='UNKNOWN'


@pytest.mark.parametrize('offset',[0,80])
@pytest.mark.parametrize('bad',[None,'missing_badge','duplicate','occluded'])
def test_real_rocking_ranking_chest_uses_current_badge_and_pose(detector,offset,bad):
    from test_bxh_shop_fixed import make_frame
    raw=cv2.rotate(make_frame('ranking-chest').normalized,cv2.ROTATE_90_COUNTERCLOCKWISE)
    raw[75:200,90:210]=(150,120,70)
    patch=cv2.imread(str(FIXTURES/'ranking-rocking-chest.png'))
    raw[85:185,95+offset:195+offset]=patch
    if bad=='duplicate':
        raw[85:185,480:580]=patch
    c=ScreenshotService(lambda _:cv2.imencode('.png',raw)[1].tobytes()).take(Target(23,'other','explicit','boot'))
    obs=detector.observe(c)
    if bad in {'missing_badge','occluded'}:
        role='ranking-attention' if bad=='missing_badge' else 'ranking-chest'
        box=obs.box(role)
        assert box is not None
        raw[box.y:box.y+box.height,box.x:box.x+box.width]=0
        c=ScreenshotService(lambda _:cv2.imencode('.png',raw)[1].tobytes()).take(Target(23,'other','explicit','boot'))
        obs=detector.observe(c)
    state,core,_=detector.availability(obs,'ranking-chest')
    if bad:
        assert state=='UNKNOWN'
    else:
        assert state=='AVAILABLE' and core.score>=.96
        assert claim_geometry(obs,'ranking-chest',core)['tap']==list(core.device_box.center)

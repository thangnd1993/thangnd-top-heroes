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

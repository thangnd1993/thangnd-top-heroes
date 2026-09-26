"""Real failed frames and strict seven-reward acceptance regressions, offline."""
import json
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app import phase6_acceptance as final
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


def runners(calls):
    def vip(manager,data,index,name,folder,*,include_upper_gift,include_daily):
        calls.append(('vip',index,include_upper_gift,include_daily))
        return dict(final_result='NOT_AVAILABLE',journal_state='NONE',free_reward_state='UNAVAILABLE',
                    upper_gift=dict(result='NOT_AVAILABLE',journal_state='NONE'),
                    cleanup='SUCCESS',selection_restored=True,return_home='SUCCESS')
    def fixed(manager,data,target,folder,*,rewards):
        calls.append(('fixed',target['index'],rewards))
        return dict(rewards={r:dict(result='NOT_AVAILABLE',journal='NONE',claim_dispatched=False) for r in rewards},
                    cleanup='SUCCESS',selection_restored=True,return_home='SUCCESS',
                    shop_traversal=dict(entries=1,horizontal_swipes=2))
    return vip,fixed


def test_final_snapshot_all_seven_routes_and_protection(rig,tmp_path):
    manager,process,_=rig
    calls=[]
    vip,fixed=runners(calls)
    result=final.run(manager,tmp_path,identity_reader=lambda *a:'disk',vip_runner=vip,fixed_runner=fixed)
    assert result['result']=='PASS'
    assert result['max_concurrency']==1
    assert [r['index'] for r in result['targets']]==[7]
    assert set(result['accounts'][0]['rewards'])==set(final.REQUIRED)
    assert calls==[('vip',7,True,True),('fixed',7,final.FIXED)]
    assert all(c[1:]==['list2'] for c in process.calls)


def test_resume_only_unfinished_routes_keeps_completed_proof(rig,tmp_path):
    manager,_,_=rig
    calls=[]
    vip,fixed=runners(calls)
    result=final.run(manager,tmp_path,identity_reader=lambda *a:'disk',vip_runner=vip,fixed_runner=fixed)
    row=result['accounts'][0]
    row['rewards']['vip-daily']['result']='UNKNOWN'
    row['rewards']['shop-monthly-privilege-gift']['result']='BLOCKED'
    row['rewards']['shop-daily-gift'].update(result='SUCCESS',journal='VERIFIED',claim_id=123)
    old=tmp_path/'resume.json'
    old.write_text(json.dumps(result),encoding='utf-8')
    calls.clear()
    resumed=final.run(manager,tmp_path,resume_report=old,identity_reader=lambda *a:'disk',vip_runner=vip,fixed_runner=fixed)
    assert calls==[('vip',7,False,True),('fixed',7,('shop-monthly-privilege-gift',))]
    assert resumed['accounts'][0]['rewards']['shop-daily-gift']['claim_id']==123
    assert resumed['result']=='PASS'


def test_identity_change_before_resume_sends_no_action(rig,tmp_path):
    manager,_,_=rig
    calls=[]
    vip,fixed=runners(calls)
    result=final.run(manager,tmp_path,identity_reader=lambda *a:'disk',vip_runner=vip,fixed_runner=fixed)
    old=tmp_path/'resume.json'
    old.write_text(json.dumps(result),encoding='utf-8')
    calls.clear()
    resumed=final.run(manager,tmp_path,resume_report=old,identity_reader=lambda *a:'different-disk',vip_runner=vip,fixed_runner=fixed)
    assert not calls and resumed['result']=='PARTIAL'


def test_no_false_pass_for_uncertain_flow(rig,tmp_path):
    manager,_,_=rig
    calls=[]
    vip,fixed=runners(calls)
    def uncertain(*a,**kw):
        r=vip(*a,**kw)
        r['upper_gift']=dict(result='ALREADY_ATTEMPTED',journal_state='RESERVED')
        return r
    result=final.run(manager,tmp_path,identity_reader=lambda *a:'disk',vip_runner=uncertain,fixed_runner=fixed)
    assert result['result']=='PARTIAL'
    assert calls[-1][0]=='fixed'
    assert result['accounts'][0]['rewards']['vip-upper-gift']['journal']=='RESERVED'


def test_missing_or_changed_content_cannot_be_selected(detector):
    obs=detector.observe(captured('permanent-clipped-tab'))
    assert not detector.selected_tab(replace(obs,page='shop-weekly'),'monthly')


def test_recovery_only_resume_never_replays_completed_rewards(rig,tmp_path):
    manager,_,_=rig
    calls=[]
    vip,fixed=runners(calls)
    result=final.run(manager,tmp_path,identity_reader=lambda *a:'disk',vip_runner=vip,fixed_runner=fixed)
    result['accounts'][0]['recovery_ok']=False
    old=tmp_path/'recovery-resume.json'
    old.write_text(json.dumps(result),encoding='utf-8')
    calls.clear()
    resumed=final.run(manager,tmp_path,resume_report=old,identity_reader=lambda *a:'disk',vip_runner=vip,fixed_runner=fixed)
    assert calls==[('fixed',7,())]
    assert resumed['result']=='PASS'
    assert resumed['accounts'][0]['new_claims']==0

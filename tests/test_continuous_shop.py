"""One current-frame Shop traversal with bounded reusable Home overlay recovery."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from test_overlay_dismissal import RecoveryPort

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app import bxh_shop_acceptance as fleet
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort, ShopTraversal
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.automation.recovery import HomeRecoveryEngine, RecoveryResult, RecoveryStatus
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def covered_home(*, seed=1, missing=False, sharp=True):
    a=np.full((1280,720,3),40,np.uint8)
    if sharp:
        a[200:1050,100:620]=np.random.default_rng(seed).integers(30,220,(850,520,3),dtype=np.uint8)
    root=Path('assets/tasks/phase6/home-overlays')
    for name,x,y in [('covered-home-shop',556,3),('covered-home-world',570,1140)]:
        if missing and name.endswith('world'):
            continue
        crop=cv2.rotate(cv2.imread(str(root/f'{name}.png')),cv2.ROTATE_90_COUNTERCLOCKWISE)
        h,w=crop.shape[:2]
        a[y:y+h,x:x+w]=crop
    return ScreenshotService(lambda _:cv2.imencode('.png',a)[1].tobytes()).take(Target(31,'any','explicit','boot'))


@pytest.mark.parametrize('seed',[1,22,300])
def test_home_overlay_independent_of_event_artwork(seed):
    c=covered_home(seed=seed)
    d=RecoveryScreenDetector().detect(c)
    assert d.state==ScreenState.HOME_OVERLAY
    assert dismiss_overlay_bottom_left(c,d)==(58,1203)
    assert dismiss_overlay_bottom_left(replace(c,device_size=(1080,1920)),d)==(86,1805)


@pytest.mark.parametrize('kwargs',[dict(missing=True),dict(sharp=False)])
def test_incomplete_home_or_no_foreground_is_unknown(kwargs):
    assert RecoveryScreenDetector().detect(covered_home(**kwargs)).state==ScreenState.UNKNOWN


def test_home_popup_chain_fresh_frames_then_continue():
    p=RecoveryPort([ScreenState.HOME_OVERLAY]*2+[ScreenState.EVENT_PROMO]*2+[ScreenState.UNKNOWN,ScreenState.GAME_HOME])
    r=HomeRecoveryEngine(sleep=lambda _:None).ensure_game_home(p)
    assert r.status==RecoveryStatus.SUCCESS
    assert len(p.actions)==2 and p.observations==6
    assert r.states_seen[-1]=='GAME_HOME'


def test_unrelated_unknown_has_no_back_and_popup_loop_is_bounded():
    p=RecoveryPort([ScreenState.UNKNOWN]*2)
    r=HomeRecoveryEngine(sleep=lambda _:None).ensure_game_home(p)
    assert r.status==RecoveryStatus.UNKNOWN_SCREEN and not p.actions
    p=RecoveryPort([ScreenState.HOME_OVERLAY]*4)
    r=HomeRecoveryEngine(sleep=lambda _:None).ensure_game_home(p)
    assert r.status==RecoveryStatus.PROMO_BLOCKING and len(p.actions)==2


@pytest.mark.parametrize('blocked',[None,1])
def test_account_enters_shop_once_and_finishes_routes_before_cleanup(rig,tmp_path,monkeypatch,blocked):
    manager,_,_=rig
    calls=[]
    class Port:
        def __init__(self,*args):
            self.shop=ShopTraversal()
            self.events=[]
            self.page='home'
        def home(self):
            calls.append('home')
            self.page='home'
            return SimpleNamespace(page='home')
        def observe_settled(self):
            calls.append('capture_current_shop')
            return SimpleNamespace(page=self.page)
        def open_shop_reward(self,frame,reward):
            if frame.page=='home':
                self.shop.entries+=1
            assert self.shop.entries==1
            calls.append(reward)
            self.page='shop-current'
            if blocked is not None and reward==fleet.SHOP_REWARDS[blocked]:
                raise SafetyError('one independent reward blocked')
        def shop_state(self):return self.shop
    def process(port,store,namespace,task,reward,identity,outcome,persist):
        assert port.page=='shop-current'
        calls.append('receipt_then_same_shop')
        outcome.update(result='NOT_AVAILABLE',journal='NONE',claim_dispatched=False)
    monkeypatch.setattr(fleet,'process_reward',process)
    original=manager.execute
    def execute(index,action,**kwargs):
        assert calls.count('home')==2
        assert all(reward in calls for reward in fleet.SHOP_REWARDS)
        calls.append('cleanup')
        return original(index,action,**kwargs)
    monkeypatch.setattr(manager,'execute',execute)
    row=fleet.run_account(manager,tmp_path,dict(index=7,name='Farm-007'),tmp_path,
         rewards=fleet.SHOP_REWARDS,identity_reader=lambda *a:'disk',port_factory=Port,
         recovery_runner=lambda *a,**kw:(RecoveryResult(RecoveryStatus.SUCCESS),tmp_path/'r.json',True))
    assert calls.count('home')==2  # before entry and after all four routes only
    assert calls[-1]=='cleanup'
    assert row['shop_traversal']['entries']==1
    assert row['shop_traversal']['routes_processed']==list(fleet.SHOP_REWARDS)
    assert row['selection_restored'] and row['cleanup']=='SUCCESS'


def test_entry_repeated_from_home_fails_closed_without_tap():
    p=object.__new__(FixedRewardPort)
    p.shop=ShopTraversal(entries=1)
    frame=SimpleNamespace(page='home',box=lambda _:True)
    with pytest.raises(SafetyError,match='re-entry'):
        p.navigate(frame,'home-shop-entry','shop-daily')


def test_monthly_menu_closes_to_shop_not_home():
    p=object.__new__(FixedRewardPort)
    calls=[]
    p.navigate=lambda obs,role,expected:(calls.append((role,expected)),SimpleNamespace(page=expected))[1]
    p.find_tab=lambda obs,role:obs
    result=p.open_shop_reward(SimpleNamespace(page='shop-ad-privileges'),'shop-permanent-privilege-gift')
    assert calls==[('ads-close','shop-monthly'),('permanent-tab','shop-permanent')]
    assert result.page=='shop-permanent'



def test_random_shop_uses_current_live_set_even_if_previously_tested(rig,tmp_path):
    import json
    manager,_,_=rig
    history=tmp_path/'diagnostics/tasks/bxh-shop-fixed/old'
    history.mkdir(parents=True)
    (history/'fleet-report.json').write_text(json.dumps(dict(mode='random-test',random_target=dict(index=7))),encoding='utf-8')
    calls=[]
    def runner(manager,data,target,folder,*,rewards):
        calls.append(target['index'])
        return dict(index=target['index'],result='COMPLETE',rewards={r:dict(result='NOT_AVAILABLE',journal='NONE') for r in rewards})
    result=fleet.run_acceptance(manager,tmp_path,random_test=True,account_runner=runner,
                                identity_reader=lambda *a:'disk',rewards=fleet.SHOP_REWARDS)
    assert [r['index'] for r in result['eligible_candidates']]==[7]
    assert calls==[7] and result['random_target']['index']==7


@pytest.mark.parametrize('known_title',[True,False])
def test_only_known_receipt_title_allows_two_more_waits(monkeypatch,known_title):
    from types import SimpleNamespace

    from top_heroes_auto.vision.models import ScreenState
    monkeypatch.setattr('top_heroes_auto.app.fixed_reward_port.time.sleep',lambda _:None)
    monkeypatch.setattr('top_heroes_auto.app.fixed_reward_port.unique_current_anchor',
                        lambda *a:SimpleNamespace(matched=known_title))
    port=object.__new__(FixedRewardPort)
    port.detector=SimpleNamespace(recovery=SimpleNamespace(receipt_anchors=[SimpleNamespace(id='receipt-title')]))
    frame=SimpleNamespace(page='UNKNOWN',overlay=SimpleNamespace(state=ScreenState.UNKNOWN),captured=object())
    calls=[]
    def observe():
        calls.append('observe')
        return frame
    port.observe=observe
    port.dispatch=lambda *a:pytest.fail('A title alone never authorizes input')
    assert port.settle(frame) is frame
    assert len(calls)==(5 if known_title else 3)


def test_monthly_rocking_entry_waits_for_fresh_qualified_frame(monkeypatch):
    monkeypatch.setattr('top_heroes_auto.automation.fixed_reward_claims.time.sleep',lambda _:None)
    port=object.__new__(FixedRewardPort)
    first=SimpleNamespace(page='shop-monthly',box=lambda _:False)
    fresh=SimpleNamespace(page='shop-monthly',box=lambda _:False)
    port.detector=SimpleNamespace(availability=lambda frame,reward:('AVAILABLE' if frame is fresh else 'UNKNOWN',None,None))
    port.observe_settled=lambda:fresh
    calls=[]
    port.navigate=lambda frame,role,expected:calls.append((frame,role,expected)) or frame
    port.open_shop_reward(first,'shop-monthly-privilege-gift')
    assert calls==[(fresh,'monthly-gift','shop-ad-privileges')]

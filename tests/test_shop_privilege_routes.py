"""Four shop routes: viewport discovery and page identity are separate gates."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from test_bxh_shop_fixed import paste

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort, TabNotFound
from top_heroes_auto.automation.fixed_reward_period import current_attempts, cycle_key
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.fixed_rewards import SHOP_REWARDS, FixedRewardDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


def frame(route, *, selected=True, title=True, target=True, badge=True, tab_x=None):
    image = np.full((1280, 720, 3), (150, 120, 70), dtype=np.uint8)
    paste(image, 'shop-title', 313, 25)
    paste(image, 'back', 35, 1215)
    if title:
        paste(image, f'{route}-title', 34, 139)
    x = (197 if route == 'permanent' else 358) if tab_x is None else tab_x
    paste(image, f'{route}-tab', x, 1201)
    if selected:
        paste(image, f'{route}-active-tab', x-46, 1175)
    if target:
        paste(image, f'{route}-gift', 595 if route == 'permanent' else 583, 211 if route == 'permanent' else 150)
    if badge:
        paste(image, f'{route}-attention', 667 if route == 'permanent' else 666, 190 if route == 'permanent' else 135)
    return ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(23, 'arbitrary', 'explicit', 'boot'))


@pytest.fixture(scope='module')
def detector():
    return FixedRewardDetector()


@pytest.mark.parametrize('route,reward', list(zip(('permanent', 'monthly'), SHOP_REWARDS[2:], strict=True)))
def test_page_requires_content_and_selected_tab(detector, route, reward):
    good = detector.observe(frame(route))
    assert good.page == f'shop-{route}'
    assert detector.availability(good, reward)[0] == 'AVAILABLE'
    for kw in ({'selected':False}, {'title':False}, {'target':False}):
        obs = detector.observe(frame(route, **kw))
        assert detector.availability(obs, reward)[0] == 'UNKNOWN'
    assert detector.availability(good, SHOP_REWARDS[1])[0] == 'UNKNOWN'


@pytest.mark.parametrize('route', ['permanent', 'monthly'])
def test_scroll_reveals_tab_but_does_not_select_page(detector, monkeypatch, route):
    monkeypatch.setattr('top_heroes_auto.app.fixed_reward_port.time.sleep', lambda _:None)
    visible = detector.observe(frame(route))
    # Newly exposed tab over the OLD weekly content: still weekly.
    visible = replace(visible, page='shop-weekly')
    hidden = replace(visible, anchors={**visible.anchors, f'{route}-tab':replace(
        visible.anchors[f'{route}-tab'], matched=False, device_box=None)})
    actions = []
    port = object.__new__(FixedRewardPort)
    port.detector = detector
    port.dispatch = lambda obs, action, values:actions.append((action, values))
    port.observe_settled = lambda:visible
    discovered = port.find_tab(hidden, f'{route}-tab')
    assert discovered.page == 'shop-weekly'
    assert actions[0][0] == 'swipe'
    x1,y1,x2,y2,_ = actions[0][1]
    assert x1>x2>visible.box('back').x+visible.box('back').width
    assert y1==y2 and y1>1280*.92
    port.tap = lambda obs, anchor:actions.append(('tap', anchor.device_box))
    with pytest.raises(SafetyError, match='Expected'):
        port.navigate(discovered, f'{route}-tab', f'shop-{route}')
    port.observe_settled = lambda:detector.observe(frame(route))
    assert port.navigate(discovered, f'{route}-tab', f'shop-{route}').page == f'shop-{route}'


@pytest.mark.parametrize('route', ['permanent', 'monthly'])
def test_missing_or_clipped_tab_fails_closed_bounded(detector, monkeypatch, route):
    monkeypatch.setattr('top_heroes_auto.app.fixed_reward_port.time.sleep', lambda _:None)
    obs = detector.observe(frame(route))
    evidence = obs.anchors[f'{route}-tab']
    clipped = replace(evidence, device_box=replace(evidence.device_box, x=700))
    obs = replace(obs, anchors={**obs.anchors,f'{route}-tab':clipped})
    calls=[]
    port=object.__new__(FixedRewardPort)
    port.dispatch=lambda *a:calls.append(a)
    port.observe_settled=lambda:obs
    with pytest.raises(TabNotFound, match='TAB_NOT_FOUND'):
        port.find_tab(obs,f'{route}-tab')
    assert len(calls)==1  # repeated viewport terminates early
    for forbidden in ('diamond-tab','city-fund-tab','weekly-pack-tab'):
        with pytest.raises(SafetyError, match='Forbidden'):
            port.find_tab(obs,forbidden)
    with pytest.raises(SafetyError, match='no scroll'):
        port.find_tab(replace(obs,page='UNKNOWN'), f'{route}-tab')
    assert len(calls)==1


def test_possible_daily_remains_locked_across_reset_without_blocking_other_rewards():
    now=datetime.now(timezone.utc)
    row=dict(reward_id='shop-daily-gift',status='RESERVED',dispatch_state='POSSIBLE',
             reserved_at=(now-timedelta(days=3)).isoformat(),id=41)
    assert current_attempts([row],'shop-daily-gift',now)==[row]
    for reward in SHOP_REWARDS[1:]:
        assert current_attempts([row],reward,now)==[]
    assert len({cycle_key(r,now) for r in SHOP_REWARDS})==4


def test_open_route_uses_new_frame_and_never_claims():
    port=object.__new__(FixedRewardPort)
    initial=SimpleNamespace(page='shop-weekly')
    fresh=SimpleNamespace(page='shop-weekly')
    final=SimpleNamespace(page='shop-permanent')
    calls=[]
    port.find_tab=lambda obs,role:fresh
    def navigate(obs,role,expected):
        assert obs is fresh
        calls.append(role)
        return final
    port.navigate=navigate
    assert port.open_shop_reward(initial,SHOP_REWARDS[2]) is final
    assert calls==['permanent-tab']


@pytest.mark.parametrize('route,reward', list(zip(('permanent', 'monthly'), SHOP_REWARDS[2:], strict=True)))
def test_privilege_one_shot_needs_underlying_received_state(detector, tmp_path, route, reward):
    from top_heroes_auto.automation.fixed_reward_claims import process_reward
    from top_heroes_auto.storage.store import Store

    before=detector.observe(frame(route))
    after_frame=frame(route, target=False, badge=False)
    portrait=cv2.rotate(after_frame.normalized, cv2.ROTATE_90_COUNTERCLOCKWISE)
    paste(portrait, 'daily-received', 592, 212)
    captured=ScreenshotService(lambda _:cv2.imencode('.png',portrait)[1].tobytes()).take(Target(23,'arbitrary','explicit','boot'))
    before=replace(before,captured=replace(before.captured,source_image=tmp_path/'before.png'))
    after=detector.observe(replace(captured,source_image=tmp_path/'after.png'))
    assert detector.availability(after,reward)[0]=='NOT_AVAILABLE'
    store=Store(tmp_path/'claims.sqlite3')
    task=store.create_task_run('n','bxh-shop-fixed',23,'arbitrary')
    taps=[]
    def tap(obs,core,before_input):
        before_input()
        taps.append(core.device_box.center)
    port=SimpleNamespace(detector=detector,observe_settled=lambda:before,tap=tap,
                         save_geometry=lambda *a:None,observe=lambda:after,settle=lambda o:o)
    result={}
    process_reward(port,store,'n',task,reward,'disk',result,lambda:None)
    assert result['journal']=='VERIFIED'
    process_reward(port,store,'n',task,reward,'disk',{},lambda:None)
    assert len(taps)==1


def test_shop_fleet_cannot_pass_when_one_required_route_missing(rig,tmp_path):
    from top_heroes_auto.app.bxh_shop_acceptance import run_acceptance

    manager,_,_=rig
    called=[]
    def runner(manager,data,target,folder,*,rewards):
        called.append(target['index'])
        assert rewards==SHOP_REWARDS
        return dict(index=target['index'],result='COMPLETE',rewards={
            r:dict(result='NOT_AVAILABLE',journal='NONE') for r in rewards[:-1]})
    result=run_acceptance(manager,tmp_path,account_runner=runner,
                          identity_reader=lambda *a:'disk',rewards=SHOP_REWARDS)
    assert called==[r['index'] for r in result['targets']]
    assert result['result']=='PARTIAL'
    assert result['required_rewards']==list(SHOP_REWARDS)


@pytest.mark.parametrize('configured', [None, 'wrong'])
def test_missing_or_changed_persistent_name_blocks_before_lifecycle(tmp_path, configured):
    import json

    from top_heroes_auto.app.bxh_shop_acceptance import persistent_identity

    folder=tmp_path/'vms/config'
    folder.mkdir(parents=True)
    (folder/'leidian23.config').write_text(json.dumps({'statusSettings.playerName':configured}),encoding='utf-8')
    manager=SimpleNamespace(ld=SimpleNamespace(installation=SimpleNamespace(console=tmp_path/'ldconsole.exe')),
                            query=lambda _:SimpleNamespace(name='authorized'))
    with pytest.raises(SafetyError,match='Persistent instance name'):
        persistent_identity(manager,23)


def test_old_possible_cannot_be_verified_from_new_daily_period(detector):
    import json

    from test_bxh_shop_fixed import make_frame

    from top_heroes_auto.automation.fixed_reward_claims import process_reward

    before=detector.observe(make_frame('shop-daily-gift',badge=False))
    row=dict(id=41,reward_id='shop-daily-gift',status='RESERVED',dispatch_state='POSSIBLE',
             reserved_at=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat(),
             before_evidence=json.dumps({'persistent_identity':'disk'}))
    store=SimpleNamespace(reward_claims=lambda *a:[row])
    port=SimpleNamespace(detector=detector,observe_settled=lambda:before)
    result={}
    process_reward(port,store,'n',1,'shop-daily-gift','disk',result,lambda:None)
    assert result['journal']=='RESERVED'
    assert result['result']=='ALREADY_ATTEMPTED'
    assert result['claim_dispatched'] is False
    assert 'prior reset' in result['reconciliation_error']


def test_visible_reward_with_unqualified_reset_is_not_reported_complete(detector):
    import json

    from top_heroes_auto.automation.fixed_reward_claims import process_reward

    reward=SHOP_REWARDS[2]
    before=detector.observe(frame('permanent'))
    row=dict(id=90,reward_id=reward,status='VERIFIED',dispatch_state='POSSIBLE',
             reserved_at=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat(),
             before_evidence=json.dumps({'persistent_identity':'disk'}))
    store=SimpleNamespace(reward_claims=lambda *a:[row])
    port=SimpleNamespace(detector=detector,observe_settled=lambda:before)
    result={}
    process_reward(port,store,'n',1,reward,'disk',result,lambda:None)
    assert result['journal']=='VERIFIED'
    assert result['result']=='PERIOD_UNQUALIFIED'
    assert result['claim_dispatched'] is False

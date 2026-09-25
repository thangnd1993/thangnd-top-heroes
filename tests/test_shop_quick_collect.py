"""User-qualified bottom action: isolated from ads, paid banner and legacy entry."""
import io
from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from test_bxh_shop_fixed import paste

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app import bxh_shop_acceptance as fleet
from top_heroes_auto.automation.fixed_reward_claims import process_reward
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.fixed_rewards import MONTHLY_QUICK, FixedRewardDetector, claim_geometry
from top_heroes_auto.vision.screenshot import ScreenshotService


def menu(*, offset=0, missing=None, duplicate=False, button_y=977):
    image = np.full((1280,720,3), (28,35,42), np.uint8)
    for name,(x,y) in {'ads-title':(159,53), 'ads-banner':(96,326),
                      'ads-quick':(225+offset,button_y), 'ads-close':(331,1182)}.items():
        if name != missing:
            paste(image,name,x,y)
    if duplicate:
        paste(image,'ads-quick',225,850)
    return ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
        Target(23,'any name','explicit','boot'))


@pytest.fixture(scope='module')
def detector():
    return FixedRewardDetector()


@pytest.mark.parametrize('offset',[-30,0,30])
def test_bottom_button_current_bbox_and_exclusion(detector,offset):
    obs=detector.observe(menu(offset=offset))
    assert obs.page=='shop-ad-privileges'
    state,core,_=detector.availability(obs,MONTHLY_QUICK)
    assert state=='AVAILABLE'
    geometry=claim_geometry(obs,MONTHLY_QUICK,core)
    assert geometry['tap']==[359+offset,1013]
    assert geometry['tap'][1]>geometry['forbidden']['height']
    assert detector.availability(obs,'shop-monthly-privilege-gift')[0]=='UNKNOWN'


@pytest.mark.parametrize('kwargs',[{'missing':'ads-title'},{'missing':'ads-banner'},
                                  {'missing':'ads-close'},{'missing':'ads-quick'},
                                  {'duplicate':True},{'button_y':500}])
def test_incomplete_duplicate_or_row_button_cannot_claim(detector,kwargs):
    obs=detector.observe(menu(**kwargs))
    assert detector.availability(obs,MONTHLY_QUICK)[0]=='UNKNOWN'


def test_legacy_upper_gift_cannot_be_dispatched_as_claim():
    with pytest.raises(ValueError,match='navigation'):
        process_reward(None,None,'n',1,'shop-monthly-privilege-gift','disk',{},lambda:None)


def test_quick_collect_one_shot_uncertain_cannot_retry(detector,tmp_path):
    from top_heroes_auto.storage.store import Store
    store=Store(tmp_path/'claims.sqlite3')
    task=store.create_task_run('n','bxh-shop-fixed',23,'any name')
    before=detector.observe(menu())
    before=replace(before,captured=replace(before.captured,source_image=tmp_path/'before.png'))
    after=detector.observe(menu(missing='ads-quick'))
    after=replace(after,captured=replace(after.captured,source_image=tmp_path/'after.png'))
    taps=[]
    def tap(obs,core,before_input):
        before_input()
        taps.append(core.device_box.center)
    port=SimpleNamespace(detector=detector,observe_settled=lambda:before,tap=tap,
                         observe=lambda:after,settle=lambda o:o,save_geometry=lambda *a:None)
    result={}
    process_reward(port,store,'n',task,MONTHLY_QUICK,'disk',result,lambda:None)
    assert result['result']=='ACTION_DISPATCHED_UNVERIFIED'
    assert result['journal']=='RESERVED'
    process_reward(port,store,'n',task,MONTHLY_QUICK,'disk',{},lambda:None)
    assert taps==[(359,1013)]


def test_unicode_progress_does_not_change_names_or_abort(monkeypatch):
    raw=io.BytesIO()
    console=io.TextIOWrapper(raw,encoding='cp1252')
    monkeypatch.setattr('sys.stdout',console)
    name='Nấm hương'
    fleet.progress(name)
    console.flush()
    assert raw.getvalue()
    assert name=='Nấm hương'


def test_interrupted_resume_only_unvisited_snapshot():
    targets=[dict(index=i,name=f'Account {i}',protected=False,persistent_identity='disk') for i in (3,10,11)]
    previous=dict(mode='fleet',max_concurrency=1,required_rewards=list(fleet.SHOP_REWARDS),
                  targets=targets,accounts=[dict(index=3,rewards={},result='BLOCKED')])
    plan=fleet.resume_plan(previous,targets,rewards=fleet.SHOP_REWARDS)
    assert [t['index'] for t,_ in plan]==[10,11]
    assert previous['accounts']==[dict(index=3,rewards={},result='BLOCKED')]
    with pytest.raises(SafetyError):
        fleet.resume_plan({**previous,'required_rewards':[]},targets,rewards=fleet.SHOP_REWARDS)
    with pytest.raises(SafetyError):
        fleet.resume_plan({**previous,'accounts':previous['accounts']*2},targets,rewards=fleet.SHOP_REWARDS)


@pytest.mark.parametrize('route,roles',[
    ('daily', [('daily-core-current',605,222),('daily-badge-current',647,202)]),
    ('permanent',[('permanent-core-current',592,218),('permanent-badge-current',665,189)])])
def test_current_gift_pose_with_independent_page_and_badge(detector,route,roles):
    image=np.full((1280,720,3),(150,120,70),np.uint8)
    paste(image,'shop-title',313,25)
    paste(image,f'{route}-title',34,139)
    if route=='permanent':
        paste(image,'permanent-tab',477,1201)
        paste(image,'permanent-active-current',430,1175)
    for role,x,y in roles:
        paste(image,role,x,y)
    def observe():
        return detector.observe(ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
            Target(31,'other layout','explicit','boot')))
    reward='shop-daily-gift' if route=='daily' else 'shop-permanent-privilege-gift'
    assert detector.availability(observe(),reward)[0]=='AVAILABLE'
    # Removing the local attention badge cannot qualify a claim or unavailability.
    _,x,y=roles[1]
    image[y:y+25,x:x+23]=(150,120,70)
    assert detector.availability(observe(),reward)[0]=='UNKNOWN'


def test_interrupted_fleet_appends_unvisited_preserving_history(rig,tmp_path):
    import json
    manager,_,_=rig
    rows=fleet.inventory(manager)
    target=dict(next(r for r in rows if r['index']==7),persistent_identity='disk')
    previous=dict(mode='fleet',max_concurrency=1,required_rewards=list(fleet.SHOP_REWARDS),
                  targets=[target],accounts=[])
    path=tmp_path/'previous.json'
    path.write_text(json.dumps(previous),encoding='utf-8')
    def runner(manager,data,target,folder,*,rewards):
        return dict(index=7,result='COMPLETE',rewards={r:dict(result='NOT_AVAILABLE',journal='NONE') for r in rewards})
    report=fleet.run_acceptance(manager,tmp_path,resume_report=path,account_runner=runner,
                               identity_reader=lambda *a:'disk',rewards=fleet.SHOP_REWARDS)
    assert len(report['accounts'])==1
    assert json.loads(path.read_text(encoding='utf-8'))==previous
    (tmp_path/'7').mkdir()
    with pytest.raises(SafetyError,match='partial evidence'):
        fleet.run_acceptance(manager,tmp_path,resume_report=path,account_runner=runner,
                             identity_reader=lambda *a:'disk',rewards=fleet.SHOP_REWARDS)


def completed_menu(*, missing=None, active=False):
    image=cv2.rotate(menu(missing=None if active else 'ads-quick').normalized,cv2.ROTATE_90_COUNTERCLOCKWISE)
    for row,y in zip(('energy','meat','wood','stone','rune'),(383,513,640,771,902),strict=True):
        paste(image,f'ads-{row}',185,y)
        if row!=missing:
            paste(image,'ads-completed',482,y+28)
    return ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(Target(23,'any name','explicit','boot'))


@pytest.mark.parametrize('missing', [None,'energy','meat','wood','stone','rune'])
def test_positive_five_completed_rows_required(detector,missing):
    state=detector.availability(detector.observe(completed_menu(missing=missing)),MONTHLY_QUICK)[0]
    assert state==('NOT_AVAILABLE' if missing is None else 'UNKNOWN')
    assert detector.availability(detector.observe(completed_menu(active=True)),MONTHLY_QUICK)[0]=='UNKNOWN'


@pytest.mark.parametrize('bad', [None,'missing_row','wrong_tap','changed_boot','stale_after'])
def test_saved_original_poststate_reconciliation_never_redispatches(detector,tmp_path,bad):
    import json
    from datetime import datetime, timedelta

    from top_heroes_auto.automation.fixed_reward_reconcile import reconcile_saved_fixed_reward
    from top_heroes_auto.storage.store import Store
    store=Store(tmp_path/'claims.sqlite3')
    task=store.create_task_run('n','bxh-shop-fixed',23,'any name')
    target=Target(23,'any name','explicit','boot')
    def save(frame,name):
        raw=cv2.rotate(frame.normalized,cv2.ROTATE_90_COUNTERCLOCKWISE)
        return ScreenshotService(lambda _:cv2.imencode('.png',raw)[1].tobytes()).take(target,tmp_path,name)
    before=detector.observe(save(menu(),'before'))
    # The old runtime could not qualify this new post-state. Preserve its raw
    # image and reconcile using the new positive row detector, without input.
    immediate=detector.observe(save(menu(missing='ads-quick'),'immediate'))
    after=detector.observe(save(completed_menu(missing='wood' if bad=='missing_row' else None),'after'))
    after=replace(after,page='UNKNOWN')
    actions=[]
    report=dict(persistent_identity='disk',rewards={'shop-monthly-privilege-gift':dict(action_reward_id=MONTHLY_QUICK)})
    path=tmp_path/'account-report.json'
    def persist():
        path.write_text(json.dumps(report),encoding='utf-8')
    def tap(obs,core,before_input):
        before_input()
        actions.append(dict(before=str(obs.captured.source_image),action='tap',values=list(core.device_box.center),outcome='DISPATCHED'))
    port=SimpleNamespace(detector=detector,observe_settled=lambda:before,tap=tap,
                         observe=lambda:immediate,settle=lambda _:after,save_geometry=lambda *a:None)
    outcome=report['rewards']['shop-monthly-privilege-gift']
    process_reward(port,store,'n',task,MONTHLY_QUICK,'disk',outcome,persist)
    store.finish_task_run(task,'PARTIAL',report_path=str(path))
    assert outcome['result']=='ACTION_DISPATCHED_UNVERIFIED'
    if bad=='wrong_tap':
        actions[0]['values']=[600,400]
    if bad=='changed_boot':
        outcome['after']['boot_id']='different'
    if bad=='stale_after':
        outcome['after']['timestamp']=(datetime.fromisoformat(before.captured.timestamp)+timedelta(minutes=5)).isoformat()
    persist()
    (tmp_path/'actions.json').write_text(json.dumps(actions),encoding='utf-8')
    if bad:
        with pytest.raises(ValueError):
            reconcile_saved_fixed_reward(store,outcome['claim_id'])
    else:
        proof=reconcile_saved_fixed_reward(store,outcome['claim_id'])
        assert proof['result']=='VERIFIED' and not proof['claim_redispatched']
    assert len(actions)==1
    assert store.reward_claims('n',23)[0]['status']==('RESERVED' if bad else 'VERIFIED')



def test_period_check_accepts_transactional_sqlite_rows():
    import sqlite3
    from datetime import datetime, timedelta, timezone

    from top_heroes_auto.automation.fixed_reward_period import current_attempts
    with sqlite3.connect(':memory:') as db:
        db.row_factory=sqlite3.Row
        row=db.execute("SELECT 'shop-daily-gift' AS reward_id, 'VERIFIED' AS status, 'POSSIBLE' AS dispatch_state, ? AS reserved_at",
                       ((datetime.now(timezone.utc)-timedelta(days=3)).isoformat(),)).fetchone()
        assert current_attempts([row],'shop-daily-gift')==[]
        row=db.execute("SELECT 'shop-daily-gift' AS reward_id, 'RESERVED' AS status, 'POSSIBLE' AS dispatch_state, ? AS reserved_at",
                       ((datetime.now(timezone.utc)-timedelta(days=3)).isoformat(),)).fetchone()
        assert len(current_attempts([row],'shop-daily-gift'))==1



@pytest.mark.parametrize('reward', ['shop-weekly-card-gift','shop-permanent-privilege-gift'])
def test_received_gift_requires_its_own_page(detector,reward):
    from test_bxh_shop_fixed import make_frame
    from test_shop_privilege_routes import frame
    if reward=='shop-weekly-card-gift':
        c=make_frame(reward,badge=False)
        name,point='weekly-received-current',(609,318)
    else:
        c=frame('permanent',target=False,badge=False)
        name,point='permanent-received',(588,188)
    raw=cv2.rotate(c.normalized,cv2.ROTATE_90_COUNTERCLOCKWISE)
    raw[185:450,575:720]=(150,120,70)
    paste(raw,name,*point)
    obs=detector.observe(ScreenshotService(lambda _:cv2.imencode('.png',raw)[1].tobytes()).take(Target(23,'any name','explicit','boot')))
    assert detector.availability(obs,reward)[0]=='NOT_AVAILABLE'
    other='shop-permanent-privilege-gift' if reward=='shop-weekly-card-gift' else 'shop-weekly-card-gift'
    assert detector.availability(obs,other)[0]=='UNKNOWN'

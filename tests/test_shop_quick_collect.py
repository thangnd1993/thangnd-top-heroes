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

"""Dynamic event write-ahead locks and independent post-condition tests."""
from dataclasses import replace

import pytest
from test_dynamic_events import control, frame

from top_heroes_auto.automation.event_journal import dispatch_once
from top_heroes_auto.storage.store import Store


def setup(tmp_path):
    store=Store(tmp_path/'events.sqlite3')
    task=store.create_task_run('install','events',13,'user name')
    f=frame('page-title',1)
    r=control('daily-gift','reward',cost='FREE',available=True)
    return store,task,f,r


def success(f,r):
    return [dict(identity=list(f.identity),capture=f'post-{n}',event='current-event',page=f.page,
                 reward=r.identity,state='NOT_AVAILABLE',independent_evidence=['disabled-control','claimed-marker'])
            for n in range(2)]


def run(store,task,f,r,calls,post=success,dispatch=None):
    def send(frame,reward,point,before):
        before()
        calls.append(point)
    return dispatch_once(store,task,'install',f,r,event_identity='current-event',persistent_identity='disk',
                         dispatch=dispatch or send,postcondition=post)


@pytest.mark.parametrize('verified',[True,False])
def test_verified_and_possible_cannot_repeat(tmp_path,verified):
    store,task,f,r=setup(tmp_path)
    calls=[]
    a=run(store,task,f,r,calls,post=success if verified else lambda *a: [])
    b=run(store,task,replace(f,capture='new'),r,calls)
    assert len(calls)==1
    assert a['journal']==b['journal']==('VERIFIED' if verified else 'RESERVED')
    assert b['claim_dispatched'] is False


def test_possible_does_not_unlock_on_new_period(tmp_path):
    store,task,f,r=setup(tmp_path)
    calls=[]
    run(store,task,f,r,calls,post=lambda *a: [])
    run(store,task,f,replace(r,period='proven-new-period'),calls)
    assert len(calls)==1


def test_sibling_is_not_suppressed(tmp_path):
    store,task,f,r=setup(tmp_path)
    calls=[]
    run(store,task,f,r,calls)
    run(store,task,f,replace(r,identity='another-free-reward'),calls)
    assert len(calls)==2
    assert len(store.reward_claims('install',13))==2


def test_undispatched_failure_releases_only_own_reservation(tmp_path):
    store,task,f,r=setup(tmp_path)
    def fail(*a):
        raise ValueError('guard rejected before input')
    with pytest.raises(ValueError):
        run(store,task,f,r,[],dispatch=fail)
    assert not store.reward_claims('install',13)


@pytest.mark.parametrize('change',[{'state':'POPUP'},{'capture':'1'}, {'identity':[14,'other','adb','boot']},
                                    {'reward':'different'}, {'independent_evidence':[]}])
def test_receipt_or_wrong_context_not_verified(tmp_path,change):
    store,task,f,r=setup(tmp_path)
    def bad(f,r):
        result=success(f,r)
        result[0].update(change)
        return result
    outcome=run(store,task,f,r,[],post=bad)
    assert outcome['result']=='ACTION_DISPATCHED_UNVERIFIED'
    assert store.reward_claims('install',13)[0]['status']=='RESERVED'


def test_dispatch_error_stays_locked(tmp_path):
    store,task,f,r=setup(tmp_path)
    def uncertain(f,r,p,before):
        before()
        raise OSError('ADB transport result unknown')
    with pytest.raises(OSError):
        run(store,task,f,r,[],dispatch=uncertain)
    assert store.reward_claims('install',13)[0]['dispatch_state']=='POSSIBLE'


@pytest.mark.parametrize('post_state',['NOT_AVAILABLE','AVAILABLE','MISSING','POPUP_ONLY'])
def test_production_adapter_requires_same_card_change_after_one_dispatch(tmp_path,monkeypatch,post_state):
    from types import SimpleNamespace

    from top_heroes_auto.app.dynamic_event_port import DynamicEventPort

    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep',lambda _:None)
    store,_,f,r=setup(tmp_path)
    initial=replace(f,page='event:runtime-title:personal-tasks',controls=(r,))
    fresh=replace(initial,capture='fresh-before')
    receipt=replace(initial,capture='receipt',page='UNKNOWN',controls=(),popup=True)
    after=[replace(initial,capture=f'after-{n}',controls=(),popup=False) for n in range(2)]
    if post_state=='POPUP_ONLY':
        after=[replace(a,page='UNKNOWN') for a in after]
    frames=iter([fresh,receipt,*after])
    port=object.__new__(DynamicEventPort)
    port.current=initial
    port.event_title='runtime-title'
    port.folder=tmp_path
    port.session=SimpleNamespace(manager=SimpleNamespace(store=store,namespace='install'),
        index=f.identity[0],name=f.identity[1],target={'persistent_identity':'disk'})
    sent=[]
    dismissed=[]

    def observe():
        port.current=next(frames)
        port.rows=[] if post_state=='MISSING' else [dict(identity=r.identity,state=post_state)]
        return port.current

    def dispatch(observed,action,point,before_input):
        before_input()
        sent.append((action,point))

    port.observe=observe
    port.dismiss=lambda frame:dismissed.append(frame.capture)
    port.transport=SimpleNamespace(last=object(),dispatch=dispatch)
    result=port.claim(initial,r)
    assert len(sent)==1 and dismissed==['receipt']
    assert result['claim_dispatched']
    row=store.reward_claims('install',f.identity[0])[0]
    if post_state=='NOT_AVAILABLE':
        assert result['journal']=='VERIFIED' and row['status']=='VERIFIED'
    else:
        assert result['result']=='ACTION_DISPATCHED_UNVERIFIED'
        assert row['status']=='RESERVED' and row['dispatch_state']=='POSSIBLE'


@pytest.mark.parametrize('verified',[True,False])
def test_title_ocr_change_cannot_unlock_unknown_period_reward(tmp_path,verified):
    store,task,f,r=setup(tmp_path)
    calls=[]
    run(store,task,f,r,calls,post=success if verified else lambda *a:[])
    after=replace(f,page='different-ocr-title',capture='new-frame')
    result=dispatch_once(store,task,'install',after,r,event_identity='different-title',
        persistent_identity='disk',dispatch=lambda *a:calls.append('must-not-send'),postcondition=success)
    assert len(calls)==1 and not result['claim_dispatched']

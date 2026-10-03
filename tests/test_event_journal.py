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

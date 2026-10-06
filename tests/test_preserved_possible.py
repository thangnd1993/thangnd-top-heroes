"""User-approved historical uncertainty completes acceptance without replay/mutation."""
import json

import pytest
from test_instance_pipeline import run

from top_heroes_auto.app.resume_exception import preserved_claims
from top_heroes_auto.automation.guard import SafetyError


def original(rig,tmp_path):
    calls = []
    result = run(rig,tmp_path,calls)
    manager,_,store = rig
    task = store.create_task_run(manager.namespace,'test',7,'Farm-007')
    cid = store.reserve_reward_claim(task,'one','batch',json.dumps({'persistent_identity':'disk'}),not_dispatched=True)
    store.mark_reward_dispatch(cid,task)
    result['accounts'][0]['rewards']['one'] = dict(result='ACTION_DISPATCHED_UNVERIFIED',journal='RESERVED',
        claim_dispatched=True,actions=[{'claim_id':cid}])
    result['accounts'][0]['rewards']['two']['result'] = 'UNKNOWN'
    path = tmp_path/'resume.json'
    path.write_text(json.dumps(result),encoding='utf-8')
    return calls,result,path,cid,dict(store.reward_claims(manager.namespace,7)[0])


def test_explicit_exception_skips_only_locked_reward_and_preserves_exact_row(rig,tmp_path):
    calls,_,path,cid,before = original(rig,tmp_path)
    calls.clear()
    result = run(rig,tmp_path,calls,resume_report=path,preserve_possible=(cid,))
    assert calls == [(7,'start'),(7,'feature-one',('two',)),(7,'cleanup')]
    assert result['result'] == 'PASS' and result['preserved_journals_unchanged']
    proof = result['accounts'][0]['rewards']['one']
    assert proof['result'] == 'PRESERVED_POSSIBLE' and proof['journal'] == 'RESERVED'
    assert proof['dispatch_state'] == 'POSSIBLE' and not proof['claim_dispatched']
    assert dict(rig[2].reward_claims(rig[0].namespace,7)[0]) == before
    # A later resume must explicitly retain the exception, not silently trust the label.
    path.write_text(json.dumps(result),encoding='utf-8')
    with pytest.raises(SafetyError,match='explicitly retain'):
        run(rig,tmp_path,[],resume_report=path)


@pytest.mark.parametrize('bad',['missing','identity','protected','verified','not-dispatched','wrong-prior','new-run'])
def test_exception_requires_exact_existing_possible_and_original_scope(rig,tmp_path,bad):
    _,previous,_,cid,_ = original(rig,tmp_path)
    manager,_,store = rig
    targets = previous['targets']
    ids = (cid,)
    if bad == 'missing':
        ids = (9999,)
    elif bad == 'identity':
        targets[0]['persistent_identity'] = 'replacement'
    elif bad == 'name':
        targets[0]['name'] = 'replacement'
    elif bad == 'protected':
        store.protect(manager.namespace,7,True)
    elif bad in {'verified','not-dispatched'}:
        with store.connect() as db:
            db.execute('UPDATE reward_claims SET status=?,dispatch_state=? WHERE id=?',
                ('VERIFIED' if bad == 'verified' else 'RESERVED','NOT_DISPATCHED' if bad == 'not-dispatched' else 'POSSIBLE',cid))
    elif bad == 'wrong-prior':
        previous['accounts'][0]['rewards']['one']['actions'] = []
    else:
        previous = None
    with pytest.raises(SafetyError):
        preserved_claims(manager,previous,targets,ids)


def test_fresh_unverified_outcome_cannot_self_authorize_exception(rig,tmp_path):
    from test_instance_pipeline import setup

    from top_heroes_auto.app.automation_fleet import run as fleet
    from top_heroes_auto.app.flow_registry import Flow
    calls,_,path,cid,_ = original(rig,tmp_path)
    registry,session,_ = setup(calls)
    registry.register(Flow('new',('four',),lambda *a:dict(return_home='SUCCESS',rewards={
        'four':dict(result='PRESERVED_POSSIBLE',claim_id=999,authorized_exception=True)})))
    result = fleet(rig[0],tmp_path,registry=registry,session_factory=session,
        identity_reader=lambda *a:'disk',resume_report=path,preserve_possible=(cid,))
    assert result['result'] == 'PARTIAL'


def test_cli_requires_resume_and_explicit_exception_ids(monkeypatch,tmp_path):
    from top_heroes_auto.app import automation_fleet, diagnostic, main

    calls = []
    monkeypatch.setattr(diagnostic,'_manager',lambda _:object())
    monkeypatch.setattr(automation_fleet,'run',lambda *a,**kw:calls.append(kw))
    with pytest.raises(ValueError):
        main.main(['automation-acceptance','--random-test','--preserve-possible','138'])
    with pytest.raises(SystemExit):
        main.main(['automation-acceptance','--resume-report',str(tmp_path),'--force'])
    assert not calls
    main.main(['automation-acceptance','--resume-report',str(tmp_path),'--preserve-possible','138'])
    assert calls == [dict(random_test=False,resume_report=tmp_path,preserve_possible=(138,))]


def test_readonly_user_rename_rebinds_same_disk_and_preserves_lock(rig,tmp_path):
    calls,_,path,cid,before = original(rig,tmp_path)
    rig[1].listing = rig[1].listing.replace('Farm-007','User label')
    calls.clear()
    result = run(rig,tmp_path,calls,resume_report=path,preserve_possible=(cid,))
    assert result['result'] == 'PASS'
    assert result['targets'][0]['name'] == result['accounts'][0]['name'] == 'User label'
    assert result['targets'][0]['historical_names'] == ['Farm-007']
    assert result['observed_name_changes'][0]['ldplayer_name_modified'] is False
    assert dict(rig[2].reward_claims(rig[0].namespace,7)[0]) == before
    assert all(c[1] == 'list2' for c in rig[1].calls)
    assert calls == [(7,'start'),(7,'feature-one',('two',)),(7,'cleanup')]


def test_rename_with_replaced_disk_cannot_preserve_exception_or_start(rig,tmp_path):
    from test_instance_pipeline import setup

    from top_heroes_auto.app.automation_fleet import run as fleet
    calls,_,path,cid,_ = original(rig,tmp_path)
    rig[1].listing = rig[1].listing.replace('Farm-007','User label')
    registry,session,_ = setup(calls)
    calls.clear()
    with pytest.raises(SafetyError):
        fleet(rig[0],tmp_path,registry=registry,session_factory=session,
            identity_reader=lambda *a:'different-disk',resume_report=path,preserve_possible=(cid,))
    assert not calls

"""Retain completed accounts without constructing their sessions."""
import json

import pytest
from test_instance_pipeline import run

from top_heroes_auto.automation.guard import SafetyError


def prior(rig, tmp_path):
    rig[1].listing += "13,another,0,0,0,-1,-1\n"
    result = run(rig, tmp_path, [])
    result['accounts'][1]['result'] = 'PARTIAL'
    result['accounts'][1]['rewards']['three']['result'] = 'UNKNOWN'
    path = tmp_path/'prior.json'
    path.write_text(json.dumps(result), encoding='utf-8')
    return path, result


def test_only_requested_unfinished_instance_executes(rig, tmp_path):
    path, old = prior(rig, tmp_path)
    calls = []
    result = run(rig, tmp_path, calls, resume_report=path, resume_indexes=(13,))
    assert calls == [(13,'start'), (13,'feature-two',('three',)), (13,'cleanup')]
    assert result['result'] == 'PASS'
    assert result['execution_indexes'] == [13] and result['retained_completed_indexes'] == [7]
    assert result['accounts'][0]['rewards'] == old['accounts'][0]['rewards']
    assert result['accounts'][0]['retained_from'] == str(path)
    assert 'session' not in result['accounts'][0] and result['accounts'][0]['new_claims'] == 0


@pytest.mark.parametrize('indexes', [(99,), (13,13), (7,), ('13',)])
def test_invalid_or_omitted_unfinished_targets_fail_before_execution(rig, tmp_path, indexes):
    path, _ = prior(rig, tmp_path)
    calls = []
    with pytest.raises(SafetyError):
        run(rig, tmp_path, calls, resume_report=path, resume_indexes=indexes)
    assert not calls


def test_scope_requires_resume_and_unchanged_retained_identity(rig, tmp_path):
    with pytest.raises(SafetyError):
        run(rig, tmp_path, [], resume_indexes=(7,))
    path, _ = prior(rig, tmp_path)
    rig[1].listing = rig[1].listing.replace('7,Farm-007', '8,Farm-007')
    calls = []
    with pytest.raises(SafetyError, match='Retained account identity'):
        run(rig, tmp_path, calls, resume_report=path, resume_indexes=(13,))
    assert not calls


def test_cli_scopes_only_explicit_resume(monkeypatch, tmp_path):
    from top_heroes_auto.app import automation_fleet, diagnostic, main
    calls = []
    monkeypatch.setattr(diagnostic,'_manager',lambda _:object())
    monkeypatch.setattr(automation_fleet,'run',lambda *a, **kw:calls.append(kw))
    with pytest.raises(ValueError):
        main.main(['automation-acceptance','--random-test','--resume-index','9'])
    assert not calls
    main.main(['automation-acceptance','--resume-report',str(tmp_path),'--resume-index','9','--preserve-possible','138'])
    assert calls[0]['resume_indexes'] == (9,) and calls[0]['preserve_possible'] == (138,)


def test_preserved_possible_on_retained_account_is_immutable(rig, tmp_path):
    from test_preserved_possible import original
    rig[1].listing += "13,another,0,0,0,-1,-1\n"
    calls, _, path, cid, row = original(rig,tmp_path)
    first = run(rig,tmp_path,calls,resume_report=path,preserve_possible=(cid,))
    first['accounts'][1]['result'] = 'PARTIAL'
    first['accounts'][1]['rewards']['three']['result'] = 'UNKNOWN'
    path.write_text(json.dumps(first),encoding='utf-8')
    calls.clear()
    result = run(rig,tmp_path,calls,resume_report=path,resume_indexes=(13,),preserve_possible=(cid,))
    assert result['result'] == 'PASS' and all(c[0] == 13 for c in calls)
    assert result['preserved_journals_unchanged']
    assert dict(rig[2].reward_claims(rig[0].namespace,7)[0]) == row


def test_external_preflight_cannot_turn_into_owned_launch(rig, tmp_path):
    from top_heroes_auto.app.instance_session import InstanceSession
    from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
    manager, process, _ = rig
    process.listing = "0,Queen,0,0,0,-1,-1\n7,Farm-007,3,4,1,201,202\n"
    manager.refresh()
    calls = []
    def recovery(*a, **kw):
        calls.append(kw)
        return RecoveryResult(RecoveryStatus.SUCCESS), tmp_path/'r', False
    target = dict(index=7,name='Farm-007',persistent_identity='disk',preflight_running=True)
    session = InstanceSession(manager,tmp_path,target,tmp_path,
        identity_reader=lambda *a:'disk',recovery_runner=recovery)
    session.start()
    assert calls[0]['allow_start'] is False
    session.close()
    assert session.report['cleanup'] == 'NOT_REQUIRED' and manager.query(7).running
    process.listing = "0,Queen,0,0,0,-1,-1\n7,Farm-007,0,0,0,-1,-1\n"
    stopped = InstanceSession(manager,tmp_path,target,tmp_path,identity_reader=lambda *a:'disk',recovery_runner=recovery)
    with pytest.raises(SafetyError,match='stopped'):
        stopped.start()
    assert len(calls)==1 and not any(c[1] in ('launch','quit') for c in process.calls)

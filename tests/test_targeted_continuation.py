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


def test_flow_scope_does_not_execute_historical_unrelated_blocker(rig, tmp_path):
    path, old = prior(rig, tmp_path)
    old['accounts'][1]['rewards']['one']['result'] = 'BLOCKED'
    path.write_text(json.dumps(old), encoding='utf-8')
    calls = []
    result = run(rig, tmp_path, calls, resume_report=path, resume_indexes=(13,),
                 resume_flows=('feature-two',))
    assert calls == [(13, 'start'), (13, 'feature-two', ('three',)), (13, 'cleanup')]
    assert result['result'] == 'PASS' and result['scope_limited']
    assert result['required_rewards'] == ['three']
    account = result['accounts'][1]
    assert account['rewards']['one'] == old['accounts'][1]['rewards']['one']
    assert account['out_of_scope_flows'] == ['feature-one']
    assert result['accounts'][0]['rewards'] == old['accounts'][0]['rewards']
    path.write_text(json.dumps(result), encoding='utf-8')
    calls.clear()
    resumed = run(rig, tmp_path, calls, resume_report=path, resume_indexes=(13,))
    assert not calls and resumed['execution_flows'] == ['feature-two']
    with pytest.raises(SafetyError, match='narrow'):
        run(rig, tmp_path, calls, resume_report=path, resume_flows=('feature-one',))
    assert not calls


@pytest.mark.parametrize('scope', [('missing',), ('feature-two', 'feature-two'), (42,)])
def test_invalid_flow_scope_rejected_before_session(rig, tmp_path, scope):
    path, _ = prior(rig, tmp_path)
    calls = []
    with pytest.raises(SafetyError):
        run(rig, tmp_path, calls, resume_report=path, resume_flows=scope)
    assert not calls


def test_flow_scope_requires_resume(rig, tmp_path):
    with pytest.raises(SafetyError):
        run(rig, tmp_path, [], resume_flows=('feature-two',))


def test_cli_passes_explicit_flow_scope(monkeypatch, tmp_path):
    from top_heroes_auto.app import automation_fleet, diagnostic, main
    calls = []
    monkeypatch.setattr(diagnostic, '_manager', lambda _: object())
    monkeypatch.setattr(automation_fleet, 'run', lambda *a, **kw: calls.append(kw))
    with pytest.raises(ValueError):
        main.main(['automation-acceptance', '--random-test', '--resume-flow', 'guild'])
    assert not calls
    main.main(['automation-acceptance', '--resume-report', str(tmp_path),
               '--resume-index', '9', '--resume-flow', 'guild', '--resume-flow', 'mail', '--refresh-flow', 'mail'])
    assert calls[0]['resume_flows'] == ('guild', 'mail')
    assert calls[0]['refresh_flows'] == ('mail',)


@pytest.mark.parametrize('refresh,expected', [(False, ('one',)), (True, ('one', 'two', 'verified'))])
def test_required_visit_rechecks_old_unavailable_without_replaying_verified(rig, tmp_path, refresh, expected):
    from dataclasses import replace

    from test_instance_pipeline import setup

    from top_heroes_auto.app.automation_fleet import execute_instance
    calls = []
    registry, session, _ = setup(calls)
    registry._flows['feature-one'] = replace(registry._flows['feature-one'],
        rewards=('one', 'two', 'verified'), refresh_current_batches=refresh)
    old = dict(recovery_ok=True, rewards={
        'one': dict(result='BLOCKED'), 'two': dict(result='NOT_AVAILABLE'),
        'verified': dict(result='SUCCESS', journal='VERIFIED', claim_id=42),
        'three': dict(result='NOT_AVAILABLE')})
    target = dict(index=7, name='Farm-007', persistent_identity='disk')
    result = execute_instance(rig[0], tmp_path, target, tmp_path/'account', registry,
        prior=old, session_factory=session, identity_reader=lambda *a: 'disk')
    assert calls == [(7, 'start'), (7, 'feature-one', expected), (7, 'cleanup')]
    assert old['rewards']['verified']['claim_id'] == 42  # Historical input proof is unchanged.
    calls.clear()
    execute_instance(rig[0], tmp_path, target, tmp_path/'next', registry,
        prior=result, session_factory=session, identity_reader=lambda *a: 'disk')
    assert not calls  # A completed feature is never reopened just for coverage.


def test_only_batch_features_opt_in_to_current_content_refresh():
    from top_heroes_auto.app.flow_registry import production_registry
    assert {f.id for f in production_registry().snapshot() if f.refresh_current_batches} == {'mail', 'events'}


def test_explicit_fresh_batch_inspection_requires_supported_scope(rig, tmp_path):
    from dataclasses import replace

    from test_instance_pipeline import setup

    from top_heroes_auto.app.automation_fleet import run as fleet_run
    calls = []
    registry, session, _ = setup(calls)
    registry._flows['feature-two'] = replace(registry._flows['feature-two'], refresh_current_batches=True)
    first = fleet_run(rig[0], tmp_path, registry=registry, session_factory=session, identity_reader=lambda *a: 'disk')
    path = tmp_path/'refresh-prior.json'
    path.write_text(json.dumps(first), encoding='utf-8')
    calls.clear()
    for args in ({'refresh_flows': ('feature-two',)},
                 {'resume_indexes': (7,), 'refresh_flows': ('feature-one',)},
                 {'resume_indexes': (7,), 'refresh_flows': ('feature-two','feature-two')}):
        with pytest.raises(SafetyError):
            fleet_run(rig[0], tmp_path, registry=registry, session_factory=session,
                identity_reader=lambda *a: 'disk', resume_report=path, **args)
    assert not calls
    result = fleet_run(rig[0], tmp_path, registry=registry, session_factory=session,
        identity_reader=lambda *a: 'disk', resume_report=path, resume_indexes=(7,),
        resume_flows=('feature-two',), refresh_flows=('feature-two',))
    assert calls == [(7,'start'), (7,'feature-two',('three',)), (7,'cleanup')]
    assert result['refresh_flows'] == ['feature-two']
    path.write_text(json.dumps(result), encoding='utf-8')
    calls.clear()
    fleet_run(rig[0], tmp_path, registry=registry, session_factory=session,
        identity_reader=lambda *a: 'disk', resume_report=path, resume_indexes=(7,))
    assert not calls  # Explicit reinspection is never inherited as an automatic replay.


@pytest.mark.parametrize('count', [1, None])
def test_final_mail_audit_cannot_hide_new_batch(count):
    from types import SimpleNamespace

    from top_heroes_auto.app.guild_mail_flows import audit_current_mail
    from top_heroes_auto.vision.guild_mail import MAIL_REWARDS
    frame = SimpleNamespace(page='mail', evidence=lambda: {'capture':'fresh'})
    tabs = {r.removeprefix('mail-'): {'count': 0} for r in MAIL_REWARDS}
    tabs['system']['count'] = count
    port = SimpleNamespace(observe_settled=lambda:frame, detector=SimpleNamespace(mail_tabs=lambda _:tabs))
    report = dict(rewards={r:dict(result='SUCCESS', journal='VERIFIED', claim_id=29) for r in MAIL_REWARDS})
    audit_current_mail(port, report)
    assert report['rewards']['mail-system']['result'] == 'CURRENT_BATCH_PENDING'
    assert report['rewards']['mail-system']['journal'] == 'VERIFIED'
    assert report['rewards']['mail-system']['claim_id'] == 29
    assert report['rewards']['mail-war']['result'] == 'SUCCESS'
    assert report['current_tab_audit']['counts']['mail-system'] == count


def test_initial_explicit_allowlist_never_dispatches_sibling_flows(rig,tmp_path):
    calls=[]
    result=run(rig,tmp_path,calls,only_flows=('feature-two',))
    assert calls == [(7,'start'),(7,'feature-two',('three',)),(7,'cleanup')]
    assert result['execution_flows']==['feature-two']
    assert result['scope_limited'] and result['explicit_flow_allowlist']==['feature-two']
    assert result['accounts'][0]['out_of_scope_flows']==['feature-one']
    path=tmp_path/'scoped.json'
    path.write_text(json.dumps(result),encoding='utf-8')
    calls.clear()
    resumed=run(rig,tmp_path,calls,resume_report=path)
    assert resumed['execution_flows']==['feature-two'] and not calls
    with pytest.raises(SafetyError):
        run(rig,tmp_path,calls,resume_report=path,only_flows=('feature-one',))
    assert not calls


@pytest.mark.parametrize('scope',[('missing',),('feature-one','feature-one')])
def test_invalid_initial_allowlist_never_starts_session(rig,tmp_path,scope):
    calls=[]
    with pytest.raises(SafetyError):
        run(rig,tmp_path,calls,only_flows=scope)
    assert not calls


def test_phase8_cli_allowlist_for_random_and_fleet(monkeypatch):
    from top_heroes_auto.app import automation_fleet, diagnostic, main
    calls=[]
    monkeypatch.setattr(diagnostic,'_manager',lambda _:object())
    monkeypatch.setattr(automation_fleet,'run',lambda *a,**kw:calls.append(kw))
    for mode in ('--random-test','--confirm-non-protected'):
        main.main(['automation-acceptance',mode,'--only-flow','PHASE_8_DYNAMIC_EVENT_REWARDS'])
    assert all(c['only_flows']==('events',) for c in calls)
    assert calls[0]['random_test'] and not calls[1]['random_test']

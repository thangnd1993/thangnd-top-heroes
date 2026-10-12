from types import SimpleNamespace

import pytest

from top_heroes_auto.app import idle_flows, task_cli
from top_heroes_auto.automation.guard import SafetyError, bound_snapshot
from top_heroes_auto.automation.idle_reward import IdleRewardResult, IdleRewardStatus
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus


def session_for(manager, path):
    return SimpleNamespace(manager=manager, index=7, name='Farm-007', data=path,
        target={'persistent_identity': 'fixture-disk-7'}, check=lambda: None,
        cancelled=lambda: False,
        snapshot=bound_snapshot(manager.store, manager.namespace, ((7, 'Farm-007'),), True))


@pytest.mark.parametrize('verified', [True, False])
@pytest.mark.parametrize('binding_ok', [True, False])
def test_conservative_prior_never_reopens_on_date_change(rig, tmp_path, monkeypatch, verified, binding_ok):
    manager, process, store = rig
    session = session_for(manager, tmp_path)
    task = store.create_task_run(manager.namespace, 'idle-reward', 7, 'Farm-007')
    claim = store.reserve_reward_claim(task, idle_flows.REWARD, idle_flows.CYCLE, '{}', not_dispatched=True)
    store.mark_reward_dispatch(claim, task)
    if verified:
        store.verify_reward_claim(claim, task, '{"independent":true}')
    with store.connect() as db:
        db.execute("UPDATE reward_claims SET reserved_at='2020-01-01T00:00:00+00:00' WHERE id=?", (claim,))
        if not binding_ok:
            db.execute("UPDATE journal_identities SET state='AMBIGUOUS' WHERE claim_id=?", (claim,))
    before = store.reward_claims(manager.namespace, 7)
    monkeypatch.setattr(idle_flows, 'run_idle_reward_diagnostic', lambda *a, **kw: pytest.fail('Redispatch'))
    result = idle_flows.run(session, tmp_path, (idle_flows.REWARD,))['rewards'][idle_flows.REWARD]
    assert result['result'] == ('ALREADY_VERIFIED' if verified and binding_ok else 'BLOCKED')
    assert not result['claim_dispatched']
    assert store.reward_claims(manager.namespace, 7) == before
    assert not process.calls


def test_shared_idle_uses_session_recovery_and_leaves_cleanup_to_outer_owner(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    process.listing = process.listing.replace('Main-Thang', 'Queen')
    manager.refresh()
    session = session_for(manager, tmp_path)
    calls = []
    session.recover = lambda: (calls.append('recover') or RecoveryResult(RecoveryStatus.SUCCESS), None, False)
    monkeypatch.setattr(task_cli, 'run_home_recovery', lambda *a, **kw: pytest.fail('Nested lifecycle'))
    task = SimpleNamespace(run=lambda *a: IdleRewardResult(IdleRewardStatus.NOT_AVAILABLE))
    result, _, started, _ = task_cli.run_idle_reward_diagnostic(
        manager, tmp_path, 7, 'Farm-007', task=task, session=session)
    assert calls == ['recover'] and not started
    assert result.recovery_result == 'SUCCESS' and result.cleanup_result == 'NOT_REQUIRED'
    assert result.journal_result == 'RELEASED' and not store.reward_claims(manager.namespace, 7)
    assert not any(c[1] in {'launch', 'quit', '-s'} for c in process.calls if len(c) > 1)


def test_shared_idle_rejects_different_session_target_before_reservation(rig, tmp_path):
    manager, _, store = rig
    session = session_for(manager, tmp_path)
    session.index = 8
    with pytest.raises(SafetyError, match='target mismatch'):
        task_cli.run_idle_reward_diagnostic(manager, tmp_path, 7, 'Farm-007', session=session)
    assert not store.reward_claims(manager.namespace, 7)


def test_protection_still_blocks_completed_idle(rig, tmp_path):
    manager, _, _ = rig
    manager.protect(7, True)
    with pytest.raises(SafetyError, match='Protected'):
        idle_flows.completed(session_for(manager, tmp_path), (idle_flows.REWARD,))


def test_legacy_completed_action_without_journal_stays_locked(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    task = store.create_task_run(manager.namespace, 'idle-reward', 7, 'old display label')
    store.finish_task_run(task, 'CLEANUP_FAILED')
    monkeypatch.setattr(idle_flows, 'run_idle_reward_diagnostic', lambda *a, **kw: pytest.fail('Legacy redispatch'))
    result = idle_flows.run(session_for(manager, tmp_path), tmp_path, (idle_flows.REWARD,))
    assert result['rewards'][idle_flows.REWARD]['journal'] == 'LEGACY_ACTION_LOCKED'
    assert not store.reward_claims(manager.namespace, 7) and not process.calls

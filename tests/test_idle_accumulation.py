import json
from types import SimpleNamespace

import pytest

from top_heroes_auto.app import idle_opportunity as policy
from top_heroes_auto.app.task_cli import DiagnosticIdleRewardPort
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import ScreenState


def prior(rig):
    manager, _, store = rig
    task = store.create_task_run(manager.namespace, policy.REWARD, 7, 'old display')
    claim = store.reserve_reward_claim(task, policy.REWARD, policy.CYCLE, '{}', not_dispatched=True)
    store.mark_reward_dispatch(claim, task)
    store.verify_reward_claim(claim, task, '{}')
    return manager, store, claim


def test_verified_empty_requires_fresh_accumulation_and_uses_previous_action_not_date(rig, monkeypatch):
    manager, store, claim = prior(rig)
    original = store.reward_claims(manager.namespace, 7)
    proof = dict(previous_claim_id=claim, persistent_identity='fixture-disk-7')
    monkeypatch.setattr(policy, 'emptied_proof', lambda *a: proof)
    cycle, returned = policy.opportunity(store, manager.namespace, 7, 'fixture-disk-7')
    assert cycle == f'idle-after-verified:{claim}' and returned == proof
    task = store.create_task_run(manager.namespace, policy.REWARD, 7, 'new display')
    new = store.reserve_reward_claim(task, policy.REWARD, cycle, json.dumps(proof), not_dispatched=True)
    store.mark_reward_dispatch(new, task)
    with pytest.raises(SafetyError, match='locked'):
        policy.opportunity(store, manager.namespace, 7, 'fixture-disk-7')
    assert store.reward_claims(manager.namespace, 7)[:1] == original


def test_missing_original_empty_and_ambiguous_history_never_reopen(rig):
    manager, store, claim = prior(rig)
    with pytest.raises(ValueError, match='proof is missing'):
        policy.opportunity(store, manager.namespace, 7, 'fixture-disk-7')
    with store.connect() as db:
        db.execute("UPDATE journal_identities SET state='AMBIGUOUS' WHERE claim_id=?", (claim,))
    with pytest.raises(SafetyError, match='AMBIGUOUS'):
        policy.opportunity(store, manager.namespace, 7, 'fixture-disk-7')


@pytest.mark.parametrize('entry,state', [(False,ScreenState.IDLE_REWARD_CLAIMABLE),
    (True,ScreenState.UNKNOWN), (True,ScreenState.IDLE_REWARD_NOT_CLAIMABLE)])
def test_new_opportunity_without_current_attention_and_green_panel_never_sends_input(entry,state):
    port = object.__new__(DiagnosticIdleRewardPort)
    detection = SimpleNamespace(state=state)
    port.latest_detection = detection
    port.observed_target = object()
    port.claim_id, port.task_run_id = 10, 10
    port.accumulation_proof = {'previous_claim_id': 1}
    port.entry_qualified = entry
    with pytest.raises(SafetyError, match='New accumulation'):
        port.tap(detection, 'idle-claim-button')


def test_claimable_frame_audited_before_one_shot_transport(rig, monkeypatch):
    manager, _, store = rig
    task = store.create_task_run(manager.namespace, policy.REWARD, 7, 'label')
    claim = store.reserve_reward_claim(task, policy.REWARD, 'idle-after-verified:1', '{}', not_dispatched=True)
    port = DiagnosticIdleRewardPort(manager, None, 7, 'label', None, claim, task)
    port.observed_target = object()
    port.latest_screen = SimpleNamespace(source_image='fresh.png', timestamp='now')
    port.latest_detection = SimpleNamespace(state=ScreenState.IDLE_REWARD_CLAIMABLE)
    port.accumulation_proof = {'previous_claim_id': 1}
    port.entry_qualified = True
    calls = []
    def dispatch(*_):
        row = store.reward_claims(manager.namespace,7)[0]
        assert json.loads(row['before_evidence'])['current_capture'] == 'fresh.png'
        store.mark_reward_dispatch(claim,task)
        calls.append('input')
    monkeypatch.setattr(port.input, 'tap_detected_target', dispatch)
    port.tap(port.latest_detection, 'idle-claim-button')
    with pytest.raises(SafetyError, match='reservation changed'):
        port.tap(port.latest_detection, 'idle-claim-button')
    assert calls == ['input']

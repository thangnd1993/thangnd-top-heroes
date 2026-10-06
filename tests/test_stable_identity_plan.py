"""Offline identity/lifecycle contracts. No real LDPlayer process or config mutation."""
import json
from dataclasses import replace

import pytest

from top_heroes_auto.app.bxh_shop_acceptance import persistent_identity
from top_heroes_auto.app.flow_registry import Flow
from top_heroes_auto.app.instance_session import InstanceSession
from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer
from top_heroes_auto.automation.execution_plan import event_terminal, terminal_plan
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError, create_snapshot
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.ldplayer.config_remediation import ConfigRemediationError, enable_authorized_adb_debug
from top_heroes_auto.ldplayer.name_safety import name_write_attempts


@pytest.mark.parametrize('label', ['B', '  中文 🌿 e\u0301, mới  '])
def test_rename_preserves_snapshot_selection_adb_and_disk(rig, label):
    manager, process, store = rig
    snapshot = create_snapshot(store, manager.namespace, manager.refresh())
    before, _ = manager.capture_verified(7, snapshot)
    identity = persistent_identity(manager, 7)
    process.listing = process.listing.replace('Farm-007', label)
    after, _ = manager.capture_verified(7, snapshot)
    assert after.name == label and after == before
    assert store.metadata(manager.namespace, 7).selected
    assert persistent_identity(manager, 7) == identity
    assert after.stable_id == before.stable_id == identity


def test_protection_rename_cannot_become_authorized(rig):
    manager, process, store = rig
    manager.protect(7, True)
    process.listing = process.listing.replace('Farm-007', 'AnythingElse')
    manager.refresh()
    assert store.metadata(manager.namespace, 7).protected
    with pytest.raises(SafetyError):
        manager.execute(7, 'verify')
    assert all(c[1] == 'list2' for c in process.calls)


def test_journal_survives_label_changes_byte_for_byte(rig):
    manager, process, store = rig
    sid = persistent_identity(manager, 7)
    task = store.create_task_run(manager.namespace, 'fixture', 7, 'stale historical label')
    cid = store.reserve_reward_claim(task, 'free', 'period', json.dumps(dict(persistent_identity=sid)),
                                     expected_instance=(7, 'current different label'), not_dispatched=True)
    store.mark_reward_dispatch(cid, task)
    original = store.reward_claims(manager.namespace, 7)
    process.listing = process.listing.replace('Farm-007', 'B')
    manager.refresh()
    assert store.reward_claims(manager.namespace, 7) == original
    with store.connect() as db:
        assert db.execute('SELECT stable_id,state FROM journal_identities WHERE claim_id=?', (cid,)).fetchone() == (sid, 'VERIFIED')
    with pytest.raises(ValueError, match='already attempted'):
        store.reserve_reward_claim(task, 'free', 'period', '{}')


@pytest.mark.parametrize('old_protected', [False, True])
def test_same_index_replaced_disk_cannot_inherit_flags_snapshot_or_journals(rig, old_protected):
    manager, process, store = rig
    snapshot = create_snapshot(store, manager.namespace, manager.refresh())
    task = store.create_task_run(manager.namespace, 'fixture', 7, 'Farm-007')
    cid = store.reserve_reward_claim(task, 'free', 'period', '{}', not_dispatched=True)
    original = store.reward_claims(manager.namespace, 7)
    manager.protect(7, old_protected)
    manager.identity_reader = lambda console, index: 'replacement' if index == 7 else f'fixture-disk-{index}'
    manager.refresh()
    meta = store.metadata(manager.namespace, 7)
    assert meta.identity_state == 'IDENTITY_CHANGED'
    assert not meta.selected and not meta.protected
    for action in ('verify', 'launch', 'quit'):
        with pytest.raises(SafetyError, match='IDENTITY_CHANGED'):
            manager.execute(7, action, snapshot=snapshot)
    with pytest.raises(ValueError, match='IDENTITY_CHANGED'):
        manager.select(7, True)
    with pytest.raises(ValueError, match='IDENTITY_CHANGED'):
        store.reserve_reward_claim(task, 'other', 'period', '{}')
    assert store.reward_claims(manager.namespace, 7) == original
    assert original[0]['id'] == cid
    # Restoring an old file/label does not reconcile a recreated generation.
    manager.identity_reader = lambda console, index: f'fixture-disk-{index}'
    manager.refresh()
    assert store.metadata(manager.namespace, 7).identity_state == 'IDENTITY_CHANGED'


def test_name_only_historical_snapshot_cannot_authorize(rig):
    manager, _, _ = rig
    with pytest.raises(SafetyError, match='IDENTITY_UNVERIFIED'):
        manager.execute(7, 'verify', snapshot=RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True))


def test_missing_disk_proof_during_run_cannot_authorize(rig):
    manager, _, store = rig
    snapshot = create_snapshot(store, manager.namespace, manager.refresh())
    manager.identity_reader = lambda *a: ''
    with pytest.raises(SafetyError, match='IDENTITY_CHANGED'):
        manager.execute(7, 'quit', snapshot=snapshot)


@pytest.mark.parametrize('command,args', [('rename', ()), ('modify', ('--name', 'B')),
                                        ('launch', ('--name', 'B')), ('quit', ('--title', 'B'))])
def test_name_write_guard_records_attempt_before_transport(rig, command, args):
    manager, process, _ = rig
    before = name_write_attempts()
    with pytest.raises(ValueError, match='read-only'):
        manager.ld._indexed(command, 7, *args)
    assert name_write_attempts() == before + 1
    assert process.calls == []


def test_config_rollback_cannot_restore_name(tmp_path):
    config, backup = tmp_path/'current.config', tmp_path/'old.config'
    config.write_text('{"statusSettings.playerName":"User name"}')
    backup.write_text('{"statusSettings.playerName":"Old name"}')
    original = config.read_bytes(), backup.read_bytes()
    with pytest.raises(ConfigRemediationError):
        enable_authorized_adb_debug(7, 'Old name', config, backup, live_name='User name', protected=False)
    assert (config.read_bytes(), backup.read_bytes()) == original


def event_detail(*, scanned=True, events=None):
    return dict(result='COMPLETE', recovery='SUCCESS', return_home='SUCCESS', exploration=dict(
        event_scan='COMPLETE' if scanned else 'NOT_STARTED', candidate_count=len(events or {}),
        observations=[dict(page='home', coverage_known=True, event_scan_performed=scanned, controls=[], capture='fresh-home')],
        events=events or {}, result='SUCCESS', return_home='SUCCESS', rewards=[], blocked=[]))


def session(rig, tmp_path, *, external=False):
    manager, _, _ = rig
    manager.select(7, False)
    flow = Flow('events', ('event-rewards',), lambda *a: None, terminal_evidence=event_terminal)
    target = dict(index=7, name='stale label', persistent_identity=persistent_identity(manager, 7),
                  preflight_running=external)
    owner = InstanceSession(manager, tmp_path, target, tmp_path, execution_plan=(flow,),
        recovery_runner=lambda *a, **kw: (RecoveryResult(RecoveryStatus.SUCCESS), tmp_path/'r.json', not external))
    owner.start()
    return owner


@pytest.mark.parametrize('submitted', [False, True])
def test_owned_home_without_event_scan_refuses_cleanup(rig, tmp_path, submitted):
    owner = session(rig, tmp_path)
    if submitted:
        owner.finish_plan({'events': event_detail(scanned=False)}, {'event-rewards': dict(result='NOT_AVAILABLE')})
    result = owner.close()
    assert result['cleanup'] == 'PREMATURE_CLEANUP'
    assert not result['cleanup_permitted_by_plan']
    assert not any(c[1] == 'quit' for c in rig[1].calls)
    assert result['selection_restored']
    assert rig[0].query(7).running


@pytest.mark.parametrize('external', [False, True])
def test_complete_zero_claim_scan_allows_only_owned_stop(rig, tmp_path, external):
    owner = session(rig, tmp_path, external=external)
    owner.finish_plan({'events': event_detail()}, {'event-rewards': dict(result='NOT_AVAILABLE')})
    result = owner.close()
    assert result['cleanup_permitted_by_plan']
    assert result['cleanup'] == ('NOT_REQUIRED' if external else 'SUCCESS')
    assert sum(c[1] == 'quit' for c in rig[1].calls) == (0 if external else 1)
    assert result['selection_restored']


def test_rename_during_session_keeps_ownership_and_updates_label(rig, tmp_path):
    owner = session(rig, tmp_path)
    rig[1].listing = rig[1].listing.replace('Farm-007', 'User B 🌿')
    owner.check()
    owner.finish_plan({'events': event_detail()}, {'event-rewards': dict(result='NOT_AVAILABLE')})
    result = owner.close()
    assert result['cleanup'] == 'SUCCESS'
    assert result['ending_display_label'] == 'User B 🌿'
    assert result['display_label_event'] == 'EXTERNAL_DISPLAY_NAME_CHANGE'
    assert result['ldplayer_name_write_attempts'] == 0


def test_pending_candidate_and_missing_flow_cannot_finish_plan():
    flow = Flow('events', ('event-rewards',), lambda *a: None, terminal_evidence=event_terminal)
    detail = event_detail(events={'a': dict(result='DISCOVERED')})
    assert not terminal_plan((flow,), {'events': detail}, {'event-rewards': dict(result='BLOCKED')})['terminal']
    assert not terminal_plan((flow,), {}, {})['terminal']


def test_blocked_event_recovers_then_processes_independent_event():
    from test_dynamic_events import Port, control, frame
    a, b = control('A', 'event'), control('B', 'event')
    reward = control('free', 'reward', cost='FREE', available=True)
    back = control('back', 'parent')
    p = Port([frame('home', 0, [a, b]), frame('UNKNOWN', 1),
              frame('home', 2, [a, b]), frame('B', 3, [reward], parent=back),
              frame('B', 4, [], parent=back), frame('home', 5, [a, b])])
    p.recover_home = lambda: dict(status='SUCCESS', report='qualified-home-recovery.json')
    result = DynamicEventExplorer().run(p)
    assert result.events['A']['result'] == 'BLOCKED'
    assert result.events['B']['result'] == 'EXHAUSTED'
    assert len(result.rewards) == 1
    assert result.event_scan == 'COMPLETE' and result.candidate_count == 2
    assert result.result == 'BLOCKED'
    assert all(call[0] != 'UNKNOWN' for call in p.calls)


def test_label_change_between_frames_does_not_change_event_transport():
    from test_dynamic_events import Port, frame
    p = Port([frame('home', 0), replace(frame('home', 1), identity=(13, 'Renamed', 'emulator-6000', 'boot'))])
    assert DynamicEventExplorer().run(p).result == 'SUCCESS'


def test_disk_recreation_changes_identity_without_config_or_name(tmp_path):
    from top_heroes_auto.ldplayer.identity import disk_identity
    console = tmp_path/'ldconsole.exe'
    disk = tmp_path/'vms/leidian9/data.vmdk'
    disk.parent.mkdir(parents=True)
    disk.write_bytes(b'fixture')
    original = disk_identity(console, 9)
    config = disk.parent/'config.json'
    config.write_text('{"statusSettings.playerName":"A"}')
    assert disk_identity(console, 9) == original
    config.write_text('{}')
    assert disk_identity(console, 9) == original
    # Keep the original file alive to prevent allocator reuse in this test.
    disk.rename(disk.with_suffix('.old'))
    disk.write_bytes(b'fixture')
    assert disk_identity(console, 9) != original


def test_ambiguous_old_journal_stays_locked_on_sidecar_migration(rig):
    manager, _, store = rig
    task = store.create_task_run(manager.namespace, 'fixture', 7, 'old label')
    cid = store.reserve_reward_claim(task, 'free', 'period', '{}')
    with store.connect() as db:
        db.execute('DELETE FROM journal_identities WHERE claim_id=?', (cid,))
    before = store.reward_claims(manager.namespace, 7)
    manager.refresh()
    with store.connect() as db:
        assert db.execute('SELECT state FROM journal_identities WHERE claim_id=?', (cid,)).fetchone() == ('AMBIGUOUS',)
    for action in (lambda: store.verify_reward_claim(cid, task, '{}'),
                   lambda: store.mark_reward_dispatch(cid, task)):
        with pytest.raises(ValueError, match='AMBIGUOUS'):
            action()
    assert store.reward_claims(manager.namespace, 7) == before


def test_boot_replacement_revokes_owned_cleanup(rig, tmp_path):
    owner = session(rig, tmp_path)
    owner.boot_id = 'ce068632-fc3e-4090-a8d7-ae8d9fe353f5'
    rig[0].ld.boot_id = lambda index: '00000000-0000-0000-0000-000000000009'
    owner.finish_plan({'events': event_detail()}, {'event-rewards': dict(result='NOT_AVAILABLE')})
    assert owner.close()['cleanup'].startswith('FAILED:')
    assert not any(c[1] == 'quit' for c in rig[1].calls)


@pytest.mark.parametrize('args', [
    ['ldconsole.exe', 'launch', '--index', '7', '--index', '0'],
    ['dnconsole.exe', 'quit', '--index', '7', '--name', 'Queen'],
    ['ldconsole.exe', 'modify', '--index', '7', '--name', 'B'],
])
def test_process_boundary_rejects_extra_target_and_name_arguments(args):
    from top_heroes_auto.app.process import CommandError, Process
    with pytest.raises(CommandError):
        Process().run(args)


def test_home_without_actual_scan_flag_cannot_finish_even_if_summary_says_complete():
    detail = event_detail()
    detail['exploration']['observations'][0]['event_scan_performed'] = False
    assert not event_terminal(detail)


def test_genuine_recovery_blocker_is_terminal_but_placeholder_is_not():
    assert event_terminal(dict(blocking_stage='before_home', recovery='ADB_ERROR', recovery_report='proof.json'))
    assert not event_terminal(dict(blocking_stage='before_home', recovery='NOT_STARTED', recovery_report='proof.json'))


def test_no_progress_branch_recovers_then_inspects_other_candidate():
    from test_dynamic_events import Port, control, frame
    a, b = control('A', 'event'), control('B', 'event')
    p = Port([frame('home', 0, [a, b]), frame('home', 1, [a, b]),
              frame('home', 2, [a, b]), frame('B', 3, [], parent=control('back', 'parent')),
              frame('home', 4, [a, b])])
    p.recover_home = lambda: dict(status='SUCCESS', report='fresh-home.json')
    result = DynamicEventExplorer().run(p)
    assert result.events['A']['result'] == 'BLOCKED'
    assert result.events['B']['result'] == 'EXHAUSTED'
    assert result.candidate_count == 2


@pytest.mark.parametrize('label', ['', '   '])
def test_empty_display_label_cannot_revoke_stable_snapshot(rig, label):
    manager, process, store = rig
    snapshot = create_snapshot(store, manager.namespace, manager.refresh())
    process.listing = process.listing.replace('Farm-007', label)
    target, _ = manager.capture_verified(7, snapshot)
    assert target.name == label and target.stable_id == 'fixture-disk-7'
    assert store.metadata(manager.namespace, 7).selected


@pytest.mark.parametrize('old_proof', [None, [], {}, 123])
def test_ambiguous_verified_legacy_reward_cannot_reopen_on_new_period(rig, old_proof):
    manager, _, store = rig
    task = store.create_task_run(manager.namespace, 'fixture', 7, 'old label')
    cid = store.reserve_reward_claim(task, 'free', 'old-period', json.dumps({'persistent_identity':old_proof}))
    store.verify_reward_claim(cid, task, 'old receipt')
    original = store.reward_claims(manager.namespace, 7)
    with store.connect() as db:
        db.execute('DELETE FROM journal_identities WHERE claim_id=?', (cid,))
    manager.refresh()
    next_task = store.create_task_run(manager.namespace, 'fixture', 7, 'new label')
    with pytest.raises(ValueError, match='AMBIGUOUS'):
        store.reserve_reward_claim(next_task, 'free', 'new-period', '{}')
    assert store.reward_claims(manager.namespace, 7) == original
    assert cid in store.identity_audit(manager.namespace)['ambiguous_journal_ids']


@pytest.mark.parametrize('exit_reason', ['unexpected_exit', 'no_progress', 'action_limit'])
def test_fresh_home_candidates_recorded_before_early_block(exit_reason):
    from dataclasses import asdict

    from test_dynamic_events import Port, control, frame

    from top_heroes_auto.automation.dynamic_events import Limits

    a, b = control('A', 'event'), control('new-B', 'event')
    start = frame('home', 0, [a])
    blocked_home = replace(frame('home', 2, [a, b]), coverage_known=False,
                           blocked=('UNQUALIFIED_NOTIFICATION_GEOMETRY',))
    frames = [start, blocked_home]
    if exit_reason == 'unexpected_exit':
        frames.insert(1, frame('A', 1, [control('child')]))
    limits = Limits(actions=1) if exit_reason == 'action_limit' else None
    port = Port(frames)
    result = DynamicEventExplorer(limits).run(port)
    assert set(result.events) == {'A', 'new-B'}
    assert result.candidate_count == 2 and result.event_scan == 'COMPLETE'
    assert result.events['new-B']['visits'] == 0
    assert result.events['new-B']['discovery_capture'] == blocked_home.capture
    assert result.events['new-B']['result'] == 'BLOCKED'
    assert result.events['new-B']['blockers']
    assert not any(call[2] == 'new-B' for call in port.calls)
    assert not result.rewards
    detail = dict(result='BLOCKED', recovery='SUCCESS', exploration=asdict(result))
    assert event_terminal(detail)  # Full scan facts + genuine blocker, never exhaustion.


def test_unscanned_home_cannot_register_or_enter_candidate():
    from dataclasses import asdict

    from test_dynamic_events import Port, control, frame

    port = Port([replace(frame('home', 0, [control('A', 'event')]), event_scan_performed=False)])
    result = DynamicEventExplorer().run(port)
    assert result.events == {} and result.event_scan == 'NOT_STARTED'
    assert result.candidate_count == 0 and not port.calls
    assert result.blocked[0]['reason'] == 'EVENT_SCAN_NOT_PERFORMED'
    assert not event_terminal(dict(result='BLOCKED', recovery='SUCCESS', exploration=asdict(result)))

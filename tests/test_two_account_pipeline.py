"""Two account workers share one lease, never mutable target state or sessions."""
import json
import threading
from types import SimpleNamespace

import pytest
from test_instance_pipeline import setup

from top_heroes_auto.app import automation_fleet as fleet
from top_heroes_auto.app.automation_ownership import (
    AutomationBusy,
    AutomationLease,
    exclusive_command,
    ownership_evidence,
)
from top_heroes_auto.app.flow_registry import Flow, FlowRegistry
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.ldplayer.client import LDPlayer


def factory(manager):
    return lambda: Manager(LDPlayer(manager.ld.installation, manager.ld.process), manager.store,
                           manager.data_dir, identity_reader=manager.identity_reader)


@pytest.mark.parametrize('count', [0, 3, True, 1.0, '2'])
def test_invalid_concurrency_never_starts_session(rig, tmp_path, count):
    calls = []
    registry, session, _ = setup(calls)
    with pytest.raises(SafetyError, match='concurrency'):
        fleet.run(rig[0], tmp_path, registry=registry, session_factory=session, max_concurrency=count)
    assert not calls


def test_two_workers_overlap_keep_identity_journals_selection_and_one_lease(rig, tmp_path):
    manager, process, store = rig
    process.listing += '13,another,0,0,0,-1,-1\n15,third,0,0,0,-1,-1\n'
    manager.refresh()
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    active = set()
    peak = 0
    leases, finished, serials = [], [], []
    parent_writes = []
    registry = FlowRegistry()

    class Session:
        def __init__(self, worker, data, target, folder, **kw):
            self.manager, self.target = worker, target
            self.index = target['index']
            self.before = store.metadata(manager.namespace, self.index).selected
            assert worker is not manager

        def start(self):
            nonlocal peak
            self.manager.select(self.index, True)
            self.manager._active = self.index
            with lock:
                active.add(self.index)
                peak = max(peak, len(active))
            if self.index in (7, 13):
                barrier.wait(timeout=10)

        def check(self):
            assert self.manager._active == self.index
            assert store.metadata(manager.namespace, self.index).selected
            assert not store.metadata(manager.namespace, self.index).protected

        def finish_plan(self, *args):
            pass

        def close(self):
            self.check()
            self.manager.select(self.index, self.before)
            with lock:
                active.remove(self.index)
                finished.append(self.index)
            return dict(cleanup='SUCCESS', selection_restored=True)

    @exclusive_command
    def probe(worker, index):
        assert worker._active == index
        evidence = ownership_evidence()
        with lock:
            leases.append(evidence['run_id'])
            serials.append((index, f'explicit-fixture-{index}'))
        with pytest.raises(AutomationBusy):
            with AutomationLease(worker.namespace, tmp_path):
                pytest.fail('second run acquired live fleet lease')

    def feature(session, folder, rewards):
        probe(session.manager, session.index)
        task = store.create_task_run(manager.namespace, 'fixture', session.index, 'display')
        claim = store.reserve_reward_claim(task, 'fixture-reward', 'period', str(folder/'before.png'))
        if session.index != 13:
            store.verify_reward_claim(claim, task, str(folder/'after.png'))
        with pytest.raises(ValueError, match='retry forbidden'):
            store.reserve_reward_claim(task, 'fixture-reward', 'period', 'retry.png')
        if session.index == 13:
            raise SafetyError('one account uncertain; independent account continues')
        return dict(rewards={'reward': dict(result='SUCCESS', journal='VERIFIED', claim_id=claim)},
                    return_home='SUCCESS')

    registry.register(Flow('fixture', ('reward',), feature))
    original_write = fleet.write

    def record(path, payload):
        if path.name == 'fleet-report.json':
            parent_writes.append(threading.current_thread())
        original_write(path, payload)

    from unittest.mock import patch
    with patch.object(fleet, 'write', record):
        result = fleet.run(manager, tmp_path, registry=registry, session_factory=Session,
                           identity_reader=lambda m, i: f'fixture-disk-{i}', max_concurrency=2,
                           manager_factory=factory(manager))
    assert peak == 2 and not active and sorted(finished) == [7, 13, 15]
    assert len(set(leases)) == 1 and leases[0] == result['automation_ownership']['run_id']
    assert all(t is threading.current_thread() for t in parent_writes)
    assert sorted(serials) == [(i, f'explicit-fixture-{i}') for i in (7, 13, 15)]
    assert [r['index'] for r in result['accounts']] == [7, 13, 15]
    assert [r['result'] for r in result['accounts']] == ['COMPLETE', 'PARTIAL', 'COMPLETE']
    assert result['all_selection_states_restored'] and result['protected_state_unchanged']
    assert not store.reward_claims(manager.namespace, 0)
    assert store.reward_claims(manager.namespace, 13)[0]['status'] == 'RESERVED'
    assert all(store.reward_claims(manager.namespace, i)[0]['status'] == 'VERIFIED' for i in (7, 15))
    assert manager._active is None
    with AutomationLease(manager.namespace, tmp_path):
        pass  # Released only after both workers' final cleanup.


@pytest.mark.parametrize('bad', ['shared', 'namespace', 'store'])
def test_invalid_worker_factory_fails_before_mutation(rig, tmp_path, bad):
    manager = rig[0]
    calls = []
    registry, session, _ = setup(calls)
    worker = manager if bad == 'shared' else factory(manager)()
    if bad == 'namespace':
        worker.namespace = 'other-installation'
    if bad == 'store':
        worker.store = SimpleNamespace(path=tmp_path/'other.sqlite3')
    with pytest.raises(SafetyError, match='separate Managers'):
        fleet.run(manager, tmp_path, registry=registry, session_factory=session,
                  identity_reader=lambda *a: 'disk', max_concurrency=2, manager_factory=lambda: worker)
    assert not calls


def test_cancelled_pending_accounts_never_start(rig, tmp_path):
    calls = []
    registry, session, _ = setup(calls)
    result = fleet.run(rig[0], tmp_path, registry=registry, session_factory=session,
                      identity_reader=lambda *a: 'disk', max_concurrency=2,
                      manager_factory=factory(rig[0]), cancelled=lambda: True)
    assert not calls
    assert result['accounts'][0]['error'] == 'Run cancelled before account dispatch.'


def test_two_worker_report_can_resume_without_replaying_completed_rewards(rig, tmp_path):
    calls = []
    registry, session, _ = setup(calls)
    result = fleet.run(rig[0], tmp_path, registry=registry, session_factory=session,
                      identity_reader=lambda *a: 'disk', max_concurrency=2, manager_factory=factory(rig[0]))
    path = tmp_path/'resume.json'
    path.write_text(json.dumps(result), encoding='utf-8')
    calls.clear()
    resumed = fleet.run(rig[0], tmp_path, registry=registry, session_factory=session,
                       identity_reader=lambda *a: 'disk', resume_report=path)
    assert not calls and resumed['result'] == 'PASS'


def test_explicit_target_disk_change_is_not_rebound(rig, tmp_path):
    calls = []
    registry, session, _ = setup(calls)
    result = fleet.run(rig[0], tmp_path, registry=registry, session_factory=session,
                      identity_reader=lambda *a: 'replacement',
                      targets=[dict(index=7, name='Farm-007', persistent_identity='original')])
    assert not calls and result['accounts'][0]['error'] == 'Original persistent identity changed.'


def test_production_worker_has_independent_transport_state(rig):
    manager = rig[0]
    worker = manager.fork_worker()
    assert worker is not manager and worker.store is manager.store
    assert worker.namespace == manager.namespace
    assert worker.ld is not manager.ld and worker.ld.process is not manager.ld.process
    assert worker.adb is not manager.adb and worker._lock is not manager._lock
    assert worker._active is None and worker.last_lifecycle_attempt is None


def test_session_construction_failure_does_not_abort_other_accounts(rig, tmp_path):
    manager, process, _ = rig
    process.listing += '13,peer,0,0,0,-1,-1\n'
    calls = []
    registry, session, _ = setup(calls)

    def create(worker, data, target, folder, **kw):
        if target['index'] == 7:
            raise SafetyError('live target binding revoked before session')
        return session(worker, data, target, folder, **kw)

    result = fleet.run(manager, tmp_path, registry=registry, session_factory=create,
        identity_reader=lambda m, i: f'fixture-disk-{i}', max_concurrency=2, manager_factory=factory(manager))
    assert [r['result'] for r in result['accounts']] == ['PARTIAL', 'COMPLETE']
    assert result['accounts'][0]['worker_terminated']
    assert not any(c[0] == 7 for c in calls)
    assert (13, 'cleanup') in calls


def test_cli_concurrency_is_explicit_and_bounded(monkeypatch):
    from top_heroes_auto.app import diagnostic, main
    calls = []
    monkeypatch.setattr(diagnostic, '_manager', lambda _: object())
    monkeypatch.setattr(fleet, 'run', lambda *a, **kw: calls.append(kw))
    main.main(['automation-acceptance', '--confirm-non-protected', '--max-concurrency', '2'])
    assert calls[0]['max_concurrency'] == 2
    with pytest.raises(SystemExit):
        main.main(['automation-acceptance', '--confirm-non-protected', '--max-concurrency', '3'])


def test_inventory_audit_allows_only_bound_peer_runtime_changes():
    from top_heroes_auto.app.diagnostic import _only_target_changed
    before = {0: ('protected', True, True), 3: ('disk3', False, False), 8: ('disk8', False, False)}
    after = dict(before, **{})
    after[8] = ('disk8', True, True)
    assert _only_target_changed(before, after, 3, peer_identities={8: 'disk8'}) == [8]
    with pytest.raises(SafetyError):
        _only_target_changed(before, after, 3)
    after[8] = ('replacement', True, True)
    with pytest.raises(SafetyError):
        _only_target_changed(before, after, 3, peer_identities={8: 'disk8'})
    after = dict(before)
    after[0] = ('protected', False, False)
    with pytest.raises(SafetyError):
        _only_target_changed(before, after, 3, peer_identities={8: 'disk8'})

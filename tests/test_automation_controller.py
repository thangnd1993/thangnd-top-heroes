"""Normal Start exercises the complete production registry through isolated workers."""
import threading
from dataclasses import replace

import pytest
from test_instance_pipeline import setup
from test_two_account_pipeline import factory

from top_heroes_auto.app import automation_controller as controller_module
from top_heroes_auto.app import automation_fleet as fleet
from top_heroes_auto.app.automation_controller import AutomationController
from top_heroes_auto.app.flow_registry import FlowRegistry, production_registry
from top_heroes_auto.app.instance_session import InstanceSession
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.storage.store import AccountStatus, RunStatus


@pytest.mark.parametrize('all_accounts,expected', [(False, [7]), (True, [7, 13])])
def test_normal_controller_runs_entire_registry(rig, tmp_path, monkeypatch, all_accounts, expected):
    manager, process, store = rig
    process.listing += '13,new display,0,0,0,-1,-1\n'
    calls = []
    _, session, feature = setup(calls)
    registry = FlowRegistry()
    production = production_registry().snapshot()
    assert {f.id for f in production} == {'idle', 'vip', 'ranking', 'shop', 'guild', 'mail', 'events'}
    for flow in production:
        registry.register(replace(flow, run=feature, completed=lambda *a: {}, terminal_evidence=lambda d: True))

    def full_path(m, data, **kw):
        assert 'only_flows' not in kw and 'enabled' not in kw
        return fleet.run(m, data, registry=registry, session_factory=session,
                         identity_reader=lambda m, i: f'fixture-disk-{i}', **kw)

    monkeypatch.setattr(controller_module, 'run_fleet', full_path)
    controller = AutomationController(store, factory(manager))
    run = controller.create(manager, 2, all_non_protected=all_accounts)
    assert [i for i, _ in run.snapshot.members] == expected
    rows = controller.execute(run)
    assert all(row[2] == AccountStatus.SUCCESS for row in rows)
    for index in expected:
        events = [call[1] for call in calls if call[0] == index]
        assert events == ['start', *[f.id for f in production], 'cleanup']
    assert not any(call[0] == 0 for call in calls)
    assert store.get(f'automation-report:{run.id}').endswith('fleet-report.json')
    with store.connect() as db:
        assert db.execute('SELECT status FROM runs WHERE id=?', (run.id,)).fetchone()[0] == RunStatus.SUCCESS


def test_per_account_cancel_does_not_cancel_peer_or_queue(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    process.listing += '13,peer,0,0,0,-1,-1\n15,next,0,0,0,-1,-1\n'
    controller = AutomationController(store, factory(manager))
    calls = []
    registry, session, _ = setup(calls)
    original = session.start

    def start(self):
        if self.target['index'] == 7:
            controller.cancel_account(7)
            assert controller.account_cancellations[7].is_set()
            assert not controller.account_cancellations[13].is_set()
            raise RuntimeError('cancelled before gameplay')
        original(self)

    session.start = start
    monkeypatch.setattr(controller_module, 'run_fleet', lambda m, data, **kw: fleet.run(
        m, data, registry=registry, session_factory=session,
        identity_reader=lambda m, i: f'fixture-disk-{i}', **kw))
    run = controller.create(manager, 2, all_non_protected=True)
    rows = controller.execute(run)
    assert {r[0]: r[2] for r in rows} == {7: AccountStatus.CANCELLED, 13: AccountStatus.SUCCESS, 15: AccountStatus.SUCCESS}
    assert all((i, 'cleanup') in calls for i in (7, 13, 15))
    assert not controller.cancelled.is_set()


@pytest.mark.parametrize('changed', [False, True])
def test_selection_restore_respects_newer_user_selection(rig, tmp_path, changed):
    manager, _, store = rig
    manager.select(7, False)
    session = InstanceSession(manager, tmp_path,
        dict(index=7, name='display', persistent_identity='fixture-disk-7'), tmp_path,
        identity_reader=lambda m, i: f'fixture-disk-{i}', recovery_runner=lambda *a, **kw:
        (RecoveryResult(RecoveryStatus.SUCCESS), tmp_path/'r', False))
    session.start()
    if changed:
        manager.select(7, False)
        manager.select(7, True)  # Same value as temporary selection, newer intent.
    report = session.close()
    assert store.metadata(manager.namespace, 7).selected is changed
    assert report['newer_selection_preserved'] is changed


def test_selection_compare_and_set_is_atomic(rig):
    manager, _, store = rig
    revision = manager.select(7, True)
    barrier = threading.Barrier(2)
    results = []

    def restore():
        barrier.wait(timeout=5)
        results.append(store.select(manager.namespace, 7, False, expected_revision=revision))

    workers = [threading.Thread(target=restore) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)
    assert sum(result is not None for result in results) == 1


def test_protection_toggle_revokes_selection_restore_token(rig):
    manager, _, _ = rig
    revision = manager.select(7, True)
    manager.protect(7, True)
    manager.protect(7, False)
    assert manager.select(7, True, expected_revision=revision) is None


def test_ui_start_uses_production_controller(rig, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from top_heroes_auto.ui.window import Window
    QApplication.instance() or QApplication([])
    manager, _, store = rig
    monkeypatch.setattr(Window, 'discover_ld', lambda self: None)
    window = Window(store, tmp_path)
    window.manager = manager
    window.instances = manager.refresh()
    window.run_scope.setCurrentIndex(1)
    window.concurrency.setValue(2)
    observed = []
    monkeypatch.setattr(window, '_queue_factory', factory(manager))
    monkeypatch.setattr(AutomationController, 'execute', lambda self, run: observed.append(run) or [])
    monkeypatch.setattr(window, 'run_job', lambda mode, work: work())
    window.start_selected()
    assert isinstance(window.run_controller, AutomationController)
    assert observed[0].max_concurrency == 2
    assert observed[0].snapshot.members == ((7, 'Farm-007'),)
    assert store.get(f'automation-temporary-selection:{observed[0].id}') == '1'
    assert window.concurrency.maximum() == 2
    assert not window.run_scope.isEnabled()
    window.close()


def test_frozen_assets_resolve_inside_bundle_without_checkout(monkeypatch, tmp_path):
    import sys

    from top_heroes_auto.vision.resources import idle_reward_template_folder, template_folder
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    assert template_folder() == tmp_path/'assets/templates'
    assert idle_reward_template_folder() == tmp_path/'assets/tasks/idle_reward'
    assert len(production_registry().snapshot()) == 7

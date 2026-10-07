"""Attach entry reuses the real registry and cannot acquire lifecycle ownership."""
import json
from types import SimpleNamespace

import pytest

from top_heroes_auto.app import event_attach as attach
from top_heroes_auto.automation.guard import SafetyError


def rows():
    return [dict(index=8, name='display', status='running', stable_id='disk', protected=False)]


def guarded(tmp_path, monkeypatch):
    live = rows()
    calls = []
    target = SimpleNamespace(serial='explicit', boot_id='boot')
    manager = SimpleNamespace(execute=lambda *a, **k: calls.append((a, k)),
                              capture_verified=lambda *a, **k: (target, b'png'))
    monkeypatch.setattr(attach, 'inventory', lambda _: live)
    return manager, live, calls, target


@pytest.mark.parametrize('action', ['launch', 'quit', 'reboot', 'open_game', 'close_game', 'packages'])
def test_attach_rejects_forbidden_operation_before_transport(tmp_path, monkeypatch, action):
    manager, live, calls, _ = guarded(tmp_path, monkeypatch)
    with attach.attach_guard(manager, live, tmp_path) as (binding, _, _):
        binding['index'] = 8
        with pytest.raises(SafetyError, match='FORBIDDEN_OPERATION'):
            manager.execute(8, action)
    assert not calls


def test_attach_forwards_one_shot_boundary_and_rejects_other_target(tmp_path, monkeypatch):
    manager, live, calls, _ = guarded(tmp_path, monkeypatch)
    def intent():
        pass
    with attach.attach_guard(manager, live, tmp_path) as (binding, _, trace):
        binding['index'] = 8
        manager.execute(8, 'tap', values=(40, 50), before_input=intent)
        assert calls[0][1]['before_input'] is intent
        assert trace[0]['outcome'] == 'DISPATCHED'
        with pytest.raises(SafetyError):
            manager.execute(9, 'tap', values=(40, 50))
    assert len(calls) == 1


@pytest.mark.parametrize('field,value', [('name', 'changed'), ('status', 'stopped'), ('protected', True)])
def test_inventory_change_stops_further_input(tmp_path, monkeypatch, field, value):
    manager, live, calls, _ = guarded(tmp_path, monkeypatch)
    with attach.attach_guard(manager, live, tmp_path) as (binding, _, _):
        binding['index'] = 8
        live[0][field] = value
        with pytest.raises(SafetyError, match='INVENTORY_CHANGED'):
            manager.execute(8, 'tap', values=(40, 50))
    assert not calls


def test_attach_boot_change_rejects_capture(tmp_path, monkeypatch):
    manager, live, _, _ = guarded(tmp_path, monkeypatch)
    with attach.attach_guard(manager, live, tmp_path) as (binding, _, _):
        binding.update(index=8, serial='explicit', boot='original-boot')
        with pytest.raises(SafetyError, match='ADB_OR_BOOT_CHANGED'):
            manager.capture_verified(8)


def test_no_running_home_candidate_never_calls_execution(rig, tmp_path, monkeypatch):
    manager, process, _ = rig
    process.listing = '0,Main,0,0,0,-1,-1\n7,Farm,0,0,0,-1,-1\n'
    monkeypatch.setattr(attach, 'execute_instance', lambda *a, **k: pytest.fail('No execution allowed'))
    result = attach.run(manager, tmp_path)
    assert result['result'] == 'PRECONDITION_NOT_READY'
    assert result['eligible_indexes'] == [] and result['selection_restored']
    assert all(c[1:] == ['list2'] for c in process.calls)


def test_single_home_target_uses_only_production_events_and_restores_selection(rig, tmp_path, monkeypatch):
    manager, process, _ = rig
    manager.select(7, False)
    monkeypatch.setattr(attach, 'persistent_identity', lambda m, i: f'fixture-disk-{i}')
    monkeypatch.setattr(attach, 'capture_home', lambda m, d, r, f: (True, dict(index=r['index'], adb='explicit', boot='boot')))
    calls = []

    def execute(m, d, target, folder, registry, **kwargs):
        assert m.store.metadata(m.namespace, target['index']).selected
        assert target['preflight_running']
        calls.append(kwargs)
        return dict(result='PARTIAL')

    monkeypatch.setattr(attach, 'execute_instance', execute)
    result = attach.run(manager, tmp_path, choice=lambda choices: choices[0])
    assert result['eligible_indexes'] == [7] and result['bound_target']['index'] == 7
    assert calls == [dict(only_flows=('events',), temporary_selection=False)]
    assert result['selection_restored'] and not manager.store.metadata(manager.namespace, 7).selected
    assert result['inventory_unchanged']
    assert all(c[1:] == ['list2'] for c in process.calls)


def test_resume_never_switches_to_another_running_account(rig, tmp_path):
    manager, process, _ = rig
    path = tmp_path/'prior.json'
    path.write_text(json.dumps(dict(mode='ATTACH_ONLY_PHASE8_ONLY', bound_target=dict(index=13))), encoding='utf-8')
    result = attach.run(manager, tmp_path, resume_report=path)
    assert result['result'] == 'BLOCKED' and 'BOUND_INSTANCE_NOT_RUNNING' in result['error']
    assert not result['actions']
    assert all(c[1:] == ['list2'] for c in process.calls)


def test_resume_unknown_screen_never_dispatches_parent(rig, tmp_path):
    manager, _, _ = rig
    row = dict(index=7, name='label', persistent_identity='fixture-disk-7')
    calls = []
    frame = SimpleNamespace(capture='fresh', page='UNKNOWN', popup=False, parent=None)
    port = SimpleNamespace(observe=lambda: frame, navigate=lambda *a: calls.append(a))
    assert not attach.resume_home(manager, row, tmp_path, lambda: None, 'saved-event',
                                  port_factory=lambda *a: port)
    assert not calls


def test_portable_entry_dispatches_to_attach_production_runner(tmp_path, monkeypatch):
    from top_heroes_auto.app import diagnostic, main

    marker = object()
    calls = []
    monkeypatch.setattr(main, 'data_directory', lambda: tmp_path)
    monkeypatch.setattr(diagnostic, '_manager', lambda _: marker)
    monkeypatch.setattr(attach, 'run', lambda *a, **k: calls.append((a, k)) or dict(result='PARTIAL'))
    assert main.main(['event-attach-acceptance', '--resume-report', str(tmp_path/'prior.json')]) == 1
    assert calls == [((marker, tmp_path), dict(resume_report=tmp_path/'prior.json'))]

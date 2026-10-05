"""OS lease tests use fixture namespaces only; no emulator or gameplay."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from top_heroes_auto.app.automation_ownership import (
    AutomationBusy,
    AutomationLease,
    exclusive_automation,
    exclusive_command,
    mutation_ownership,
)
from top_heroes_auto.storage.store import Store


def manager(tmp_path):
    return SimpleNamespace(namespace='fixture:'+str(tmp_path), data_dir=tmp_path,
                           store=Store(tmp_path/'fixture.sqlite3', recover_running=False))


def test_second_runner_blocked_and_normal_cleanup_releases(tmp_path):
    m = manager(tmp_path)
    with AutomationLease(m.namespace, tmp_path) as first:
        with pytest.raises(AutomationBusy, match='AUTOMATION_BUSY'):
            with AutomationLease(m.namespace, tmp_path):
                pytest.fail('must not own a second run')
        assert json.loads(first.path.read_text())['state'] == 'ACTIVE'
    assert json.loads(first.path.read_text())['state'] == 'RELEASED'
    with AutomationLease(m.namespace, tmp_path) as second:
        assert second.run_id != first.run_id


def test_pid_reuse_metadata_cannot_steal_live_kernel_owner(tmp_path):
    m = manager(tmp_path)
    with AutomationLease(m.namespace, tmp_path) as first:
        first.path.write_text(json.dumps(dict(pid=os.getpid(), process_token='old', state='ACTIVE')))
        with pytest.raises(AutomationBusy):
            with AutomationLease(m.namespace, tmp_path):
                pytest.fail('saved PID must not grant ownership')


def test_proven_stale_record_recovered_only_after_os_lock(tmp_path):
    m = manager(tmp_path)
    lease = AutomationLease(m.namespace, tmp_path)
    lease.path.write_text(json.dumps(dict(pid=os.getpid(), process_token='reused-pid', state='ACTIVE')))
    with lease:
        assert lease.stale_recovered
        record = json.loads(lease.path.read_text())
        assert record['run_id'] == lease.run_id and record['process_token'] != 'reused-pid'


def test_crash_releases_os_ownership_without_manual_unlock(tmp_path):
    namespace = 'fixture:'+str(tmp_path)
    script = ('from pathlib import Path; import os; '
              'from top_heroes_auto.app.automation_ownership import AutomationLease; '
              f'lease=AutomationLease({namespace!r},Path({str(tmp_path)!r})); '
              'lease.__enter__(); os._exit(17)')
    result = subprocess.run([sys.executable, '-c', script], timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    assert result.returncode == 17
    with AutomationLease(namespace, tmp_path) as recovered:
        assert recovered.active and recovered.stale_recovered


def test_exception_cleanup_releases(tmp_path):
    m = manager(tmp_path)
    with pytest.raises(ValueError):
        with mutation_ownership(m):
            raise ValueError('fake run fails')
    with AutomationLease(m.namespace, tmp_path):
        pass


def test_scoped_fleet_retains_lease_through_nested_commands(tmp_path):
    m = manager(tmp_path)
    calls = []

    @exclusive_command
    def command(manager):
        with pytest.raises(AutomationBusy):
            with AutomationLease(manager.namespace, tmp_path):
                pytest.fail('competing run during current command')
        calls.append('one guarded command')

    @exclusive_automation
    def run(manager, data, *, only_flows):
        assert only_flows == ('events',)
        command(manager)
        command(manager)
        return 'finished'

    assert run(m, tmp_path, only_flows=('events',)) == 'finished'
    assert len(calls) == 2


def test_startup_viewer_does_not_interrupt_live_tasks(tmp_path):
    m = manager(tmp_path)
    m.store.create_task_run(m.namespace, 'fixture', 23, 'name')
    viewer = Store(m.store.path, recover_running=False)
    assert viewer.latest_task_run(m.namespace,'fixture',23)[2] == 'RUNNING'
    viewer.recover_interrupted('other namespace')
    assert viewer.latest_task_run(m.namespace,'fixture',23)[2] == 'RUNNING'
    with mutation_ownership(m):
        viewer.recover_interrupted(m.namespace)
    assert viewer.latest_task_run(m.namespace,'fixture',23)[2] == 'INTERRUPTED'


def test_different_data_folders_cannot_compete_for_same_fleet(tmp_path):
    m = manager(tmp_path)
    with AutomationLease(m.namespace, tmp_path):
        with pytest.raises(AutomationBusy):
            with AutomationLease(m.namespace, tmp_path/'different-app-data'):
                pytest.fail('same namespace must remain exclusive')


def test_live_owner_in_other_process_is_blocked(tmp_path):
    namespace='fixture:'+str(tmp_path)
    script=('from pathlib import Path; '
            'from top_heroes_auto.app.automation_ownership import AutomationLease,AutomationBusy; '
            f'lease=AutomationLease({namespace!r},Path({str(tmp_path)!r})); '
            '\ntry: lease.__enter__()\nexcept AutomationBusy: raise SystemExit(19)\n'
            'lease.__exit__(None,None,None)')
    with AutomationLease(namespace,tmp_path):
        child=subprocess.run([sys.executable,'-c',script],timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        assert child.returncode==19

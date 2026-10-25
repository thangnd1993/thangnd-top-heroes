"""Run20 cost: 722-824 identity/inventory commands per account (~12-15% of wall time).

Only reads that are provably adjacent (same target, no command and no deliberate
wait in between, <250 ms) are coalesced. Every other guard still reads fresh."""
import pytest
from conftest import FakeProcess

from top_heroes_auto.app.process import Process
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation import timing
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError, bound_snapshot
from top_heroes_auto.ldplayer.client import Installation, LDPlayer
from top_heroes_auto.storage.store import Store


class Counting(FakeProcess):
    """Transport that counts commands exactly like production Process."""

    def __init__(self):
        super().__init__()
        self.command_serial = 0

    def run(self, args, timeout=20):
        self.command_serial += 1
        return super().run(args, timeout)


def make(tmp_path, process=None, window=None):
    process = process or Counting()
    store = Store(tmp_path / 'c.sqlite3')
    manager = Manager(LDPlayer(Installation(tmp_path / 'ldconsole.exe', tmp_path / 'adb.exe'), process), store,
                      tmp_path, identity_reader=lambda console, index: f'disk-{index}')
    if window is not None:
        manager.ADJACENT_INVENTORY_SECONDS = window
    manager.refresh()
    manager.protect(0, True)
    manager.select(7, True)
    process.calls.clear()
    manager._inventory_read = None  # setup reads must not warm the cache under test
    return manager, process, store


def lists(process):
    return sum(1 for c in process.calls if c[1] == 'list2')


def test_back_to_back_reads_with_no_command_between_share_one_list2(tmp_path):
    manager, process, _ = make(tmp_path)
    first = manager._target_inventory(7)
    second = manager._target_inventory(7)
    assert lists(process) == 1 and first == second


def test_any_intervening_command_forces_a_fresh_read(tmp_path):
    manager, process, _ = make(tmp_path)
    manager._target_inventory(7)
    manager.ld.adb_serial(7)  # an indexed command: the runtime may have changed
    manager._target_inventory(7)
    assert lists(process) == 2


def test_runtime_change_after_a_command_is_seen_not_hidden(tmp_path):
    manager, process, _ = make(tmp_path)
    before = manager._target_inventory(7)[0]
    process.listing = process.listing.replace('7,Farm-007,3,4,1,201,202', '7,Farm-007,0,0,0,-1,-1')
    manager.ld.adb_serial(7)
    after = manager._target_inventory(7)[0]
    assert before.running and not after.running


def test_deliberate_wait_invalidates(tmp_path):
    manager, process, _ = make(tmp_path)
    manager._target_inventory(7)
    timing.pause(lambda seconds: None, 0.01)
    manager._target_inventory(7)
    assert lists(process) == 2


def test_age_bound_and_target_scope(tmp_path, monkeypatch):
    manager, process, _ = make(tmp_path)
    manager._target_inventory(7)
    manager._target_inventory(0)  # another index is never answered from index 7's read
    assert lists(process) == 2
    manager._target_inventory(0)
    assert lists(process) == 2
    real = __import__('time').monotonic()
    monkeypatch.setattr('top_heroes_auto.app.service.time.monotonic', lambda: real + 5)
    manager._target_inventory(0)
    assert lists(process) == 3


def test_transport_that_cannot_count_commands_never_coalesces(tmp_path):
    manager, process, _ = make(tmp_path, FakeProcess())
    manager._target_inventory(7)
    manager._target_inventory(7)
    assert lists(process) == 2


def test_process_counts_every_command(monkeypatch):
    import subprocess

    class Done:
        returncode, stdout, stderr = 0, b'', b''

    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: Done())
    process = Process()
    process.run(['adb.exe', 'devices'])
    process.run(['adb.exe', 'devices'])
    assert process.command_serial == 2


def test_selection_and_protection_are_still_read_fresh_between_adjacent_reads(tmp_path):
    """The coalesced inventory must never carry a stale Protected/selected decision."""
    manager, process, store = make(tmp_path)
    snapshot = bound_snapshot(store, manager.namespace, ((7, 'Farm-007'),), False)
    manager._active = RunSnapshot(manager.namespace, tuple(m for m in snapshot.members if m[0] == 7), False,
                                  snapshot.identities)
    manager._check(7)
    with store.connect() as db:
        db.execute('UPDATE instances SET selected=0,protected=1 WHERE namespace=? AND idx=7', (manager.namespace,))
    with pytest.raises(SafetyError):
        manager._check(7)
    assert lists(process) <= 1  # the second check reused the read yet still refused


def commands_for_capture(tmp_path, window):
    manager, process, store = make(tmp_path, window=window)
    snapshot = bound_snapshot(store, manager.namespace, ((7, 'Farm-007'),), True)
    target, _ = manager.capture_verified(7, snapshot)
    capture = [c[1] for c in process.calls]
    process.calls.clear()
    manager.execute(7, 'tap', values=(10, 20), snapshot=snapshot, observed_target=target)
    return capture, [c[1] for c in process.calls]


def test_capture_and_tap_use_fewer_inventory_reads_without_dropping_any_probe(tmp_path_factory):
    """Platform-independent: absolute counts differ between Linux and Windows CI (see docs)."""
    before_capture, before_tap = commands_for_capture(tmp_path_factory.mktemp('off'), 0.0)
    after_capture, after_tap = commands_for_capture(tmp_path_factory.mktemp('on'), .25)
    print(f'COMMAND_COUNTS capture before={len(before_capture)}/{before_capture.count("list2")}list2 '
          f'after={len(after_capture)}/{after_capture.count("list2")}list2; '
          f'tap before={len(before_tap)}/{before_tap.count("list2")}list2 '
          f'after={len(after_tap)}/{after_tap.count("list2")}list2')
    assert after_capture.count('list2') < before_capture.count('list2')
    assert len(after_capture) < len(before_capture)
    # No safety-bearing identity/transport probe was removed: only adjacent inventories.
    assert [c for c in before_capture if c != 'list2'] == [c for c in after_capture if c != 'list2']
    assert [c for c in before_tap if c != 'list2'] == [c for c in after_tap if c != 'list2']
    assert after_tap.count('list2') <= before_tap.count('list2')
    assert after_tap[-1] == before_tap[-1] == '-s'  # the input itself is still last

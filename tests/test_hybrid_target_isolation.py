"""Hybrid workflow guarantees, exercised through the production Manager guard path
(indexed ADB serial + boot identity + live Protection) with a fake LDPlayer/ADB transport."""
import pytest

from top_heroes_auto.automation.guard import SafetyError, bound_snapshot


def inputs(process):
    return [c for c in process.calls if 'input' in c]


def listing_with(process, index, row):
    process.listing = '\n'.join(row if line.startswith(f'{index},') else line
                                for line in process.listing.splitlines()) + '\n'


def snapshot(manager, store):
    return bound_snapshot(store, manager.namespace, ((7, 'Farm-007'),), True)


def test_display_rename_of_target_keeps_identity_and_allows_input(rig):
    manager, process, store = rig
    snap = snapshot(manager, store)
    target, _ = manager.capture_verified(7, snap)
    listing_with(process, 7, '7,Renamed by user,3,4,1,201,202')  # user renames mid-session
    manager.execute(7, 'tap', values=(10, 20), snapshot=snap, observed_target=target)
    assert len(inputs(process)) == 1
    assert store.metadata(manager.namespace, 7).stable_id == 'fixture-disk-7'
    assert not any('--name' in c or 'rename' in c for c in process.calls)  # never written back


@pytest.mark.parametrize('unrelated', [
    '0,Main-Thang,0,0,0,-1,-1',          # user stops another instance
    '0,Queen renamed,1,2,1,101,102',     # user renames another instance
    '0,Main-Thang,1,2,1,909,910',        # another instance restarted (new PIDs)
])
def test_unrelated_instance_activity_does_not_block_the_bound_target(rig, unrelated):
    manager, process, store = rig
    snap = snapshot(manager, store)
    target, _ = manager.capture_verified(7, snap)
    listing_with(process, 0, unrelated)
    manager.execute(7, 'tap', values=(10, 20), snapshot=snap, observed_target=target)
    assert len(inputs(process)) == 1
    assert all(c[-1] != '0' or c[1] == 'list2' for c in process.calls if '--index' in c)  # no command to index 0


def test_unrelated_instance_appearing_does_not_block_the_bound_target(rig):
    manager, process, store = rig
    snap = snapshot(manager, store)
    target, _ = manager.capture_verified(7, snap)
    process.listing += '9,Brand new,0,0,0,-1,-1\n'
    manager.execute(7, 'tap', values=(10, 20), snapshot=snap, observed_target=target)
    assert len(inputs(process)) == 1


def test_wrong_indexed_adb_mapping_fails_closed_without_input(rig):
    """LDPlayer's indexed boot id and the transport's boot id disagree: a different emulator answers."""
    manager, process, store = rig
    process.device_boot = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
    with pytest.raises(SafetyError):
        manager.capture_verified(7, snapshot(manager, store))
    assert not inputs(process) and not any('screencap' in c for c in process.calls)


def test_transport_boot_change_after_screenshot_rejects_the_stale_frame(rig):
    manager, process, store = rig
    snap = snapshot(manager, store)
    target, _ = manager.capture_verified(7, snap)
    process.device_boot = process.cli_boot = '11111111-2222-3333-4444-555555555555'  # emulator rebooted
    with pytest.raises(SafetyError):
        manager.execute(7, 'tap', values=(10, 20), snapshot=snap, observed_target=target)
    assert not inputs(process)


def test_protection_is_checked_live_for_the_target_only(rig):
    manager, process, store = rig
    snap = snapshot(manager, store)
    target, _ = manager.capture_verified(7, snap)
    with store.connect() as db:  # user protects the target after the screenshot
        db.execute('UPDATE instances SET selected=0, protected=1 WHERE namespace=? AND idx=7', (manager.namespace,))
    with pytest.raises(SafetyError):
        manager.execute(7, 'tap', values=(10, 20), snapshot=snap, observed_target=target)
    assert not inputs(process)


def test_protected_unrelated_instance_never_receives_commands(rig):
    manager, process, store = rig
    assert store.metadata(manager.namespace, 0).protected
    snap = snapshot(manager, store)
    target, _ = manager.capture_verified(7, snap)
    manager.execute(7, 'tap', values=(10, 20), snapshot=snap, observed_target=target)
    assert not [c for c in process.calls if c[1:4] in (['adb', '--index', '0'], ['launch', '--index', '0'],
                                                        ['quit', '--index', '0'])]


def test_target_replaced_by_new_backing_disk_fails_closed(rig):
    manager, process, store = rig
    snap = snapshot(manager, store)
    target, _ = manager.capture_verified(7, snap)
    manager.identity_reader = lambda console, index: f'replaced-disk-{index}'
    with pytest.raises(SafetyError):
        manager.execute(7, 'tap', values=(10, 20), snapshot=snap, observed_target=target)
    assert not inputs(process)

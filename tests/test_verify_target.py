"""`diagnostic verify-target`: the read-only first step of the hybrid Windows workflow."""
from pathlib import Path

import pytest

from top_heroes_auto.app.diagnostic import verify_target_command
from top_heroes_auto.automation.guard import SafetyError

PNG = (Path(__file__).parent / 'fixtures' / 'run20' / 'vip-disabled-2.png').read_bytes()


def mutating(process):
    return [c for c in process.calls if 'input' in c or c[1] in ('launch', 'quit', 'reboot')
            or any('--name' in str(a) for a in c)]


@pytest.fixture
def real_png(rig, monkeypatch):
    manager, _, _ = rig
    monkeypatch.setattr(manager.adb, '_capture', lambda serial: PNG)
    return rig


def test_verifies_identity_transport_and_one_fresh_screenshot_without_any_mutation(real_png, tmp_path):
    manager, process, store = real_png
    before = [store.metadata(manager.namespace, i) for i in (0, 7)]
    report = verify_target_command(manager, tmp_path, 7)['verify_target']
    assert report['adb_serial'] == 'emulator-5568' and report['stable_id'] == 'fixture-disk-7'
    assert report['screen']['state'] and Path(report['screenshot']).read_bytes() == PNG
    assert {'inventory_seconds', 'identity_and_capture_seconds', 'classification_seconds', 'total_seconds'} <= set(report['stages'])
    assert not report['input_dispatched'] and not mutating(process)
    assert before == [store.metadata(manager.namespace, i) for i in (0, 7)]  # selection/Protection untouched


def test_protected_target_fails_closed_before_any_adb_command(real_png, tmp_path):
    manager, process, _ = real_png
    with pytest.raises(SafetyError, match='PROTECTED_TARGET'):
        verify_target_command(manager, tmp_path, 0)
    assert not [c for c in process.calls if c[1] == 'adb' or c[1] == '-s']


def test_stopped_target_is_reported_not_launched(real_png, tmp_path):
    manager, process, _ = real_png
    process.listing = process.listing.replace('7,Farm-007,3,4,1,201,202', '7,Farm-007,0,0,0,-1,-1')
    with pytest.raises(SafetyError, match='ADB_UNAVAILABLE'):
        verify_target_command(manager, tmp_path, 7)
    assert not mutating(process)


def test_replaced_backing_disk_fails_closed(real_png, tmp_path):
    manager, process, _ = real_png
    manager.identity_reader = lambda console, index: f'other-disk-{index}'
    with pytest.raises(SafetyError, match='TARGET_IDENTITY_AMBIGUOUS'):
        verify_target_command(manager, tmp_path, 7)
    assert not [c for c in process.calls if c[1] == '-s']


def test_display_rename_is_informational_only(real_png, tmp_path):
    manager, process, _ = real_png
    process.listing = process.listing.replace('7,Farm-007,', '7,Tên mới,')
    report = verify_target_command(manager, tmp_path, 7)['verify_target']
    assert report['display_name_informational_only'] == 'Tên mới' and report['stable_id'] == 'fixture-disk-7'
    assert not mutating(process)


def test_missing_index_and_wrong_mapping_fail_closed(real_png, tmp_path):
    manager, process, _ = real_png
    with pytest.raises(SafetyError, match='TARGET_NOT_FOUND'):
        verify_target_command(manager, tmp_path, 5)
    process.device_boot = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'  # transport answers from a different emulator
    with pytest.raises(SafetyError):
        verify_target_command(manager, tmp_path, 7)
    assert not mutating(process)


def test_cli_wires_the_read_only_subcommand():
    from top_heroes_auto.app.diagnostic import parser

    args = parser().parse_args(['verify-target', '--index', '7'])
    assert args.command == 'verify-target' and args.index == 7

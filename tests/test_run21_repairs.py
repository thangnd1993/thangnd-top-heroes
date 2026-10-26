"""Run21 repairs: transient read-only capture failure and slow ADB registration."""
import pytest

from top_heroes_auto.app.process import CommandError
from top_heroes_auto.automation.guard import SafetyError


def _timeout():
    return CommandError("Command ['adb', '-s', 'emulator-5568', 'exec-out', 'screencap', '-p'] timed out")


def test_single_screencap_timeout_retries_same_verified_target(rig):
    manager, process, _ = rig
    manager.CAPTURE_RETRY_DELAY = 0
    manager.IDENTITY_PROBE_DELAY = 0
    failures = []

    def hook(args):
        if 'screencap' in args and not failures:
            failures.append(args)
            raise _timeout()

    process.hook = hook
    target, png = manager.capture_verified(7)
    assert png.startswith(b'\x89PNG') and target.serial == 'emulator-5568'
    screencaps = [c for c in process.calls if 'screencap' in c]
    assert len(screencaps) == 2 and all(c[2] == 'emulator-5568' for c in screencaps)
    assert not any(c[1] in {'launch', 'quit', 'reboot', 'kill-server'} or 'input' in c for c in process.calls)


def test_persistent_screencap_failure_is_bounded(rig):
    manager, process, _ = rig
    manager.CAPTURE_RETRY_DELAY = 0
    manager.IDENTITY_PROBE_DELAY = 0

    def hook(args):
        if 'screencap' in args:
            raise _timeout()

    process.hook = hook
    with pytest.raises(CommandError):
        manager.capture_verified(7)
    assert len([c for c in process.calls if 'screencap' in c]) == manager.CAPTURE_ATTEMPTS == 2


@pytest.mark.parametrize('change', ['pid', 'disk', 'selection', 'boot'])
def test_changed_target_between_screencap_attempts_fails_closed(rig, change):
    manager, process, store = rig
    manager.CAPTURE_RETRY_DELAY = 0
    manager.IDENTITY_PROBE_DELAY = 0

    def hook(args):
        if 'screencap' in args:
            if change == 'pid':
                process.listing = process.listing.replace('201,202', '901,902')
            elif change == 'disk':
                manager.identity_reader = lambda *a: 'replacement-disk'
            elif change == 'selection':
                store.select(manager.namespace, 7, False)
            else:
                process.device_boot = 'c86845e1-b195-485a-ade1-2a2be060da1e'
            raise _timeout()

    process.hook = hook
    with pytest.raises(SafetyError):
        manager.capture_verified(7)
    assert len([c for c in process.calls if 'screencap' in c]) == 1


def test_stop_during_screencap_retry_prevents_second_capture(rig):
    manager, process, _ = rig
    manager.CAPTURE_RETRY_DELAY = 0
    manager.cancelled = lambda: any('screencap' in c for c in process.calls)

    def hook(args):
        if 'screencap' in args:
            raise _timeout()

    process.hook = hook
    with pytest.raises(SafetyError, match='cancelled'):
        manager.capture_verified(7)
    assert len([c for c in process.calls if 'screencap' in c]) == 1


def test_slow_cold_transport_registration_outlasts_old_34_second_window(rig, monkeypatch):
    """Run20/21 #8/#11: transport absent ~34s; a later registration must resolve."""
    manager, process, _ = rig
    manager.IDENTITY_PROBE_DELAY = 0
    manager.POLL_INTERVAL = 1
    clock = [1000.0]
    monkeypatch.setattr('top_heroes_auto.app.service.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('top_heroes_auto.app.service.pause', lambda sleep, seconds: clock.__setitem__(0, clock[0] + seconds))
    ready_at = 1000.0 + 55.0
    absent = 'List of devices attached\n'
    present = 'List of devices attached\nemulator-5568\tdevice\n'
    good_boot = process.cli_boot
    process.cli_boot = ''

    def hook(args):
        # Every sample costs time like the real indexed adb/devices commands.
        clock[0] += 0.5
        ready = clock[0] >= ready_at
        process.devices_output = present if ready else absent
        process.cli_boot = good_boot if ready else ''

    process.hook = hook
    assert 'emulator-5568' in manager.execute(7, 'verify')
    assert clock[0] - 1000.0 > 34
    assert not any(c[1] in {'launch', 'quit', 'reboot', 'kill-server'} for c in process.calls)


def test_transport_wait_stops_on_user_stop_without_lifecycle(rig, monkeypatch):
    manager, process, _ = rig
    manager.IDENTITY_PROBE_DELAY = 0
    manager.POLL_INTERVAL = 0
    process.devices_output = 'List of devices attached\n'
    process.cli_boot = ''
    samples = []
    original = process.run

    def run(args, timeout=20):
        if args[1:] == ['devices']:
            samples.append(args)
        return original(args, timeout)

    process.run = run
    manager.cancelled = lambda: len(samples) >= 3
    with pytest.raises(SafetyError, match='cancelled'):
        manager.execute(7, 'verify')
    assert len(samples) == 3
    assert not any(c[1] in {'launch', 'quit', 'reboot', 'kill-server', 'connect'} for c in process.calls)


def test_default_resolution_window_is_longer_than_observed_failure():
    from top_heroes_auto.app.service import Manager
    assert Manager.ADB_RESOLVE_TIMEOUT >= 90

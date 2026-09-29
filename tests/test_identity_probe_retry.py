"""Only bounded read probes may retry; target/input identity never weakens."""
import pytest

from top_heroes_auto.adb.client import BootIdentityUnavailable
from top_heroes_auto.automation.guard import SafetyError


@pytest.mark.parametrize('channel',['serial','indexed-boot','direct-boot'])
def test_transient_probe_uses_same_exact_target(rig,channel):
    manager,process,_ = rig
    manager.IDENTITY_PROBE_DELAY = 0
    attempts = 0
    def hook(args):
        nonlocal attempts
        matched = ((channel == 'serial' and args[-1] == 'get-serialno') or
                   (channel == 'indexed-boot' and args[1] == 'adb' and args[-1] != 'get-serialno') or
                   (channel == 'direct-boot' and args[1] == '-s' and args[-1].endswith('boot_id')))
        if matched:
            attempts += 1
            if channel == 'serial':
                process.serial = '' if attempts == 1 else 'emulator-5568'
            else:
                if attempts == 1:
                    raise BootIdentityUnavailable('temporary empty boot read')
    process.hook = hook
    assert 'emulator-5568' in manager.execute(7,'verify')
    assert attempts >= 2
    assert all(c[2] == 'emulator-5568' for c in process.calls if c[1] == '-s')
    assert not any(c[1] in {'launch','quit','kill-server'} for c in process.calls)


def test_persistent_direct_probe_has_strict_bound(rig):
    manager,process,_ = rig
    manager.IDENTITY_PROBE_DELAY = 0
    process.device_boot = ''
    with pytest.raises(BootIdentityUnavailable):
        manager.execute(7,'tap',values=(10,20))
    reads = [c for c in process.calls if c[1] == '-s']
    assert len(reads) == 3 and all(c[-1].endswith('boot_id') for c in reads)


@pytest.mark.parametrize('change',['pid','protection','selection','name'])
def test_target_change_during_probe_cannot_retry_input(rig,change):
    manager,process,store = rig
    manager.IDENTITY_PROBE_DELAY = 0
    reads = 0
    def hook(args):
        nonlocal reads
        if args[1] == '-s' and args[-1].endswith('boot_id'):
            reads += 1
            if change == 'pid':
                process.listing = process.listing.replace('201,202','901,902')
            elif change == 'name':
                process.listing = process.listing.replace('Farm-007','Changed')
            elif change == 'protection':
                store.protect(manager.namespace,7,True)
            else:
                store.select(manager.namespace,7,False)
            raise BootIdentityUnavailable('temporarily empty')
    process.hook = hook
    with pytest.raises(SafetyError):
        manager.execute(7,'tap',values=(10,20))
    assert reads == 1 and not any('input' in c for c in process.calls)


def test_nonempty_ambiguous_serial_is_not_retried(rig):
    manager,process,_ = rig
    process.serial = 'emulator-5568\nemulator-5570'
    with pytest.raises(SafetyError):
        manager.execute(7,'verify')
    assert len([c for c in process.calls if c[-1] == 'get-serialno']) == 1


def test_valid_mismatched_boot_is_not_transient(rig):
    manager,process,_ = rig
    process.device_boot = 'c86845e1-b195-485a-ade1-2a2be060da1e'
    with pytest.raises(SafetyError,match='không khớp'):
        manager.execute(7,'tap',values=(10,20))
    assert len([c for c in process.calls if c[1] == '-s']) == 1

from dataclasses import replace

import pytest

from top_heroes_auto.app.instance_session import InstanceSession
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus


def test_stop_during_identity_probe_prevents_input_and_journal_intent(rig):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    stopped = False
    manager.cancelled = lambda: stopped
    def hook(args):
        nonlocal stopped
        if '/proc/sys/kernel/random/boot_id' in args:
            stopped = True
    process.hook = hook
    intents=[]
    with pytest.raises(SafetyError,match='cancelled'):
        manager.execute(7,'tap',values=(10,10),observed_target=target,
                        before_input=lambda:intents.append(True))
    assert not intents
    assert not any('input' in args for args in process.calls)


def test_cached_capture_avoids_global_discovery_but_reverifies_explicit_boot(rig):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    process.calls.clear()
    current, _ = manager.capture_verified(7,observed_target=target)
    assert current==target
    assert not any('devices' in args or 'start-server' in args for args in process.calls)
    assert any('/proc/sys/kernel/random/boot_id' in args for args in process.calls)
    process.device_boot='another-boot'
    with pytest.raises(SafetyError):
        manager.capture_verified(7,observed_target=target)


@pytest.mark.parametrize('field,value',[('index',0),('stable_id','replacement'),('boot_id','new-boot')])
def test_cached_capture_rejects_changed_identity(rig,field,value):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    process.calls.clear()
    with pytest.raises(SafetyError):
        manager.capture_verified(7,observed_target=replace(target,**{field:value}))
    assert not any('screencap' in args for args in process.calls)


def test_ended_runtime_does_not_keep_our_temporary_selection(rig,tmp_path):
    manager, process, store = rig
    manager.select(7,False)
    session=InstanceSession(manager,tmp_path,dict(index=7,name='display',persistent_identity='fixture-disk-7'),
        tmp_path,identity_reader=lambda *a:'fixture-disk-7',
        recovery_runner=lambda *a,**k:(RecoveryResult(RecoveryStatus.SUCCESS),tmp_path/'r',False))
    session.start()
    process.listing='0,Queen,0,0,0,-1,-1\n7,renamed by user,0,0,0,-1,-1\n'
    process.calls.clear()
    report=session.close()
    assert report['selection_restored'] and not store.metadata(manager.namespace,7).selected
    assert not any(args[1] in {'launch','quit','adb'} for args in process.calls)

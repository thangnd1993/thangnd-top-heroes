"""No emulator: exact process/readiness reacquisition and no lifecycle fallback."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.ldplayer.client import Instance


def instance():
    return Instance(23,'Unicode account',False,101,202,1280,720,240)


def test_transient_readiness_same_runtime_readonly(monkeypatch):
    original=instance()
    states=iter([original,replace(original,android_started=True)])
    monkeypatch.setattr('top_heroes_auto.app.service.time.sleep',lambda _:None)
    m=SimpleNamespace(_check=lambda index:next(states),IDENTITY_PROBE_DELAY=.2)
    assert Manager._capture_ready(m,23).android_started


@pytest.mark.parametrize('changes',[{'pid':303},{'vbox_pid':303},{'stable_id':'replacement'},{'pid':0,'vbox_pid':0}])
def test_readiness_changed_runtime_fails_closed(monkeypatch,changes):
    original=instance()
    states=iter([original,replace(original,android_started=True,**changes)])
    monkeypatch.setattr('top_heroes_auto.app.service.time.sleep',lambda _:None)
    m=SimpleNamespace(_check=lambda index:next(states),IDENTITY_PROBE_DELAY=.2)
    with pytest.raises(SafetyError):
        Manager._capture_ready(m,23)


def test_persistent_readiness_bounded(monkeypatch):
    calls=[]
    def query(index):
        calls.append(index)
        return instance()
    monkeypatch.setattr('top_heroes_auto.app.service.time.sleep',lambda _:None)
    m=SimpleNamespace(_check=query,IDENTITY_PROBE_DELAY=.2)
    with pytest.raises(SafetyError,match='readiness remained'):
        Manager._capture_ready(m,23)
    assert calls==[23,23,23]


def test_resolver_cannot_replace_runtime_after_readiness(rig,monkeypatch):
    manager,process,_=rig
    original=manager._resolve
    def resolve(index):
        target=original(index)
        process.listing=process.listing.replace('201,202','301,302')
        return target
    monkeypatch.setattr(manager,'_resolve',resolve)
    with pytest.raises(SafetyError):
        manager.capture_verified(7)
    assert not any('screencap' in command for command in process.calls)

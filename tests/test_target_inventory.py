from dataclasses import replace

import pytest

from top_heroes_auto.automation.guard import SafetyError, bound_snapshot


def test_target_query_never_rechecks_unrelated_disks_or_revokes_peer_selection(rig):
    manager,process,store=rig
    process.listing+='8,Peer,0,0,0,-1,-1\n'
    manager.refresh()
    store.select(manager.namespace,8,True)
    reads=[]
    def identity(console,index):
        reads.append(index)
        assert index==7
        return 'fixture-disk-7'
    manager.identity_reader=identity
    process.listing='7,renamed display,3,4,1,201,202\n'
    assert manager.query(7).name=='renamed display'
    assert reads==[7]
    peer=store.metadata(manager.namespace,8)
    assert not peer.protected and peer.selected
    assert peer.identity_state=='VERIFIED'
    assert store.metadata(manager.namespace,0).protected


def test_every_bound_capture_reads_current_target_disk_and_runtime(rig):
    manager,process,store=rig
    snapshot=bound_snapshot(store,manager.namespace,((7,'display'),),True)
    reads=[]
    def identity(console,index):
        reads.append(index)
        return 'fixture-disk-7'
    manager.identity_reader=identity
    target,_=manager.capture_verified(7,snapshot)
    reads.clear()
    manager.capture_verified(7,snapshot,observed_target=target)
    assert reads and set(reads)=={7}
    manager.identity_reader=lambda *a:'replacement'
    process.calls.clear()
    with pytest.raises((SafetyError,ValueError),match='IDENTITY_CHANGED'):
        manager.capture_verified(7,snapshot,observed_target=target)
    assert not any('screencap' in c or 'input' in c for c in process.calls)


def test_partial_merge_never_marks_other_instances_absent(rig):
    manager,_,store=rig
    target=manager.query(7)
    before=store.metadata(manager.namespace,0)
    store.merge(manager.namespace,(replace(target,name='new label'),),complete=False)
    assert store.metadata(manager.namespace,0)==before
    assert store.metadata(manager.namespace,7).selected
    store.merge(manager.namespace,(target,))
    assert not store.metadata(manager.namespace,0).protected


def test_missing_target_fails_without_selecting_a_peer(rig):
    manager,process,store=rig
    snapshot=bound_snapshot(store,manager.namespace,((7,'display'),),True)
    process.listing='0,Main,1,2,1,101,102\n'
    with pytest.raises(SafetyError,match='missing'):
        manager.capture_verified(7,snapshot)
    assert not any('input' in c or 'screencap' in c for c in process.calls)


def test_missing_title_skips_detail_but_still_checks_shared_close(monkeypatch,tmp_path):
    from top_heroes_auto.vision.models import AnchorEvidence, NormalizedRect, ScreenState, VisualAnchor
    from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
    anchors=tuple(VisualAnchor(name,ScreenState.EVENT_PROMO,tmp_path/'x.png',NormalizedRect(0,0,1,1),.98)
        for name in ('sample-close','sample-title','sample-detail'))
    calls=[]
    def match(screen,anchor):
        calls.append(anchor.id)
        return AnchorEvidence(anchor.id,anchor.state,1 if anchor.id.endswith('close') else 0,
                              .98,anchor.id.endswith('close'))
    monkeypatch.setattr('top_heroes_auto.vision.recovery_detector.unique_current_anchor',match)
    result=RecoveryScreenDetector._paired(None,anchors,always=('sample-close',))
    assert calls==['sample-title','sample-close']
    assert not all(e.matched for e in result)

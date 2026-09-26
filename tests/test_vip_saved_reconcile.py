"""Original-task VIP post-state proof only; no emulator/transport available."""
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.free_reward_tasks import _load_profile_details
from top_heroes_auto.app.vip_gift import gift_profile
from top_heroes_auto.app.vip_gift_reconcile import reconcile_saved_vip_gift
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.phase6_visual import FrameRewardAdapter
from top_heroes_auto.automation.reward_journal import evidence_json
from top_heroes_auto.storage.store import Store
from top_heroes_auto.vision.screenshot import ScreenshotService


@pytest.mark.parametrize('bad',[None,'claimable_after','wrong_boot','stale','wrong_tap','not_dispatched','protected','foreign_folder','changed_identity','missing_identity'])
def test_saved_upper_claim_never_replayed(tmp_path,bad):
    store=Store(tmp_path/'claims.sqlite3')
    store.merge('test',[SimpleNamespace(index=23,name='exact')])
    task=store.create_task_run('test','vip-reward',23,'exact')
    profile,_=_load_profile_details('vip-reward')
    adapter=FrameRewardAdapter(gift_profile(profile))
    fixtures=Path(__file__).parent/'fixtures/phase6_vip'
    def save(filename,folder):
        data=(fixtures/filename).read_bytes()
        return ScreenshotService(lambda _:data).take(Target(23,'exact','explicit','boot'),folder)
    before=adapter.observe(save('index2-vip-claimable.png',tmp_path/'upper-gift'))
    after=save('index2-vip-claimable.png' if bad=='claimable_after' else 'soup-vip-unavailable.png',tmp_path)
    meta_path=after.source_image.with_suffix('.json')
    meta=json.loads(meta_path.read_text(encoding='utf-8'))
    if bad=='stale':
        timestamp=(datetime.fromisoformat(before.captured.timestamp)+timedelta(minutes=5)).isoformat()
        meta['timestamp']=timestamp
        after=replace(after,timestamp=timestamp)
        meta_path.write_text(json.dumps(meta),encoding='utf-8')
    if bad=='wrong_boot':
        after=replace(after,boot_id='different')
    b=json.loads(evidence_json(before.screen))
    claim=store.reserve_reward_claim(task,'vip-upper-gift','original',json.dumps(b),not_dispatched=True)
    store.mark_reward_dispatch(claim,task)
    core=before.evidence['claim'].device_box
    report=dict(task_run_id=task,upper_gift=dict(claim_id=claim,claim_dispatched=bad!='not_dispatched',before=b,
        geometry=dict(claim_bbox=vars(core),tap_point_adb=[1,1] if bad=='wrong_tap' else list(core.center))),
        before_evidence=json.loads(evidence_json(adapter.observe(after).screen)))
    if bad=='foreign_folder':
        report['before_evidence']['capture_id']=str(tmp_path/'foreign'/after.source_image.name)
    path=tmp_path/'account-report.json'
    path.write_text(json.dumps(report),encoding='utf-8')
    store.finish_task_run(task,'PARTIAL',report_path=str(path))
    if bad=='protected':
        store.protect('test',23,True)
    if bad=='changed_identity':
        store.merge('test',[SimpleNamespace(index=23,name='changed')])
    if bad=='missing_identity':
        with store.connect() as db:
            db.execute('DELETE FROM instances')
    if bad:
        with pytest.raises((ValueError,SafetyError)):
            reconcile_saved_vip_gift(store,claim)
    else:
        proof=reconcile_saved_vip_gift(store,claim)
        assert proof['result']=='VERIFIED' and proof['claim_redispatched'] is False
        with pytest.raises(ValueError):
            reconcile_saved_vip_gift(store,claim)
    rows=store.reward_claims('test',23)
    assert len(rows)==1 and rows[0]['status']==('RESERVED' if bad else 'VERIFIED')

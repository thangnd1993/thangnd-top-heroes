"""Offline VIP upper-gift proof from its original interrupted task; no transport."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from top_heroes_auto.app.free_reward_tasks import _load_profile_details
from top_heroes_auto.app.vip_gift import gift_profile, gift_state
from top_heroes_auto.automation.fixed_reward_reconcile import saved_frame
from top_heroes_auto.automation.phase6_visual import FrameRewardAdapter
from top_heroes_auto.automation.reward_journal import evidence_json
from top_heroes_auto.automation.vip_geometry import validate_vip_claim_geometry


def reconcile_saved_vip_gift(store, claim_id):
    with store.connect() as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM reward_claims WHERE id=?', (claim_id,)).fetchone()
        if (not row or row['reward_id'] != 'vip-upper-gift' or row['status'] != 'RESERVED'
                or row['dispatch_state'] != 'POSSIBLE'):
            raise ValueError('An original uncertain VIP upper-gift claim is required.')
        task = db.execute('SELECT * FROM task_runs WHERE id=?', (row['task_run_id'],)).fetchone()
        identity = db.execute('SELECT name,protected FROM instances WHERE namespace=? AND idx=?',
                              (row['namespace'],row['instance_index'])).fetchone()
    if not task or (task['namespace'],task['instance_index'],task['task']) != (
            row['namespace'],row['instance_index'],'vip-reward'):
        raise ValueError('Original VIP task ownership mismatch.')
    if not identity or identity['protected'] or identity['name'] != row['instance_name']:
        raise ValueError('Protected, missing or changed journal identity cannot be reconciled.')
    path = Path(task['report_path']).resolve()
    report = json.loads(path.read_text(encoding='utf-8'))
    upper = report['upper_gift']
    before = json.loads(row['before_evidence'])
    # The production runner captures this AFTER upper-gift handling, BEFORE the
    # independent green reward. No caller-supplied newer screenshot is accepted.
    after = report['before_evidence']
    if (upper.get('claim_id') != claim_id or upper.get('claim_dispatched') is not True
            or upper.get('before') != before or report['task_run_id'] != row['task_run_id']):
        raise ValueError('Original one-shot upper-gift dispatch is not proven.')
    profile, _ = _load_profile_details('vip-reward')
    adapter = FrameRewardAdapter(gift_profile(profile))
    frames, times = [], []
    for evidence, folder in ((before,path.parent/'upper-gift'),(after,path.parent)):
        if any(evidence[k] != before[k] for k in ('index','name','adb_target','boot_id')):
            raise ValueError('Original target/boot changed.')
        if (evidence['index'],evidence['name']) != (row['instance_index'],row['instance_name']):
            raise ValueError('Original journal identity mismatch.')
        timestamp = evidence['detection']['timestamp']
        image = Path(evidence['capture_id']).resolve()
        if image.parent != folder.resolve():
            raise ValueError('Capture does not belong to the original VIP task.')
        meta = json.loads(image.with_suffix('.json').read_text(encoding='utf-8'))
        delay = datetime.fromisoformat(timestamp)-datetime.fromisoformat(meta['timestamp'])
        if not timedelta(0) <= delay < timedelta(seconds=2):
            raise ValueError('Original capture timestamp mismatch.')
        captured = saved_frame(dict(capture=str(image), timestamp=timestamp,
            index=evidence['index'], name=evidence['name'], adb=evidence['adb_target'],
            boot_id=evidence['boot_id']), folder)
        frames.append(adapter.observe(captured))
        times.append(datetime.fromisoformat(meta['timestamp']))
    if not timedelta(0) < times[1]-times[0] <= timedelta(seconds=60):
        raise ValueError('Post-state is outside the original action window.')
    if gift_state(frames[0].screen) != 'FREE_CLAIMABLE' or gift_state(frames[1].screen) != 'NOT_AVAILABLE':
        raise ValueError('Independent claimable-to-inactive gift change is not proven.')
    core, paid = (frames[0].evidence[role] for role in ('claim','paid'))
    geometry = upper['geometry']
    if not core.matched or not paid.matched or not core.device_box or not paid.device_box:
        raise ValueError('Original target/paid geometry is not qualified.')
    point = tuple(geometry['tap_point_adb'])
    validate_vip_claim_geometry(core.device_box,point,(paid.device_box,))
    if point != core.device_box.center or geometry['claim_bbox'] != vars(core.device_box):
        raise ValueError('Original dispatched point differs from the visual target.')
    proof = dict(method='original_vip_upper_dispatch_and_same_task_inactive_gift',
        claim_id=claim_id, task_run_id=row['task_run_id'], claim_redispatched=False,
        before=json.loads(evidence_json(frames[0].screen)),
        after=json.loads(evidence_json(frames[1].screen)))
    store.verify_reward_claim(claim_id,row['task_run_id'],json.dumps(proof,ensure_ascii=False))
    result = dict(result='VERIFIED',**proof)
    (path.parent/f'saved-reconciliation-{claim_id}.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

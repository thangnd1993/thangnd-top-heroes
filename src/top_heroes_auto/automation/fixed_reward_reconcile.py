"""Observation-only completion of a recently dispatched fixed reward receipt."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

from top_heroes_auto.adb.client import Target
from top_heroes_auto.vision.fixed_rewards import ALL_REWARDS as REWARDS
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.screenshot import ScreenshotService


def saved_frame(evidence, folder):
    path = Path(evidence['capture']).resolve()
    if path.parent != folder.resolve() or path.suffix != '.png':
        raise ValueError('Receipt capture must belong to the reserving task folder.')
    metadata = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    if (metadata['instance']['index'], metadata['instance']['name'], metadata['adb_target'], metadata['boot_id']) != (
            evidence['index'], evidence['name'], evidence['adb'], evidence['boot_id']):
        raise ValueError('Saved capture identity mismatch.')
    raw = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), 1)
    if metadata['rotated_from_portrait']:
        raw = cv2.rotate(raw, cv2.ROTATE_90_COUNTERCLOCKWISE)
    target = Target(evidence['index'], evidence['name'], evidence['adb'], evidence['boot_id'])
    frame = ScreenshotService(lambda _: cv2.imencode('.png', raw)[1].tobytes()).take(target)
    return replace(frame, source_image=path, timestamp=evidence['timestamp'])


def reconcile_fixed_reward(store, row, detector, current, identity):
    """Receipt alone never verifies; require saved AVAILABLE and fresh empty slot.

    No transport is available here. A changed boot is permitted only after the
    caller has reverified the same persistent disk and explicit ADB association.
    Freshness applies to the current observation, not to time spent waiting for
    repair/CI. The original receipt must immediately follow its claimable frame.
    """
    reward_id = row['reward_id']
    if (reward_id not in REWARDS or row['status'] != 'RESERVED'
            or row['dispatch_state'] != 'POSSIBLE'):
        return None
    before = json.loads(row['before_evidence'])
    if before.get('persistent_identity') != identity:
        return None
    if detector.availability(current, reward_id)[0] != 'NOT_AVAILABLE':
        return None
    age = datetime.now(timezone.utc) - datetime.fromisoformat(current.captured.timestamp)
    if not timedelta(0) <= age < timedelta(seconds=30):
        return None
    with store.connect() as db:
        task = db.execute('SELECT namespace,instance_index,task,report_path FROM task_runs WHERE id=?',
                          (row['task_run_id'],)).fetchone()
    if not task or tuple(task[:3]) != (row['namespace'], row['instance_index'], 'bxh-shop-fixed'):
        return None
    path = Path(task[3])
    report = json.loads(path.read_text(encoding='utf-8'))
    reward = report['rewards'][reward_id]
    if (report.get('persistent_identity') != identity or reward.get('claim_id') != row['id']
            or reward.get('claim_dispatched') is not True or reward['before']['capture'] != before['capture']):
        return None
    receipt = reward.get('after') or reward.get('immediate_after')
    if not receipt or (receipt['index'], receipt['adb'], receipt['boot_id']) != (
            before['index'], before['adb'], before['boot_id']):
        return None
    if (current.captured.index, current.captured.serial) != (before['index'], before['adb']):
        return None
    if not datetime.fromisoformat(before['timestamp']) < datetime.fromisoformat(receipt['timestamp']) < datetime.fromisoformat(current.captured.timestamp):
        return None
    if datetime.fromisoformat(receipt['timestamp']) - datetime.fromisoformat(before['timestamp']) > timedelta(seconds=60):
        return None
    original = detector.observe(saved_frame(before, path.parent))
    popup = detector.recovery.detect(saved_frame(receipt, path.parent))
    anchors = {e.anchor_id for e in popup.evidence}
    qualified = anchors == {'ranking-receipt-title', 'ranking-receipt-gem', 'ranking-receipt-continue'} if reward_id == 'ranking-chest' else anchors in (
        {'receipt-title', 'receipt-continue'}, {'receipt-title', 'receipt-continue-dim'})
    if (detector.availability(original, reward_id)[0] != 'AVAILABLE'
            or popup.state != ScreenState.REWARD_RECEIPT or not qualified):
        return None
    proof = dict(method='saved_available_and_receipt_then_fresh_unavailable',
                 original_claim_id=row['id'], original_task_run_id=row['task_run_id'],
                 persistent_identity=identity, before=original.evidence(),
                 receipt=popup.as_dict(), after=current.evidence(), claim_redispatched=False)
    store.verify_reward_claim(row['id'], row['task_run_id'], json.dumps(proof, ensure_ascii=False))
    return proof

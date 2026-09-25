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
    matches = [r for key, r in report['rewards'].items() if r.get('action_reward_id', key) == reward_id]
    if len(matches) != 1:
        return None
    reward = matches[0]
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


def reconcile_saved_fixed_reward(store, claim_id):
    """Qualify the original immediate post-state offline; never access transport.

    Only the bottom action, weekly gift and permanent gift have qualified saved
    post-states here. Legacy upper entries, daily reset disputes and unrelated
    rewards are excluded; no period is reopened and no new action is possible.
    """
    import sqlite3

    from top_heroes_auto.vision.fixed_rewards import MONTHLY_QUICK, FixedRewardDetector, claim_geometry

    with store.connect() as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM reward_claims WHERE id=?', (claim_id,)).fetchone()
    if not row or row['reward_id'] not in {MONTHLY_QUICK, 'shop-weekly-card-gift', 'shop-permanent-privilege-gift'} or row['status'] != 'RESERVED' or row['dispatch_state'] != 'POSSIBLE':
        raise ValueError('Only an existing POSSIBLE qualified Shop action may be reconciled.')
    row = dict(row)
    if store.metadata(row['namespace'], row['instance_index']).protected:
        raise ValueError('Protected journal is outside the authorized reconciliation scope.')
    with store.connect() as db:
        db.row_factory = sqlite3.Row
        task = db.execute('SELECT * FROM task_runs WHERE id=?', (row['task_run_id'],)).fetchone()
    if (not task or task['namespace'] != row['namespace'] or task['instance_index'] != row['instance_index']
            or task['task'] != 'bxh-shop-fixed' or not task['report_path']):
        raise ValueError('Original task ownership is not proven.')
    path = Path(task['report_path'])
    report = json.loads(path.read_text(encoding='utf-8'))
    matches = [r for key, r in report['rewards'].items() if r.get('action_reward_id', key) == row['reward_id']]
    if len(matches) != 1 or matches[0].get('claim_id') != claim_id or matches[0].get('claim_dispatched') is not True:
        raise ValueError('Original dispatched action report is missing or ambiguous.')
    outcome = matches[0]
    before = json.loads(row['before_evidence'])
    if (before['capture'] != outcome['before']['capture'] or not before.get('persistent_identity')
            or before['persistent_identity'] != report.get('persistent_identity')):
        raise ValueError('Original persistent identity/evidence mismatch.')
    evidence = [before, outcome['immediate_after'], outcome['after']]
    times = [datetime.fromisoformat(e['timestamp']) for e in evidence]
    if not times[0] < times[1] < times[2] <= times[0]+timedelta(seconds=60):
        raise ValueError('Post-state was not captured immediately after the original action.')
    detector = FixedRewardDetector()
    frames = []
    for item in evidence:
        if (item['index'], item['name'], item['adb'], item['boot_id']) != (
                before['index'], before['name'], before['adb'], before['boot_id']):
            raise ValueError('Capture target/boot changed.')
        metadata = json.loads(Path(item['capture']).with_suffix('.json').read_text(encoding='utf-8'))
        # ScreenshotService persists metadata immediately before constructing
        # CapturedScreen, whose timestamp is created a few milliseconds later.
        delay = datetime.fromisoformat(item['timestamp'])-datetime.fromisoformat(metadata['timestamp'])
        if not timedelta(0) <= delay < timedelta(seconds=1):
            raise ValueError('Capture timestamp mismatch.')
        frames.append(detector.observe(saved_frame(item, path.parent)))
    if before['index'] != row['instance_index']:
        raise ValueError('Claim index mismatch.')
    reward_id = row['reward_id']
    state, core, _ = detector.availability(frames[0], reward_id)
    if state != 'AVAILABLE' or detector.availability(frames[2], reward_id)[0] != 'NOT_AVAILABLE':
        raise ValueError('Independent AVAILABLE to positive received state is not proven.')
    geometry = claim_geometry(frames[0], reward_id, core)
    actions = json.loads((path.parent/'actions.json').read_text(encoding='utf-8'))
    taps = [a for a in actions if a['before'] == before['capture']]
    if (len(taps) != 1 or taps[0]['action'] != 'tap' or taps[0]['outcome'] != 'DISPATCHED'
            or taps[0]['values'] != geometry['tap'] or geometry != before['geometry']):
        raise ValueError('Exactly one qualified original tap is not proven.')
    # Confetti can obscure the immediate receipt title. Verification is supplied
    # independently by all five completed rows, never by that popup alone.
    proof = dict(method='original_one_shot_and_independent_received_state', reward_id=reward_id,
                 claim_id=claim_id, task_run_id=row['task_run_id'], claim_redispatched=False,
                 before=frames[0].evidence(), receipt=frames[1].evidence(), after=frames[2].evidence())
    store.verify_reward_claim(claim_id, row['task_run_id'], json.dumps(proof, ensure_ascii=False))
    result = dict(result='VERIFIED', **proof)
    (path.parent/f'saved-reconciliation-{claim_id}.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result

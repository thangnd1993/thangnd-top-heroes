"""Accumulation, never a calendar date, establishes the next Idle opportunity."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from top_heroes_auto.automation.fixed_reward_reconcile import saved_frame
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.idle_detector import IdleRewardDetector
from top_heroes_auto.vision.models import ScreenState

REWARD = 'idle-reward'
CYCLE = 'idle-conservative-opportunity'


def emptied_proof(store, row, stable_id):
    """Re-read an original post-action empty panel, not a newer unavailable UI."""
    proof = json.loads(row['after_evidence'] or '{}')
    if proof.get('claim_dispatched') is not True or proof.get('postcondition_result') != 'VERIFIED':
        raise ValueError('Original verified Idle action proof is missing.')
    steps = proof.get('steps', [])
    dispatch = [s['number'] for s in steps if s.get('action') == 'claim_once']
    if len(dispatch) != 1:
        raise ValueError('Original one-shot Idle action is not proven.')
    with store.connect() as db:
        task = db.execute('SELECT namespace,instance_index,task,report_path FROM task_runs WHERE id=?',
                          (row['task_run_id'],)).fetchone()
    if not task or task[:3] != (row['namespace'], row['instance_index'], REWARD) or not task[3]:
        raise ValueError('Original Idle task ownership is missing.')
    folder = Path(task[3]).resolve().parent
    for step in steps:
        if step['number'] <= dispatch[0] or step.get('state') != 'IDLE_REWARD_NOT_CLAIMABLE':
            continue
        path = Path(step['screenshot']).resolve()
        if path.parent != folder:
            continue
        meta = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        if (meta['instance'].get('stable_id') != stable_id
                or meta['instance']['index'] != row['instance_index']
                or meta['adb_target'] != proof['adb_target']
                or not datetime.fromisoformat(row['reserved_at']) <= datetime.fromisoformat(meta['timestamp'])
                <= datetime.fromisoformat(row['verified_at'])):
            continue
        frame = saved_frame(dict(capture=str(path), timestamp=meta['timestamp'],
            index=row['instance_index'], name=meta['instance']['name'], adb=meta['adb_target'],
            boot_id=meta['boot_id']), folder)
        if IdleRewardDetector().detect(frame).state == ScreenState.IDLE_REWARD_NOT_CLAIMABLE:
            return dict(previous_claim_id=row['id'], empty_capture=str(path),
                        empty_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        persistent_identity=stable_id)
    raise ValueError('Original empty accumulation panel and durable identity are not proven.')


def opportunity(store, namespace, index, stable_id):
    if store.metadata(namespace, index).protected:
        raise SafetyError('Protected target cannot authorize Idle.')
    rows = [r for r in store.reward_claims(namespace, index) if r['reward_id'] == REWARD]
    with store.connect() as db:
        identity = db.execute('SELECT stable_id,state FROM instance_identities WHERE namespace=? AND idx=?',
                              (namespace, index)).fetchone()
        bindings = [db.execute('SELECT stable_id,state FROM journal_identities WHERE claim_id=?',
                               (r['id'],)).fetchone() for r in rows]
        legacy = db.execute('SELECT id,status,report_path FROM task_runs WHERE namespace=? '
                            'AND instance_index=? AND task=? ORDER BY id', (namespace,index,REWARD)).fetchall()
    if rows:
        expected = (stable_id, 'VERIFIED')
        if identity != expected or any(b != expected for b in bindings):
            raise SafetyError('AMBIGUOUS: historical Idle disk association remains locked.')
        if any(r['status'] != 'VERIFIED' for r in rows):
            raise SafetyError('Existing Idle dispatch/reservation remains locked; no repeat.')
        proof = emptied_proof(store, rows[-1], stable_id)
        return f"idle-after-verified:{rows[-1]['id']}", proof
    for task_id, status, path in legacy:
        evidence = {}
        try:
            if path:
                evidence = json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
        if evidence.get('claim_dispatched') or status in {
                'SUCCESS', 'SUCCESS_WITH_RECOVERY_WARNING', 'CLEANUP_FAILED', 'ACTION_RESULT_UNCERTAIN'}:
            raise SafetyError(f'LEGACY_ACTION_LOCKED: Idle task {task_id} lacks proven original empty/identity evidence.')
    return CYCLE, {}

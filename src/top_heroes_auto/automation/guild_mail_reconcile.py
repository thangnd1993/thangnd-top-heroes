"""Requalify an original Guild/Mail post-state, with no device transport."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from top_heroes_auto.automation.fixed_reward_reconcile import saved_frame
from top_heroes_auto.automation.guild_mail_claims import qualified_progress
from top_heroes_auto.vision.guild_mail import GUILD_REWARDS, MAIL_REWARDS, GuildMailDetector


def qualify_saved_guild_mail(store, claim_id, *, detector=None):
    with store.connect() as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM reward_claims WHERE id=?',(claim_id,)).fetchone()
        task = db.execute('SELECT * FROM task_runs WHERE id=?',(row['task_run_id'],)).fetchone() if row else None
    if (not row or row['reward_id'] not in (*GUILD_REWARDS,*MAIL_REWARDS)
            or row['status'] != 'RESERVED' or row['dispatch_state'] != 'POSSIBLE'):
        raise ValueError('Only an existing POSSIBLE Guild/Mail action can be reconciled.')
    if store.metadata(row['namespace'],row['instance_index']).protected:
        raise ValueError('Protected journal is excluded.')
    feature = 'guild' if row['reward_id'] in GUILD_REWARDS else 'mail'
    if (not task or task['task'] != feature or task['namespace'] != row['namespace']
            or task['instance_index'] != row['instance_index'] or not task['report_path']):
        raise ValueError('Original task ownership is not proven.')
    path = Path(task['report_path']).resolve()
    report = json.loads(path.read_text(encoding='utf-8'))
    before = json.loads(row['before_evidence'])
    outcome = report['rewards'].get(row['reward_id'],{})
    actions = [a for a in outcome.get('actions',[]) if a.get('claim_id') == claim_id]
    if (len(actions) != 1 or actions[0].get('claim_dispatched') is not True
            or actions[0].get('before') != before or not before.get('persistent_identity')
            or report.get('task_run_id') != row['task_run_id']
            or (report['index'],report['name']) != (row['instance_index'],row['instance_name'])):
        raise ValueError('Original dispatched action evidence is missing or ambiguous.')
    action = actions[0]
    transport = json.loads((path.parent/'actions.json').read_text(encoding='utf-8'))
    inputs = [a for a in transport if a.get('before') == before['frame']['capture']]
    if (len(inputs) != 1 or inputs[0].get('action') != 'tap' or inputs[0].get('outcome') != 'DISPATCHED'
            or inputs[0].get('values') != before['geometry']['tap']):
        raise ValueError('Exactly one original claim input is required.')
    detector = detector or GuildMailDetector()

    def observe(evidence):
        if (evidence['index'],evidence['name'],evidence['adb'],evidence['boot_id']) != (
                row['instance_index'],row['instance_name'],before['frame']['adb'],before['frame']['boot_id']):
            raise ValueError('Original capture identity changed.')
        image = Path(evidence['capture']).resolve()
        if image.parent != path.parent or image.suffix != '.png':
            raise ValueError('Capture escaped the original task.')
        metadata = json.loads(image.with_suffix('.json').read_text(encoding='utf-8'))
        delay = datetime.fromisoformat(evidence['timestamp'])-datetime.fromisoformat(metadata['timestamp'])
        if not timedelta(0) <= delay < timedelta(seconds=1):
            raise ValueError('Capture timestamp mismatch.')
        frame = detector.observe(saved_frame(evidence,path.parent))
        return frame,detector.availability(frame,row['reward_id'])

    original, available = observe(before['frame'])
    if json.dumps(available.evidence(),sort_keys=True) != json.dumps(before['opportunity'],sort_keys=True):
        raise ValueError('Original claimable state is not independently reproduced.')
    geometry = detector.action_geometry(original,available.role,available.box,available.forbidden)
    if geometry != before['geometry']:
        raise ValueError('Original tap geometry changed.')
    candidates = action.get('post_observations',[])+[action.get('after',{}),action.get('confirmation',{})]
    seen, qualified = set(),[]
    for candidate in candidates:
        evidence = candidate.get('frame')
        if not evidence or evidence['capture'] in seen:
            continue
        seen.add(evidence['capture'])
        current,view = observe(evidence)
        if qualified_progress(original,available,current,view):
            qualified.append((current,view))
        if len(qualified) == 2:
            break
    if len(qualified) != 2 or qualified[0][1].state != qualified[1][1].state or qualified[0][1].remaining != qualified[1][1].remaining:
        raise ValueError('Two original independent post-state frames are required.')
    proof = dict(method='original_one_shot_and_two_saved_progress_frames',claim_id=claim_id,
        persistent_identity=before['persistent_identity'],before=original.evidence(),
        after=[dict(frame=f.evidence(),opportunity=v.evidence()) for f,v in qualified],claim_redispatched=False)
    return dict(proof=proof,task_id=row['task_run_id'],path=path,namespace=row['namespace'],index=row['instance_index'])


def reconcile_saved_guild_mail(store, claim_id, *, detector=None):
    qualified = qualify_saved_guild_mail(store,claim_id,detector=detector)
    proof, path = qualified['proof'], qualified['path']
    if store.metadata(qualified['namespace'],qualified['index']).protected:
        raise ValueError('Protection changed before reconciliation.')
    store.verify_reward_claim(claim_id,qualified['task_id'],json.dumps(proof,ensure_ascii=False))
    (path.parent/f'claim-{claim_id}-reconciled.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(claim_id=claim_id,result='VERIFIED',claim_redispatched=False)

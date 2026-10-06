"""Requalify an original Guild/Mail post-state, with no device transport."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from top_heroes_auto.automation.fixed_reward_reconcile import saved_frame
from top_heroes_auto.automation.guild_mail_claims import qualified_progress
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.ldplayer.identity import runtime_key
from top_heroes_auto.vision.guild_mail import GUILD_REWARDS, MAIL_REWARDS, GuildMailDetector
from top_heroes_auto.vision.models import ScreenState


def _original_action(store, claim_id, *, detector=None):
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
            or runtime_key((report['index'],report['name'])) != runtime_key((row['instance_index'],row['instance_name']))):
        raise ValueError('Original dispatched action evidence is missing or ambiguous.')
    action = actions[0]
    transport = json.loads((path.parent/'actions.json').read_text(encoding='utf-8'))
    inputs = [a for a in transport if a.get('before') == before['frame']['capture']]
    if (len(inputs) != 1 or inputs[0].get('action') != 'tap' or inputs[0].get('outcome') != 'DISPATCHED'
            or inputs[0].get('values') != before['geometry']['tap']):
        raise ValueError('Exactly one original claim input is required.')
    immediate = action.get('immediate_after')
    if immediate:
        start = datetime.fromisoformat(before['frame']['timestamp'])
        end = datetime.fromisoformat(immediate['timestamp'])
        for event in transport:
            image = Path(event['before']).resolve()
            if image in {Path(before['frame']['capture']).resolve(),Path(immediate['capture']).resolve()}:
                continue  # An input bound to the receipt occurs AFTER that receipt was captured.
            if image.parent != path.parent or image.suffix != '.png':
                raise ValueError('Action capture escaped the original task.')
            metadata = json.loads(image.with_suffix('.json').read_text(encoding='utf-8'))
            if start < datetime.fromisoformat(metadata['timestamp']) <= end:
                raise ValueError('Another input intervened before the original receipt.')
    detector = detector or GuildMailDetector()

    def observe(evidence):
        if runtime_key((evidence['index'],evidence['name'],evidence['adb'],evidence['boot_id'])) != runtime_key((
                row['instance_index'],row['instance_name'],before['frame']['adb'],before['frame']['boot_id'])):
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
    receipt_inputs = [e for e in transport if immediate and Path(e['before']).resolve() == Path(immediate['capture']).resolve()]
    if receipt_inputs:
        popup,_ = observe(immediate)
        if len(receipt_inputs) != 1 or popup.overlay.state != ScreenState.REWARD_RECEIPT:
            raise ValueError('Original receipt input is ambiguous.')
        event = receipt_inputs[0]
        if (event.get('action') != 'tap' or event.get('outcome') != 'DISPATCHED' or
                event.get('values') != list(dismiss_overlay_bottom_left(popup.captured,popup.overlay))):
            raise ValueError('Original receipt input is not a qualified dismissal.')
    return row,path,before,action,detector,observe,original,available


def qualify_saved_guild_mail(store, claim_id, *, detector=None):
    row,path,before,action,detector,observe,original,available = _original_action(
        store,claim_id,detector=detector)
    candidates = action.get('post_observations',[])+[action.get('after',{}),action.get('confirmation',{})]
    seen, qualified = set(),[]
    for candidate in candidates:
        evidence = candidate.get('frame')
        if not evidence or evidence['capture'] in seen:
            continue
        seen.add(evidence['capture'])
        current,view = observe(evidence)
        if (qualified_progress(original,available,current,view) or
                _delayed_receipt_progress(original,available,current,view,observe,path,action)):
            qualified.append((current,view))
        if len(qualified) == 2:
            break
    if len(qualified) != 2 or qualified[0][1].state != qualified[1][1].state or qualified[0][1].remaining != qualified[1][1].remaining:
        raise ValueError('Two original independent post-state frames are required.')
    proof = dict(method='original_one_shot_and_two_saved_progress_frames',claim_id=claim_id,
        persistent_identity=before['persistent_identity'],before=original.evidence(),
        after=[dict(frame=f.evidence(),opportunity=v.evidence()) for f,v in qualified],claim_redispatched=False)
    return dict(proof=proof,task_id=row['task_run_id'],path=path,namespace=row['namespace'],index=row['instance_index'])


def _delayed_receipt_progress(original, available, current, view, observe, path, action):
    """Bounded ORIGINAL popup chain, not a longer global claim timeout.

    The saved run spent ~80s failing to classify a clear receipt. Permit at most
    180s only with its immediate receipt, exactly one qualified bottom-left
    dismissal, and independent progress within 30s of that dismissal.
    """
    start = datetime.fromisoformat(original.captured.timestamp)
    end = datetime.fromisoformat(current.captured.timestamp)
    if not timedelta(seconds=90) < end-start <= timedelta(seconds=180):
        return False
    immediate = action.get('immediate_after')
    if not immediate:
        return False
    receipt,_ = observe(immediate)
    at = datetime.fromisoformat(receipt.captured.timestamp)
    if not (start < at <= start+timedelta(seconds=60) and receipt.overlay.state == ScreenState.REWARD_RECEIPT):
        return False
    actions = json.loads((path.parent/'actions.json').read_text(encoding='utf-8'))
    intervening = []
    for event in actions:
        image = Path(event['before']).resolve()
        if image.parent != path.parent or image.suffix != '.png':
            raise ValueError('Action capture escaped the original task.')
        metadata = json.loads(image.with_suffix('.json').read_text(encoding='utf-8'))
        stamp = datetime.fromisoformat(metadata['timestamp'])
        if at <= stamp < end:
            intervening.append((event,image,metadata,stamp))
    if len(intervening) != 1:
        return False
    event,image,metadata,stamp = intervening[0]
    evidence = dict(capture=str(image),timestamp=metadata['timestamp'],index=metadata['instance']['index'],
                    name=metadata['instance']['name'],adb=metadata['adb_target'],boot_id=metadata['boot_id'])
    popup,_ = observe(evidence)
    if (event.get('action') != 'tap' or event.get('outcome') != 'DISPATCHED'
            or popup.overlay.state != ScreenState.REWARD_RECEIPT
            or end-stamp > timedelta(seconds=30)
            or event.get('values') != list(dismiss_overlay_bottom_left(popup.captured,popup.overlay))):
        return False
    return qualified_progress(original,available,current,view,maximum_elapsed=180)


def reconcile_saved_guild_mail(store, claim_id, *, detector=None):
    qualified = qualify_saved_guild_mail(store,claim_id,detector=detector)
    proof, path = qualified['proof'], qualified['path']
    if store.metadata(qualified['namespace'],qualified['index']).protected:
        raise ValueError('Protection changed before reconciliation.')
    store.verify_reward_claim(claim_id,qualified['task_id'],json.dumps(proof,ensure_ascii=False))
    (path.parent/f'claim-{claim_id}-reconciled.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(claim_id=claim_id,result='VERIFIED',claim_redispatched=False)


FRESH_BATCH_REWARDS = frozenset(('guild-gifts-loot','guild-gifts-member',*MAIL_REWARDS))


def prepare_observed_guild_mail(store, claim_id, detector, identity):
    """Qualify original files before taking fresh observations; no transport."""
    row,path,before,action,detector,observe,original,available = _original_action(
        store,claim_id,detector=detector)
    if row['reward_id'] not in FRESH_BATCH_REWARDS or before['persistent_identity'] != identity:
        raise ValueError('Only the same persistent batch target can be reconciled.')
    evidence = action.get('immediate_after')
    if not evidence:
        raise ValueError('Original immediate receipt is missing.')
    receipt,_ = observe(evidence)
    elapsed = datetime.fromisoformat(receipt.captured.timestamp)-datetime.fromisoformat(original.captured.timestamp)
    if not timedelta(0) < elapsed <= timedelta(seconds=60):
        raise ValueError('Receipt did not immediately follow the original input.')
    if not _qualified_receipt(receipt):
        receipt = _settled_original_receipt(path,before,evidence,observe,receipt)
    return row,path,original,available,receipt,identity


def _qualified_receipt(frame):
    popup = frame.overlay
    return (popup.state == ScreenState.REWARD_RECEIPT and popup.confidence >= .96
            and len({e.anchor_id for e in popup.evidence if e.matched}) >= 2)


def _settled_original_receipt(path, before, immediate, observe, first):
    """Original animation may settle; never fabricate a fresh receipt later.

    Inspect at most five following original captures, within the SAME 60-second
    original-action window. Every capture retains task/target/boot ownership.
    Any intervening input or known different screen rejects the chain. This
    prepares evidence only; two fresh independent progress states are still
    required before the old claim can verify. No runtime wait/threshold changes.
    """
    if first.page != 'UNKNOWN' or first.overlay.state != ScreenState.UNKNOWN:
        raise ValueError('Original receipt is not independently qualified.')
    start = datetime.fromisoformat(before['frame']['timestamp'])
    initial = datetime.fromisoformat(immediate['timestamp'])
    deadline = start+timedelta(seconds=60)
    captures = []
    for sidecar in path.parent.glob('*-guild-mail.evidence.json'):
        evidence = json.loads(sidecar.read_text(encoding='utf-8'))
        stamp = datetime.fromisoformat(evidence['timestamp'])
        if initial < stamp <= deadline:
            image = Path(evidence['capture']).resolve()
            if image != sidecar.with_name(sidecar.name.removesuffix('.evidence.json')+'.png').resolve():
                raise ValueError('Original receipt sidecar ownership is ambiguous.')
            captures.append((stamp,evidence))
    transport = json.loads((path.parent/'actions.json').read_text(encoding='utf-8'))
    for stamp,evidence in sorted(captures,key=lambda item:item[0])[:5]:
        for event in transport:
            image = Path(event['before']).resolve()
            if image == Path(before['frame']['capture']).resolve():
                continue  # The single original claim was already verified above.
            if image.parent != path.parent or image.suffix != '.png':
                raise ValueError('Action capture escaped the original task.')
            metadata = json.loads(image.with_suffix('.json').read_text(encoding='utf-8'))
            if start < datetime.fromisoformat(metadata['timestamp']) <= stamp:
                raise ValueError('Input interrupted original receipt stabilization.')
        frame,_ = observe(evidence)
        if _qualified_receipt(frame):
            return frame
        if frame.page != 'UNKNOWN' or frame.overlay.state != ScreenState.UNKNOWN:
            raise ValueError('Original receipt stabilization changed screen.')
    raise ValueError('Original receipt is not independently qualified.')


def reconcile_observed_guild_mail(store, claim_id, detector, frames, identity, *, prepared=None):
    """Original one-shot + original receipt + two fresh agreeing progress states.

    Read-only observation is supplied by the existing bound instance session.
    No reward transport exists here. Receipt alone or counter change alone cannot
    release an uncertain batch. Positive remainder still needs its selected tab
    and qualified free control, and is separate work after this action verifies.
    """
    prepared = prepared or prepare_observed_guild_mail(store,claim_id,detector,identity)
    row,path,original,available,receipt,original_identity = prepared
    if row['id'] != claim_id or original_identity != identity:
        raise ValueError('Prepared original evidence belongs to another action.')
    if len(frames) != 2:
        raise ValueError('Two fresh post-state frames are required.')
    a,b = (frame.captured for frame in frames)
    if (a.source_image is None or b.source_image is None or a.source_image == b.source_image
            or runtime_key((a.index,a.name,a.serial,a.boot_id)) != runtime_key((b.index,b.name,b.serial,b.boot_id))
            or runtime_key((a.index,a.name,a.serial)) != runtime_key((original.captured.index,original.captured.name,original.captured.serial))):
        raise ValueError('Fresh post-state identity/capture is ambiguous.')
    now = datetime.now(timezone.utc)
    at,bt = datetime.fromisoformat(a.timestamp),datetime.fromisoformat(b.timestamp)
    if not (datetime.fromisoformat(receipt.captured.timestamp) < at < bt <= now
            and now-at <= timedelta(seconds=60)):
        raise ValueError('Fresh post-state observations are stale or unordered.')
    observations = []
    for frame in frames:
        view = detector.availability(frame,row['reward_id'])
        if (frame.page != original.page or view.reward != available.reward or view.context != available.context
                or type(view.remaining) is not int or type(available.remaining) is not int
                or not 0 <= view.remaining < available.remaining
                or (view.remaining == 0 and view.state != 'NOT_AVAILABLE')
                or (view.remaining > 0 and (view.state != 'AVAILABLE' or view.box is None))):
            raise ValueError('Independent batch progress is not proven.')
        observations.append(dict(frame=frame.evidence(),opportunity=view.evidence()))
    if observations[0]['opportunity'] != observations[1]['opportunity']:
        raise ValueError('Fresh post-state progress is not stable.')
    if store.metadata(row['namespace'],row['instance_index']).protected:
        raise ValueError('Protection changed before reconciliation.')
    proof = dict(method='original_one_shot_receipt_and_two_fresh_progress_frames',claim_id=claim_id,
                 persistent_identity=identity,before=original.evidence(),receipt=receipt.evidence(),
                 after=observations,claim_redispatched=False)
    store.verify_reward_claim(claim_id,row['task_run_id'],json.dumps(proof,ensure_ascii=False))
    (path.parent/f'claim-{claim_id}-reconciled.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    return proof

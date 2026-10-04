"""Independent task-list removal effects, paired with a qualified receipt."""
import json
from dataclasses import replace
from pathlib import Path

import cv2

from top_heroes_auto.adb.client import Target
from top_heroes_auto.vision.dynamic_events import (
    selected_task_badge_count,
    task_context_box,
    task_reward_rows,
)
from top_heroes_auto.vision.local_ocr import read_words
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.screenshot import ScreenshotService


def saved_frame(path):
    path = Path(path)
    meta = json.loads(path.with_suffix('.event.json').read_text(encoding='utf-8'))
    screenshot = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    identity = [screenshot['instance']['index'], screenshot['instance']['name'],
                screenshot['adb_target'], screenshot['boot_id']]
    if meta['frame']['identity'] != identity:
        raise ValueError('Saved frame transport evidence conflicts.')
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError('Missing task-list evidence.')
    if image.shape[1] > image.shape[0]:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image, meta, screenshot


def removal_effect(proof, captures, receipt, *, reader=read_words, allow_new_boot=False):
    """Two fresh counter observations plus actual removal of the claimable prefix.

    Some task controls consume several AVAILABLE cards in one tap. Require the
    exact decrement for a completely visible prefix, or a qualified lower
    bound when every complete visible row is AVAILABLE, zero remaining claimable
    controls in the fresh top viewport, the same selected task context/outer
    Event and a receipt bound to the original transport. Receipt alone, missing
    rows alone, scrolling alone or arbitrary badge changes cannot verify anything.
    """
    if len(captures) != 2 or len(set(map(str,captures))) != 2 or not receipt:
        return []
    before, meta, before_shot = saved_frame(proof['capture'])
    frame = meta['frame']
    if frame['identity'] != list(proof['identity']) or frame['page'] != proof['page']:
        return []
    template = cv2.imread(str(template_folder().parent/'tasks/phase8/personal-task-tab.png'))
    context = task_context_box(before, template)
    if context is None or not meta.get('entered_event'):
        return []
    rows = task_reward_rows(before, template, reader=reader)
    available = [r for r in rows if r['state'] == 'AVAILABLE']
    if (not available or not rows or proof['reward'] not in {r['identity'] for r in available}
            or list(rows[:len(available)]) != available
            or rows[0]['row'].y-context.y-context.height > before.shape[0]*.04):
        return []
    target_rows = [r for r in available if r['identity'] == proof['reward']]
    if len(target_rows) != 1 or (proof.get('tap') and list(target_rows[0]['box'].center) != proof['tap']):
        return []
    controls = [c for c in frame['controls'] if c['kind'] == 'reward']
    if ({c['identity'] for c in controls} != {r['identity'] for r in available}
            or any(c['cost'] != 'FREE' or not c['available'] for c in controls)):
        return []
    count = selected_task_badge_count(before, meta['shell']['selected'], reader=reader)
    if count is None or count < len(available):
        return []
    receipt = Path(receipt)
    receipt_shot = json.loads(receipt.with_suffix('.json').read_text(encoding='utf-8'))
    receipt_identity = [receipt_shot['instance']['index'],receipt_shot['instance']['name'],
                        receipt_shot['adb_target'],receipt_shot['boot_id']]
    if receipt_identity != list(proof['identity']) or receipt_shot['timestamp'] <= before_shot['timestamp']:
        return []
    image = cv2.imread(str(receipt))
    if image is None:
        return []
    if image.shape[1] > image.shape[0]:
        image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    target = Target(*proof['identity'])
    captured = ScreenshotService(lambda _: cv2.imencode('.png',image)[1].tobytes()).take(target)
    detected = RecoveryScreenDetector().detect(replace(captured, source_image=receipt))
    if detected.state != ScreenState.REWARD_RECEIPT:
        return []
    observations = []
    for number,path in enumerate(captures):
        after, after_meta, shot = saved_frame(path)
        current = after_meta['frame']
        if (str(path) == proof['capture'] or current['page'] != proof['page']
                or current['identity'][:2] != list(proof['identity'])[:2]
                or (not allow_new_boot and current['identity'] != list(proof['identity']))
                or after_meta.get('entered_event') != meta['entered_event']
                or shot['timestamp'] <= receipt_shot['timestamp']
                or (observations and current['identity'] != observations[0]['identity'])):
            return []
        after_context = task_context_box(after, template)
        after_rows = task_reward_rows(after, template, reader=reader)
        after_count = selected_task_badge_count(after,after_meta['shell']['selected'],reader=reader)
        prefix_complete = len(available) < len(rows)
        if (after_context is None or not after_rows or after_count is None
                or (prefix_complete and after_count != count-len(available))
                or (not prefix_complete and count-after_count < len(available))
                or (observations and after_count != observations[0]['after_count'])
                or any(r['state'] != 'NOT_AVAILABLE' for r in after_rows)):
            return []
        if number == 0 and after_rows[0]['row'].y-after_context.y-after_context.height > after.shape[0]*.04:
            return []  # A lower scrolled viewport alone is never prefix-removal proof.
        observations.append(dict(identity=current['identity'], capture=str(path),
            event=proof['event'],page=proof['page'],reward=proof['reward'],state='NOT_AVAILABLE',
            receipt=str(receipt),before_count=count,after_count=after_count,
            consumed_reward_ids=[r['identity'] for r in available],
            visible_prefix_complete=prefix_complete,
            observed_count_decrement=count-after_count,
            unobserved_consumed_count=count-after_count-len(available),
            prefix_removal_capture=str(captures[0]),independent_evidence=[
                'same-qualified-task-context','unique-selected-tab-counter',
                ('exact-free-prefix-count-decrement' if prefix_complete else
                 'incomplete-visible-prefix-count-lower-bound'),'claimable-prefix-gone',
                'fresh-unavailable-controls','independent-receipt-pair']))
    return observations


def reconcile_saved(manager, claim_id, original_report, after_report):
    """Only an Event claim, only its existing owner, no selection/ADB/game input."""
    from top_heroes_auto.app.bxh_shop_acceptance import persistent_identity
    from top_heroes_auto.automation.guard import SafetyError

    original_path, after_path = Path(original_report), Path(after_report)
    original = json.loads(original_path.read_text(encoding='utf-8'))
    recent = json.loads(after_path.read_text(encoding='utf-8'))
    for report in (original,recent):
        if (report.get('schema') != 'instance-first-v1' or report.get('max_concurrency') != 1
                or report.get('execution_flows') != ['events'] or not report.get('scope_limited')):
            raise SafetyError('Saved reconciliation requires original events-only reports.')
    claims = [r for target in original['targets']
              for r in manager.store.reward_claims(manager.namespace,target['index']) if r['id']==claim_id]
    if len(claims) != 1 or not claims[0]['reward_id'].startswith('event:'):
        raise SafetyError('Only the explicitly identified Event journal may be reconciled.')
    claim = claims[0]
    if claim['status'] == 'VERIFIED':
        return dict(claim_id=claim_id,result='ALREADY_VERIFIED',claim_dispatched=False)
    if claim['status'] != 'RESERVED' or claim['dispatch_state'] != 'POSSIBLE':
        raise SafetyError('Existing dispatched Event journal required.')
    index, name = claim['instance_index'],claim['instance_name']
    proof = json.loads(claim['before_evidence'])
    current = [r for r in manager.refresh() if r.index == index and r.name == name]
    target = [r for r in recent['targets'] if r['index'] == index and r['name'] == name]
    if (len(current) != 1 or len(target) != 1 or manager.store.metadata(manager.namespace,index).protected
            or persistent_identity(manager,index) != proof['persistent_identity']
            or target[0]['persistent_identity'] != proof['persistent_identity']):
        raise SafetyError('Current exact non-Protected Event target/disk proof required.')
    folder = original_path.parent/str(index)/'events'
    if Path(proof['capture']).resolve().parent != folder.resolve():
        raise SafetyError('Original claim capture is outside its task evidence.')
    actions = json.loads((folder/'actions.json').read_text(encoding='utf-8'))
    taps = [a for a in actions if a['action']=='tap' and a['before']==proof['capture']]
    if len(taps) != 1 or taps[0]['values'] != proof['tap']:
        raise SafetyError('Exactly one original claim dispatch must be proven.')
    after_folder = after_path.parent/str(index)/'events'
    candidates=[]
    for path in sorted(after_folder.glob('*.event.json')):
        metadata=json.loads(path.read_text(encoding='utf-8'))
        if metadata['frame']['page']==proof['page']:
            candidates.append(path.with_suffix('').with_suffix('.png'))
    candidates=candidates[:8]
    receipts=[p for p in sorted(folder.glob('*-bxh-shop.png'))
              if p.name > Path(proof['capture']).name][:5]
    observations=[]
    for receipt in receipts:
        for a,b in zip(candidates,candidates[1:]):
            observations=removal_effect(proof,[a,b],receipt,allow_new_boot=True)
            if observations:
                break
        if observations:
            break
    if not observations:
        raise SafetyError('Independent removal/count/receipt proof incomplete; journal remains POSSIBLE.')
    # Recheck live ownership immediately before the journal mutation. This does
    # not select, launch, stop, ADB-target, rename or repair any instance.
    current = [r for r in manager.refresh() if r.index==index and r.name==name]
    if (len(current)!=1 or manager.store.metadata(manager.namespace,index).protected
            or persistent_identity(manager,index)!=proof['persistent_identity']):
        raise SafetyError('Event reconciliation authorization/identity changed.')
    manager.store.verify_reward_claim(claim_id,claim['task_run_id'],json.dumps(observations))
    result=dict(claim_id=claim_id,index=index,result='VERIFIED',claim_dispatched=False,
        original_task=claim['task_run_id'],after_evidence=observations)
    (after_folder/f'claim-{claim_id}-reconciled.json').write_text(
        json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

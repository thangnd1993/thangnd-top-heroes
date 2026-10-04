"""Qualified disappearance/count-decrement variant, never receipt-only success."""
import json
import sys
from pathlib import Path

import cv2
import pytest

from top_heroes_auto.app.event_task_effect import removal_effect
from top_heroes_auto.vision.dynamic_events import event_shell, task_reward_rows
from top_heroes_auto.vision.models import BoundingBox

FIXTURES = Path(__file__).parent/'fixtures/phase8'


def role_reader(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv,(35,60,80),(85,255,255))
    return [{'text':'Nhan' if cv2.countNonZero(green) > green.size*.10 else 'Den'}]


def rig(tmp_path, *, before_fixture='task-list-before-batch.png',
        after_fixture='task-list-after-batch.png'):
    template = cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    paths = []
    before_rows = None
    for name,fixture,stamp,boot in [('before',before_fixture,1,'old'),
            ('after1',after_fixture,3,'new'),
            ('after2',after_fixture,4,'new')]:
        image = cv2.imread(str(FIXTURES/fixture))
        rows = task_reward_rows(image,template,reader=role_reader)
        path = tmp_path/(name+'.png')
        path.write_bytes(cv2.imencode('.png',cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE))[1].tobytes())
        identity = [13,'fixture account','explicit',boot]
        shell = event_shell(image,BoundingBox(34,1209,52,47),reader=lambda _: [{'text':'Arbitrary title'}])
        controls = [dict(identity=r['identity'],kind='reward',cost='FREE',available=True) for r in rows if r['state']=='AVAILABLE']
        meta = dict(frame=dict(identity=identity,page='event:arbitrary:personal-tasks',controls=controls),
                    entered_event='current-icon',shell=dict(selected=shell['selected']))
        path.with_suffix('.event.json').write_text(json.dumps(meta))
        path.with_suffix('.json').write_text(json.dumps(dict(instance={'index':13,'name':'fixture account'},
            adb_target='explicit',boot_id=boot,timestamp=f'2026-01-01T00:00:0{stamp}+00:00')))
        paths.append(path)
        if before_rows is None:
            before_rows=rows
    receipt = tmp_path/'receipt.png'
    receipt.write_bytes((FIXTURES/'large-receipt.png').read_bytes())
    receipt.with_suffix('.json').write_text(json.dumps(dict(instance={'index':13,'name':'fixture account'},
            adb_target='explicit',boot_id='old',timestamp='2026-01-01T00:00:02+00:00')))
    proof = dict(identity=[13,'fixture account','explicit','old'],event='arbitrary',
                 capture=str(paths[0]),page='event:arbitrary:personal-tasks',reward=before_rows[0]['identity'])
    return proof,paths,receipt


def badge_counts(monkeypatch, values):
    calls = iter(values)
    monkeypatch.setattr('top_heroes_auto.app.event_task_effect.selected_task_badge_count',lambda *a,**k:next(calls))


def test_actual_removed_prefix_requires_exact_count_change_receipt_and_two_captures(tmp_path,monkeypatch):
    proof,paths,receipt = rig(tmp_path)
    badge_counts(monkeypatch,[9,7,7])
    result = removal_effect(proof,paths[1:],receipt,reader=role_reader,allow_new_boot=True)
    assert len(result)==2
    assert result[0]['before_count']==9 and result[0]['after_count']==7
    assert len(result[0]['consumed_reward_ids'])==2
    assert proof['reward'] in result[0]['consumed_reward_ids']
    assert all(r['state']=='NOT_AVAILABLE' for r in result)


@pytest.mark.parametrize('counts', [[9,9], [9,8], [9,6], [9,7,6], [None]])
def test_missing_rows_or_wrong_counter_change_remain_unverified(tmp_path,monkeypatch,counts):
    proof,paths,receipt = rig(tmp_path)
    badge_counts(monkeypatch,counts)
    assert not removal_effect(proof,paths[1:],receipt,reader=role_reader,allow_new_boot=True)


def test_arbitrary_counts_are_not_a_fixed_nine_to_seven_route(tmp_path,monkeypatch):
    proof,paths,receipt = rig(tmp_path)
    badge_counts(monkeypatch,[21,19,19])
    assert len(removal_effect(proof,paths[1:],receipt,reader=role_reader,allow_new_boot=True))==2


def test_receipt_alone_duplicate_or_wrong_target_never_proves_removal(tmp_path,monkeypatch):
    proof,paths,receipt = rig(tmp_path)
    assert not removal_effect(proof,[paths[1]]*2,receipt,reader=role_reader,allow_new_boot=True)
    meta = json.loads(paths[1].with_suffix('.event.json').read_text())
    meta['frame']['page'] = 'other-event'
    paths[1].with_suffix('.event.json').write_text(json.dumps(meta))
    badge_counts(monkeypatch,[9])
    assert not removal_effect(proof,paths[1:],receipt,reader=role_reader,allow_new_boot=True)


def test_receipt_without_changed_underlying_page_cannot_verify(tmp_path,monkeypatch):
    proof,paths,receipt = rig(tmp_path)
    for path in paths[1:]:
        path.write_bytes(paths[0].read_bytes())
    badge_counts(monkeypatch,[9,7])
    assert not removal_effect(proof,paths[1:],receipt,reader=role_reader,allow_new_boot=True)


@pytest.mark.skipif(sys.platform!='win32',reason='Real native Windows OCR evidence qualification')
def test_real_badge_digits_and_real_frame_control_labels(tmp_path):
    proof,paths,receipt = rig(tmp_path)
    assert len(removal_effect(proof,paths[1:],receipt,allow_new_boot=True)) == 2


def saved_rig(tmp_path,monkeypatch,*,protected=False,disk='disk',scope=None):
    from types import SimpleNamespace

    from top_heroes_auto.storage.store import Store
    old=tmp_path/'old'/'13'/'events'
    old.mkdir(parents=True)
    proof,paths,receipt=rig(old)
    new=tmp_path/'new'/'13'/'events'
    new.mkdir(parents=True)
    for path in paths[1:]:
        for file in (path,path.with_suffix('.json'),path.with_suffix('.event.json')):
            file.rename(new/file.name)
    before=old/'before-bxh-shop.png'
    paths[0].rename(before)
    paths[0].with_suffix('.json').rename(before.with_suffix('.json'))
    paths[0].with_suffix('.event.json').rename(before.with_suffix('.event.json'))
    original_receipt=old/'receipt-bxh-shop.png'
    receipt.rename(original_receipt)
    receipt.with_suffix('.json').rename(original_receipt.with_suffix('.json'))
    proof.update(capture=str(before),persistent_identity='disk',tap=[612,590])
    (old/'actions.json').write_text(json.dumps([dict(action='tap',before=str(before),values=proof['tap'])]))
    report=dict(schema='instance-first-v1',max_concurrency=1,execution_flows=['events'],scope_limited=True,
        targets=[dict(index=13,name='fixture account',persistent_identity='disk')])
    original=old.parent.parent/'fleet-report.json'
    original.write_text(json.dumps(report))
    recent=new.parent.parent/'fleet-report.json'
    recent.write_text(json.dumps({**report,**(scope or {})}))
    store=Store(tmp_path/'journal.sqlite3')
    task=store.create_task_run('install','events',13,'fixture account')
    claim=store.reserve_reward_claim(task,'event:original','unknown-period',json.dumps(proof),
        expected_instance=(13,'fixture account'),not_dispatched=True)
    store.mark_reward_dispatch(claim,task)
    manager=SimpleNamespace(store=store,namespace='install',refresh=lambda:[SimpleNamespace(index=13,name='fixture account')])
    manager.execute=lambda *a,**k:pytest.fail('No emulator/input operation is permitted')
    monkeypatch.setattr(store,'metadata',lambda *a:SimpleNamespace(protected=protected))
    monkeypatch.setattr('top_heroes_auto.app.bxh_shop_acceptance.persistent_identity',lambda *a:disk)
    observed=[dict(identity=[13,'fixture account','explicit','new'],capture=str(new/f'after{n+1}.png'),
        page=proof['page'],reward=proof['reward'],state='NOT_AVAILABLE',consumed_reward_ids=[proof['reward'],'sibling'],
        independent_evidence=['qualified-body-count-removal']) for n in range(2)]
    monkeypatch.setattr('top_heroes_auto.app.event_task_effect.removal_effect',lambda *a,**k:observed)
    return manager,claim,original,recent


def test_saved_reconciliation_only_changes_existing_event_owner_and_sends_no_input(tmp_path,monkeypatch):
    from top_heroes_auto.app.event_task_effect import reconcile_saved

    manager,claim,original,recent=saved_rig(tmp_path,monkeypatch)
    outcome=reconcile_saved(manager,claim,original,recent)
    row=manager.store.reward_claims('install',13)[0]
    assert outcome['result']=='VERIFIED' and not outcome['claim_dispatched']
    assert row['status']=='VERIFIED'
    assert reconcile_saved(manager,claim,original,recent)['result']=='ALREADY_VERIFIED'
    assert len(manager.store.reward_claims('install',13))==1


@pytest.mark.parametrize('options',[{'protected':True},{'disk':'changed'},
    {'scope':{'execution_flows':['events','vip']}}])
def test_saved_reconciliation_protection_identity_scope_fail_closed(tmp_path,monkeypatch,options):
    from top_heroes_auto.app.event_task_effect import reconcile_saved
    from top_heroes_auto.automation.guard import SafetyError

    manager,claim,original,recent=saved_rig(tmp_path,monkeypatch,**options)
    before=manager.store.reward_claims('install',13)[0]
    with pytest.raises(SafetyError):
        reconcile_saved(manager,claim,original,recent)
    assert manager.store.reward_claims('install',13)[0]==before


def test_duplicate_original_dispatch_cannot_be_reconciled(tmp_path,monkeypatch):
    from top_heroes_auto.app.event_task_effect import reconcile_saved
    from top_heroes_auto.automation.guard import SafetyError

    manager,claim,original,recent=saved_rig(tmp_path,monkeypatch)
    path=original.parent/'13/events/actions.json'
    actions=json.loads(path.read_text())
    path.write_text(json.dumps(actions*2))
    with pytest.raises(SafetyError):
        reconcile_saved(manager,claim,original,recent)
    assert manager.store.reward_claims('install',13)[0]['status']=='RESERVED'


def test_plain_dot_and_duplicate_active_tab_badges_are_not_numeric_evidence():
    from top_heroes_auto.vision.dynamic_events import discover_badges, selected_task_badge_count

    image=cv2.imread(str(FIXTURES/'task-list-before-batch.png'))
    shell=event_shell(image,BoundingBox(34,1209,52,47),reader=lambda _: [{'text':'Arbitrary title'}])
    tab=BoundingBox(**shell['selected'][0])
    badge=next(b for b in discover_badges(image,tab) if b.qualified)
    b=badge.box
    damaged=image.copy()
    inset=3
    damaged[b.y+inset:b.y+b.height-inset,b.x+inset:b.x+b.width-inset]=(30,50,220)
    assert selected_task_badge_count(damaged,shell['selected'],reader=lambda _:pytest.fail('A dot has no digit')) is None
    duplicate=image.copy()
    duplicate[b.y:b.y+b.height,b.x-23:b.x-23+b.width]=image[b.y:b.y+b.height,b.x:b.x+b.width]
    assert selected_task_badge_count(duplicate,shell['selected'],reader=lambda _:pytest.fail('Duplicate badges are ambiguous')) is None


def test_partial_visible_prefix_models_observed_batch_without_fabricating_hidden_ids(tmp_path,monkeypatch):
    proof,paths,receipt=rig(tmp_path,before_fixture='task-list-before-partial-prefix.png',
                           after_fixture='task-list-after-partial-prefix.png')
    badge_counts(monkeypatch,[13,8,8])
    result=removal_effect(proof,paths[1:],receipt,reader=role_reader,allow_new_boot=True)
    assert len(result)==2
    assert result[0]['visible_prefix_complete'] is False
    assert result[0]['observed_count_decrement']==5
    assert result[0]['unobserved_consumed_count']==2
    assert len(result[0]['consumed_reward_ids'])==3


@pytest.mark.parametrize('counts',[[13,13],[13,11],[13,8,7]])
def test_partial_prefix_rejects_unchanged_insufficient_or_conflicting_counter(tmp_path,monkeypatch,counts):
    proof,paths,receipt=rig(tmp_path,before_fixture='task-list-before-partial-prefix.png',
                           after_fixture='task-list-after-partial-prefix.png')
    badge_counts(monkeypatch,counts)
    assert not removal_effect(proof,paths[1:],receipt,reader=role_reader,allow_new_boot=True)


def test_saved_reconciliation_keeps_first_post_action_receipt_in_long_session(tmp_path,monkeypatch):
    import top_heroes_auto.app.event_task_effect as module

    manager,claim,original,recent=saved_rig(tmp_path,monkeypatch)
    first=original.parent/'13/events/receipt-bxh-shop.png'
    for n in range(7):
        (first.parent/f'z-later-{n}-bxh-shop.png').write_bytes(first.read_bytes())
    existing=module.removal_effect
    inspected=[]

    def effect(proof,captures,receipt,**kw):
        inspected.append(receipt.name)
        return existing(proof,captures,receipt,**kw) if receipt==first else []

    monkeypatch.setattr(module,'removal_effect',effect)
    assert module.reconcile_saved(manager,claim,original,recent)['result']=='VERIFIED'
    assert inspected==['receipt-bxh-shop.png']

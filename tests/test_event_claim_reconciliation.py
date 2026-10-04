"""Cross-session proof must keep POSSIBLE locked without another tap."""
import json
from dataclasses import replace

import cv2
import pytest
from test_dynamic_events import task_rows
from test_event_journal import run, setup

from top_heroes_auto.app.event_claim_reconciliation import bind_saved_rewards, reconcile_possible
from top_heroes_auto.automation.guard import SafetyError


def evidence(tmp_path):
    image = cv2.imread('tests/fixtures/phase8/task-reward-list.png')
    row = task_rows(image)[0]
    source = tmp_path/'before.png'
    source.write_bytes(cv2.imencode('.png', cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE))[1].tobytes())
    saved = {**row, 'row': vars(row['row']), 'box': vars(row['box'])}
    source.with_suffix('.event.json').write_text(json.dumps({'reward_rows': [saved]}))
    claim = dict(reward_id='event:key', dispatch_state='POSSIBLE', before_evidence=json.dumps(dict(
        page='event:title:personal-tasks', reward=row['identity'], capture=str(source),
        identity=[13,'user name','explicit','old-boot'], persistent_identity='disk')))
    return image, row, claim


def test_unique_caption_alias_keeps_original_lock_identity_without_coordinates(tmp_path):
    image,row,claim = evidence(tmp_path)
    moved = cv2.warpAffine(image, __import__('numpy').float32([[1,0,0],[0,1,20]]), (720,1280))
    current = task_rows(moved)[0]
    current['identity'] = 'different-raster-hash'
    result = bind_saved_rewards(moved, [current], [claim], persistent_identity='disk', index=13)
    assert result[0]['identity'] == row['identity']
    assert result[0]['box'].y == row['box'].y+20
    assert 'unique-saved-caption-agreement' in result[0]['evidence']


def test_duplicate_saved_caption_fails_closed(tmp_path):
    image,row,claim = evidence(tmp_path)
    result = bind_saved_rewards(image, [row, dict(row)], [claim], persistent_identity='disk', index=13)
    assert all(r['state'] == 'UNKNOWN' for r in result)


def test_missing_saved_evidence_or_changed_disk_cannot_unlock(tmp_path):
    image,row,claim = evidence(tmp_path)
    with pytest.raises(SafetyError):
        bind_saved_rewards(image, [row], [claim], persistent_identity='different', index=13)
    source = json.loads(claim['before_evidence'])['capture']
    from pathlib import Path
    Path(source).unlink()
    with pytest.raises(SafetyError):
        bind_saved_rewards(image, [row], [claim], persistent_identity='disk', index=13)


def pending(tmp_path):
    store,task,f,r = setup(tmp_path)
    f = replace(f, page='event:title:personal-tasks')
    calls = []
    result = run(store,task,f,r,calls,post=lambda *a: [])
    post = [dict(identity=[*f.identity[:3], 'fresh-verified-boot'], capture=f'fresh-{i}',
        page=f.page, reward=r.identity, state='NOT_AVAILABLE',
        independent_evidence=['unique-saved-caption-agreement','qualified-control-color',
                              'selected-task-context','complete-reward-card'])
        for i in range(2)]
    return store,f,r,calls,result,post


def test_two_fresh_proofs_reconcile_original_task_without_redispatch(tmp_path):
    store,f,r,calls,result,post = pending(tmp_path)
    assert reconcile_possible(store,'install',13,'disk',post) == [result['claim_id']]
    assert store.reward_claims('install',13)[0]['status'] == 'VERIFIED'
    run(store,store.create_task_run('install','events',13,'user name'),f,r,calls)
    assert len(calls) == 1


@pytest.mark.parametrize('change', [{'state':'POPUP'}, {'capture':'fresh-0'},
    {'page':'wrong-page'}, {'reward':'wrong-reward'}, {'independent_evidence':[]}])
def test_weak_reconciliation_keeps_possible(change,tmp_path):
    store,_,_,calls,_,post = pending(tmp_path)
    post[1].update(change)
    assert not reconcile_possible(store,'install',13,'disk',post)
    assert store.reward_claims('install',13)[0]['dispatch_state'] == 'POSSIBLE'
    assert store.reward_claims('install',13)[0]['status'] == 'RESERVED'
    assert len(calls) == 1


def test_reconciliation_excludes_current_session_claim_owned_by_dispatch_once(tmp_path):
    store,_,_,calls,result,post = pending(tmp_path)
    assert not reconcile_possible(store,'install',13,'disk',post,claim_ids=set())
    assert store.reward_claims('install',13)[0]['status'] == 'RESERVED'
    assert reconcile_possible(store,'install',13,'disk',post,claim_ids={result['claim_id']}) == [result['claim_id']]
    assert len(calls) == 1


def test_unrecognized_new_caption_cannot_reopen_unresolved_claim(tmp_path):
    image,row,claim = evidence(tmp_path)
    current = image.copy()
    b = row['row']
    current[b.y+8:b.y+round(b.height*.30), b.x+10:b.x+round(b.width*.72)] = (210,220,230)
    cv2.putText(current, 'Different raster', (b.x+20,b.y+35), cv2.FONT_HERSHEY_SIMPLEX, .7, (30,65,100), 2)
    changed = dict(row, identity='new-raster')
    result = bind_saved_rewards(current, [changed], [claim], persistent_identity='disk', index=13)
    assert result[0]['state'] == 'UNKNOWN'


def test_reconciliation_does_not_read_or_modify_unrelated_possible_journals(tmp_path):
    store,_,_,_,result,post = pending(tmp_path)
    task = store.create_task_run('install','legacy-vip',13,'user name')
    unrelated = store.reserve_reward_claim(task,'vip:old','unknown-period','{}',
        expected_instance=(13,'user name'),not_dispatched=True)
    store.mark_reward_dispatch(unrelated,task)
    before = next(r for r in store.reward_claims('install',13) if r['id']==unrelated)
    assert reconcile_possible(store,'install',13,'disk',post,
        claim_ids={result['claim_id'],unrelated}) == [result['claim_id']]
    assert next(r for r in store.reward_claims('install',13) if r['id']==unrelated) == before


@pytest.mark.parametrize('status',['RESERVED','VERIFIED'])
def test_unfamiliar_but_positively_unavailable_row_stays_unavailable(tmp_path,status):
    image,row,claim=evidence(tmp_path)
    current=image.copy()
    b=row['row']
    current[b.y+8:b.y+round(b.height*.30), b.x+10:b.x+round(b.width*.72)]=(210,220,230)
    cv2.putText(current,'Different raster',(b.x+20,b.y+35),cv2.FONT_HERSHEY_SIMPLEX,.7,(30,65,100),2)
    claim['status']=status
    changed=dict(row,identity='new-raster',state='NOT_AVAILABLE')
    result=bind_saved_rewards(current,[changed],[claim],persistent_identity='disk',index=13)
    assert result[0]['state']=='NOT_AVAILABLE'

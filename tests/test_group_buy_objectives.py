"""Saved public objectives must never authorize the adjacent paid offer."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.vision.event_inline_objectives import inline_objective_rows
from top_heroes_auto.vision.models import BoundingBox, ScreenState


def image():
    return cv2.imread('tests/fixtures/phase8/group-buy-objectives.png')


def reader(crop):
    saved=json.loads(Path('tests/fixtures/phase8/group-buy-ocr.json').read_text(encoding='utf-8'))
    return saved.get(hashlib.sha256(crop.tobytes()).hexdigest(),[])


def test_two_complete_public_goals_are_free_but_partial_goal_is_not():
    rows=inline_objective_rows(image(),reader=reader)
    assert len(rows)==2 and all(r['state']=='AVAILABLE' for r in rows)
    assert len({r['identity'] for r in rows})==2
    assert all(r['box'].y>r['row'].y>615 for r in rows)
    assert all('separate-paid-package' in r['evidence'] for r in rows)


def test_public_goals_move_without_account_coordinates():
    before=inline_objective_rows(image(),reader=reader)
    moved=cv2.warpAffine(image(),np.float32([[1,0,-4],[0,1,5]]),(720,1280))
    rows=inline_objective_rows(moved,reader=reader)
    assert [r['identity'] for r in rows]==[r['identity'] for r in before]
    assert all((r['box'].x,r['box'].y)==(b['box'].x-4,b['box'].y+5) for b,r in zip(before,rows))


@pytest.mark.parametrize('damage', ['title','caption','counter','cost'])
def test_missing_or_cost_conflicting_public_evidence_never_claims(damage):
    im=image()
    if damage=='title':
        im[131:165,36:236]=0
    elif damage=='caption':
        im[650:683,110:284]=0
        im[842:875,110:284]=0
    elif damage=='counter':
        im[650:680,599:690]=0
        im[842:872,599:690]=0
    else:
        # A foreign premium/resource icon inside either button vetoes the free label.
        im[730:760,523:543]=(255,120,0)
        im[922:952,523:543]=(255,120,0)
    assert not any(r['state']=='AVAILABLE' for r in inline_objective_rows(im,reader=reader))


def test_popup_or_ocr_disagreement_is_not_claimed_state():
    assert not any(r['state']=='NOT_AVAILABLE' for r in inline_objective_rows(image(),reader=reader))
    assert not inline_objective_rows(image(),reader=lambda _:[])
    assert not inline_objective_rows(cv2.imread('tests/fixtures/phase8/paid-offer-one.png'),reader=reader)


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows OCR')
def test_saved_public_rows_with_real_windows_ocr():
    from top_heroes_auto.vision.local_ocr import read_words
    rows=inline_objective_rows(image(),reader=read_words)
    assert len(rows)==2 and all(r['state']=='AVAILABLE' for r in rows)


def test_group_buy_uncertain_caption_alias_cannot_create_new_reward(tmp_path):
    from dataclasses import asdict

    from top_heroes_auto.app.event_claim_reconciliation import bind_saved_rewards
    rows=inline_objective_rows(image(),reader=reader)
    path=tmp_path/'saved.png'
    cv2.imwrite(str(path),image())
    path.with_suffix('.event.json').write_text(json.dumps(dict(reward_rows=[
        {**r,'row':asdict(r['row']),'box':asdict(r['box'])} for r in rows])))
    claim=dict(reward_id='event:original',status='RESERVED',dispatch_state='POSSIBLE',after_evidence='[]',
        before_evidence=json.dumps(dict(persistent_identity='disk',identity=[7,'disk','adb','boot'],
            event='value',page='event:value:inline-objectives',reward=rows[0]['identity'],
            capture=str(path),evidence=rows[0]['evidence'])))
    current=[dict(r,identity='raster-'+str(i)) for i,r in enumerate(rows)]
    bound=bind_saved_rewards(image(),current,[claim],persistent_identity='disk',index=7,family='inline-objectives')
    assert bound[0]['identity']==rows[0]['identity']


def test_production_public_goals_keep_paid_region_excluded_and_expose_scroll(tmp_path,monkeypatch):
    from top_heroes_auto.app import dynamic_event_port as module
    im=image()
    capture=SimpleNamespace(original=im,rotated_from_portrait=False,index=7,serial='explicit',
        boot_id='boot',source_image=tmp_path/'current.png')
    back=BoundingBox(35,1200,55,55)
    observed=SimpleNamespace(captured=capture,page='UNKNOWN',box=lambda _:back,
        overlay=SimpleNamespace(state=ScreenState.UNKNOWN),evidence=lambda:{})
    port=object.__new__(DynamicEventPort)
    port.transport=SimpleNamespace(observe=lambda:observed)
    port.session=SimpleNamespace(target={'persistent_identity':'disk'},manager=SimpleNamespace(
        namespace='n',store=SimpleNamespace(reward_claims=lambda *a:[])),index=7)
    port.current=None
    port.entered='current-event'
    port.task_context=cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    port.unavailable_observations={}
    monkeypatch.setattr(module,'read_words',reader)
    monkeypatch.setattr(module,'event_shell',lambda *a,**k:dict(page='event:value',title='value',
        back=back,tabs=[],selected=[]))
    frame=port.observe()
    from top_heroes_auto.automation.dynamic_events import free_geometry
    rewards=[c for c in frame.controls if c.kind=='reward']
    assert len(rewards)==2
    assert all(free_geometry(c)[1]>615 for c in rewards)
    assert any(c.kind=='scroll' and c.identity=='public-objective-list' for c in frame.controls)
    assert all(any(b.y==0 and b.height>615 for b in c.forbidden) for c in rewards)

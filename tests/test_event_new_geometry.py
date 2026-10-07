"""Saved current geometry and semantic task categories; no live emulator."""
from dataclasses import replace

import cv2
import numpy as np
import pytest

from top_heroes_auto.vision.dynamic_events import (
    competitive_navigation_shell,
    discover_menu_tiles,
    matching_icon_cores,
    menu_art_image,
)
from top_heroes_auto.vision.event_competitive import competitive_indicator_contract
from top_heroes_auto.vision.event_task_grid import task_grid_rows, task_grid_shell
from top_heroes_auto.vision.models import BoundingBox


def image(name):
    return cv2.imread('tests/fixtures/phase8/'+name+'.png')


def test_gallery_compression_and_scroll_keep_one_reusable_visual_child():
    before,after=(image(name) for name in ('menu-before-scroll','menu-after-scroll'))
    old=[c for c in discover_menu_tiles(before) if c.icon_box.x>350][0]
    new=[c for c in discover_menu_tiles(after) if c.icon_box.x>350][0]
    assert old.fingerprint!=new.fingerprint
    assert old.icon_box!=new.icon_box
    known={old.fingerprint:menu_art_image(before,old.icon_box)}
    assert matching_icon_cores(menu_art_image(after,new.icon_box),known)==(old.fingerprint,)
    assert not matching_icon_cores(255-menu_art_image(after,new.icon_box),known)
    known['duplicate']=known[old.fingerprint].copy()
    assert len(matching_icon_cores(menu_art_image(after,new.icon_box),known))==2


@pytest.mark.parametrize('name',['task-grid-partial-free','task-grid-partial-free-variant'])
def test_task_grid_current_frame_owns_close_scroll_and_only_complete_cards(name):
    im=image(name)
    shell=task_grid_shell(im)
    assert shell and shell['permission']=='TASK_GRID'
    assert len(shell['cards'])==3
    assert all(b.y+b.height<1063 for b in shell['cards'])
    assert min(b.x for b in shell['cards']) < shell['scroll'].x < max(b.x for b in shell['cards'])
    assert all(shell['scroll'].x >= b.x+b.width or shell['scroll'].x+shell['scroll'].width <= b.x for b in shell['cards'])
    assert shell['scroll'].y+shell['scroll'].height<shell['back'].y
    moved=cv2.warpAffine(im,np.float32([[1,0,8],[0,1,10]]),(720,1280))
    fresh=task_grid_shell(moved)
    assert fresh and fresh['back']==replace(shell['back'],x=shell['back'].x+8,y=shell['back'].y+10)


@pytest.mark.parametrize('role',['tasks-word','race-word','close-core'])
def test_missing_or_competing_functional_role_cannot_authorize_task_modal(role):
    im=image('task-grid-partial-free')
    b=task_grid_shell(im)['functional_anchors'][role]
    damaged=im.copy()
    damaged[b['y']:b['y']+b['height'],b['x']:b['x']+b['width']]=40
    assert task_grid_shell(damaged) is None
    duplicate=im.copy()
    duplicate[200:200+b['height'],100:100+b['width']]=im[b['y']:b['y']+b['height'],b['x']:b['x']+b['width']]
    assert task_grid_shell(duplicate) is None


def reader(crop,*,label='Nhận',fraction='10/10'):
    h=crop.shape[0]
    return [{'text':'Complete objective ten' if h in {90,180} else label if h in {134,201} else fraction}]


def available_frame(*,bar=True):
    im=image('task-grid-partial-free')
    shell=task_grid_shell(im)
    b=shell['cards'][0]
    roi=im[b.y+round(b.height*.80):b.y+b.height-3,b.x+8:b.x+b.width-8]
    blue=cv2.inRange(cv2.cvtColor(roi,cv2.COLOR_BGR2HSV),(85,60,80),(115,255,255))
    roi[blue>0]=(40,170,100)
    if bar:
        im[b.y+round(b.height*.70):b.y+round(b.height*.80),b.x:b.x+b.width]=(76,57,104)
        cv2.rectangle(im,(b.x+15,b.y+round(b.height*.735)),
            (b.x+b.width-21,b.y+round(b.height*.775)),(40,190,130),-1)
    return im,shell


def test_grid_free_control_requires_complete_fraction_full_bar_and_owned_button():
    im,shell=available_frame()
    rows=task_grid_rows(im,shell,reader=reader)
    assert len(rows)==1 and rows[0]['state']=='AVAILABLE'
    assert rows[0]['identity']=='task-caption:complete objective ten'
    b,t=rows[0]['row'],rows[0]['box']
    assert b.x<t.center[0]<b.x+b.width and b.y<t.center[1]<b.y+b.height
    assert 'qualified-race-task-grid' in rows[0]['evidence']
    no_bar,shell=available_frame(bar=False)
    assert task_grid_rows(no_bar,shell,reader=reader)[0]['state']=='UNKNOWN'
    assert task_grid_rows(im,shell,reader=lambda c:reader(c,fraction='9/10'))[0]['state']=='UNKNOWN'


@pytest.mark.parametrize('label',['Nhận 10 VND','Nhận 10','Mua','Cống Hiến'])
def test_grid_prices_and_resource_actions_never_become_free(label):
    im,shell=available_frame()
    assert not task_grid_rows(im,shell,reader=lambda c:reader(c,label=label))


def test_cost_icon_cannot_hide_behind_mocked_free_label():
    im,shell=available_frame()
    row=task_grid_rows(im,shell,reader=reader)[0]
    b=row['box']
    cv2.rectangle(im,(b.x+10,b.y+10),(b.x+28,b.y+28),(255,100,20),-1)
    assert not task_grid_rows(im,shell,reader=reader)


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows local OCR evidence')
def test_real_partial_grid_claim_is_never_exposed_and_competitive_is_navigation_only():
    from top_heroes_auto.vision.local_ocr import read_words

    im=image('task-grid-partial-free')
    shell=task_grid_shell(im)
    assert not any(r['state']=='AVAILABLE' for r in task_grid_rows(im,shell,reader=read_words))
    im=image('competitive-current-unclaimed')
    shell=competitive_navigation_shell(im,BoundingBox(34,1207,52,47))
    proof=competitive_indicator_contract(im,shell,reader=read_words)
    assert proof and proof['permission']=='BACK_ONLY' and proof['chest_progress']==0
    assert proof['attempt_counter']==5
    for rect in [(40,188,55,205),(475,1022,500,1047),(354,1189,379,1214)]:
        damaged=im.copy()
        x,y,r,b=rect
        damaged[y:b,x:r]=40
        assert not competitive_indicator_contract(damaged,shell,reader=read_words)
    cv2.rectangle(im,(250,760),(440,820),(40,180,90),-1)
    assert not competitive_indicator_contract(im,shell,reader=read_words)


def test_production_partial_grid_exposes_navigation_without_reward(tmp_path,monkeypatch):
    from types import SimpleNamespace

    from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
    from top_heroes_auto.vision.models import ScreenState

    im=image('task-grid-partial-free')
    captured=SimpleNamespace(index=13,name='fixture',serial='explicit',boot_id='boot',
        source_image=tmp_path/'current.png',original=im,rotated_from_portrait=False)
    observed=SimpleNamespace(captured=captured,page='UNKNOWN',box=lambda _:None,
        overlay=SimpleNamespace(state=ScreenState.UNKNOWN),evidence=lambda:{'state':'UNKNOWN'})
    port=object.__new__(DynamicEventPort)
    port.current=None
    port.entered='qualified-event'
    port.rows=()
    port.home_icon_cores={}
    port.menu_icon_cores={}
    port.pending_claim_ids=set()
    port.unavailable_observations={}
    port.task_context=cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    port.session=SimpleNamespace(index=13,target={'persistent_identity':'disk'},
        manager=SimpleNamespace(namespace='fixture',store=SimpleNamespace(reward_claims=lambda *a:())))
    sent=[]
    port.transport=SimpleNamespace(observe=lambda:observed,last=observed,dispatch=lambda *a:sent.append(a))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.read_words',lambda _:[])
    result=port.observe()
    assert result.page.endswith(':race-task-grid') and result.coverage_known
    assert [c.kind for c in result.controls]==['scroll']
    assert result.parent and result.parent.kind=='parent'
    assert not sent


def test_unreadable_complete_green_action_cannot_disappear_into_exhausted_coverage():
    from top_heroes_auto.vision.event_task_grid import unresolved_grid_actions

    im,shell=available_frame()
    assert unresolved_grid_actions(im,shell,[])
    rows=task_grid_rows(im,shell,reader=reader)
    assert not unresolved_grid_actions(im,shell,rows)
    assert not unresolved_grid_actions(image('task-grid-partial-free'),shell,[])


def test_completed_fraction_may_exceed_goal_but_needs_independent_full_bar():
    im,shell=available_frame()
    assert task_grid_rows(im,shell,reader=lambda c:reader(c,fraction='600/500'))[0]['state']=='AVAILABLE'
    assert task_grid_rows(im,shell,reader=lambda c:reader(c,fraction='499/500'))[0]['state']=='UNKNOWN'
    assert task_grid_rows(im,shell,reader=lambda c:reader(c,fraction='600/0'))[0]['state']=='UNKNOWN'


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows local OCR evidence')
def test_current_full_grid_caption_and_exceeded_objective_are_safely_free():
    from top_heroes_auto.vision.local_ocr import read_words

    im=image('task-grid-complete-exceeded')
    shell=task_grid_shell(im)
    rows=task_grid_rows(im,shell,reader=read_words)
    free=[r for r in rows if r['state']=='AVAILABLE']
    assert len(free)==1
    assert free[0]['identity']=='task-caption:tich luy tieu 500 kc'
    assert free[0]['row'].y+free[0]['row'].height<1063
    # Objective wording describes past activity, not a spending control.
    assert free[0]['box'].center[1]>free[0]['row'].y+free[0]['row'].height*.80


def test_reputation_functional_glyphs_do_not_depend_on_animated_art_background():
    from top_heroes_auto.vision.dynamic_events import (
        body_label_box,
        reputation_information,
        side_task_navigation,
    )

    im=image('reputation-current-caption')
    assert reputation_information(im) and side_task_navigation(im)
    b=body_label_box(im,'reputation-level')
    damaged=im.copy()
    damaged[b.y:b.y+b.height,b.x:b.x+b.width]=40
    assert not reputation_information(damaged)
    other=body_label_box(im,'side-tasks-label')
    duplicate=im.copy()
    duplicate[200:200+other.height,100:100+other.width]=im[other.y:other.y+other.height,other.x:other.x+other.width]
    assert side_task_navigation(duplicate) is None


def test_personal_standing_noun_is_not_a_free_claim_label():
    from top_heroes_auto.vision.dynamic_events import event_body_contract

    im=image('reputation-current-caption')
    assert event_body_contract(im,(),None,reader=lambda _: [{'text':'Danh vong ca nhan'}])=='REPUTATION_INFORMATION'
    for word in ('Nhan','Mien Phi','VND','Kich Hoat'):
        assert event_body_contract(im,(),None,reader=lambda _: [{'text':'Danh vong ca nhan '+word}])=='UNSUPPORTED'


def test_competing_old_and_current_glyph_variants_fail_closed():
    from top_heroes_auto.vision.dynamic_events import body_label_box

    im=image('reputation-current-caption')
    for role in ('reputation-level','side-tasks-label'):
        duplicate=im.copy()
        old=cv2.imread('assets/tasks/phase8/'+role+'.png')
        h,w=old.shape[:2]
        duplicate[200:200+h,100:100+w]=old
        assert body_label_box(duplicate,role) is None


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows local OCR evidence')
def test_explicit_claimed_word_and_absent_green_control_are_independent_post_state():
    from top_heroes_auto.vision.local_ocr import read_words

    im=image('task-grid-claimed')
    rows=task_grid_rows(im,task_grid_shell(im),reader=read_words)
    assert len(rows)==1 and rows[0]['state']=='NOT_AVAILABLE'
    assert rows[0]['identity']=='task-caption:tich luy tieu 500 kc'
    assert {'explicit-claimed-label','original-green-control-absent'}.issubset(rows[0]['evidence'])
    damaged=im.copy()
    b=rows[0]['box']
    damaged[b.y:b.y+b.height,b.x:b.x+b.width]=40
    assert not any('explicit-claimed-label' in r['evidence'] for r in task_grid_rows(damaged,task_grid_shell(damaged),reader=read_words))


def test_claimed_word_cannot_coexist_with_active_button_or_duplicate_label():
    from top_heroes_auto.vision.event_task_grid import claimed_grid_label

    im=image('task-grid-claimed')
    card=max(task_grid_shell(im)['cards'],key=lambda b:b.x)
    col=BoundingBox(card.x+8,card.y+round(card.height*.80),card.width-16,round(card.height*.20)-3)
    crop=im[col.y:col.y+col.height,col.x:col.x+col.width].copy()
    assert claimed_grid_label(crop,col)
    ref=cv2.imread('assets/tasks/phase8/task-grid/claimed-word.png',0)
    active=np.full_like(crop,(40,170,100))
    active[17:17+ref.shape[0],38:38+ref.shape[1]][ref>0]=(255,255,255)
    assert claimed_grid_label(active,col) is None
    duplicate=np.full_like(crop,40)
    for y in (4,38):
        duplicate[y:y+ref.shape[0],38:38+ref.shape[1]]=cv2.cvtColor(ref,cv2.COLOR_GRAY2BGR)
    assert claimed_grid_label(duplicate,col) is None


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows local OCR evidence')
def test_full_tall_fraction_and_unmasked_caption_require_agreement():
    from top_heroes_auto.vision.local_ocr import read_words

    im=image('task-grid-tall-fraction')
    shell=task_grid_shell(im)
    rows=task_grid_rows(im,shell,reader=read_words)
    free=[r for r in rows if r['state']=='AVAILABLE']
    assert len(free)==1
    assert free[0]['box'].center==(361,694)
    assert free[0]['identity'].startswith('task-caption:')
    # Destroy the independent filled progress bar while preserving fraction/button.
    damaged=im.copy()
    b=free[0]['row']
    damaged[b.y+round(b.height*.74):b.y+round(b.height*.80),b.x:b.x+b.width]=40
    assert not any(r['state']=='AVAILABLE' for r in task_grid_rows(damaged,shell,reader=read_words))


def test_conflicting_readable_progress_is_never_replaced_by_fallback():
    im,shell=available_frame()
    count=0

    def disagree(crop):
        nonlocal count
        # Existing masked progress renders have a distinctive short height.
        if crop.shape[0] in {124,186}:
            count+=1
            return [{'text':'5/5' if count%2 else '4/5'}]
        return reader(crop)

    rows=task_grid_rows(im,shell,reader=disagree)
    assert count>=2 and rows
    assert not any(r['state']=='AVAILABLE' for r in rows)


@pytest.mark.parametrize('fallback', [('5/5','4/5'),('5/5',''),('5/0','5/0')])
def test_large_progress_fallback_still_rejects_conflict_missing_or_zero_goal(fallback):
    im,shell=available_frame()
    calls=0

    def read(crop):
        nonlocal calls
        if crop.shape[0] in {124,186}:
            return []
        if crop.shape[0] in {204,208,255,260}:
            text=fallback[calls%2]
            calls+=1
            return [{'text':text}]
        return reader(crop)

    rows=task_grid_rows(im,shell,reader=read)
    assert calls>=2 and rows
    assert not any(r['state']=='AVAILABLE' for r in rows)


def test_unmasked_caption_fallback_requires_exact_pair_not_fuzzy_agreement():
    im,shell=available_frame()

    def read(crop):
        h=crop.shape[0]
        if h in {90,180,140,210}:
            return [{'text':'objective complete ten' if h in {90,140} else 'objective complete two'}]
        return reader(crop)

    assert not task_grid_rows(im,shell,reader=read)

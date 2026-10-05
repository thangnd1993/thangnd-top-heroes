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
    assert shell['scroll'].x+shell['scroll'].width<min(b.x for b in shell['cards'])
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
    return [{'text':'Complete objective ten' if h in {76,152} else label if h in {67,134} else fraction}]


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

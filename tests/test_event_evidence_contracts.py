"""Qualified mechanical UI families, current geometry, no live device actions."""
from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.dynamic_events import (
    body_label_box,
    contained_signal_on_known_icon,
    discover_events,
    discover_menu_tiles,
    event_body_contract,
    icon_core_image,
    matching_icon_cores,
    task_reward_rows,
)
from top_heroes_auto.vision.models import BoundingBox

REGION=BoundingBox(490,70,230,442)


def image(name):
    return cv2.imread('tests/fixtures/phase8/'+name+'.png')


def contract(im,text,rows=()):
    return event_body_contract(im,rows,cv2.imread('assets/tasks/phase8/personal-task-tab.png'),
        reader=lambda _: [{'text':text}])


def test_actual_badge_overlapping_corner_requires_current_four_sides():
    im=image('event-gallery-badged-corner')
    found=discover_menu_tiles(im)
    assert len(found)==1 and found[0].icon_box==BoundingBox(364,714,342,290)
    shifted=cv2.warpAffine(im,np.float32([[1,0,-8],[0,1,-30]]),(720,1280))
    moved=discover_menu_tiles(shifted)
    assert any(c.icon_box==BoundingBox(356,684,342,290) for c in moved)
    assert found[0].fingerprint in {c.fingerprint for c in moved}


@pytest.mark.parametrize('rect',[(357,760,375,960),(390,995,670,1015),(670,740,715,980)])
def test_missing_card_side_cannot_be_repaired_from_neighbors(rect):
    im=image('event-gallery-badged-corner')
    x,y,r,b=rect
    im[y:b,x:r]=40
    assert not any(c.icon_box.x>350 for c in discover_menu_tiles(im))


def test_partial_card_and_unattached_badge_are_not_menu_edges():
    found=discover_menu_tiles(image('event-gallery-badged-corner'))
    assert all(c.icon_box.y+c.icon_box.height<1280*.9 for c in found)
    im=image('event-gallery-badged-corner')
    im[400:710]=40
    assert not found or not discover_menu_tiles(im)


def test_gallery_is_navigation_only_and_potential_reward_or_cost_is_unsupported():
    im=image('event-gallery-badged-corner')
    assert contract(im,'3 Ngay 2 Ngay')=='MENU_GRID'
    assert contract(im,'3 Ngay 2 Ngay Nhan')=='UNSUPPORTED'
    assert contract(im,'3 Ngay 2 Ngay VND')=='UNSUPPORTED'
    assert contract(im,'Unknown artwork')=='UNSUPPORTED'
    cv2.rectangle(im,(400,850),(640,912),(40,180,80),-1)
    assert contract(im,'3 Ngay 2 Ngay')=='UNSUPPORTED'


def test_broken_white_outline_fallback_retains_strong_unique_notification():
    candidates=discover_events(image('home-event-broken-outline'),REGION)
    found=[c for c in candidates if c.icon_box==BoundingBox(528,289,79,76)]
    assert len(found)==1 and found[0].qualified and found[0].rim_confidence>.6
    weak=replace(found[0],qualified=False,rim_confidence=.1)
    assert not contained_signal_on_known_icon(weak,())


def test_interior_red_paint_adds_no_edge_and_cannot_hide_an_unowned_badge():
    candidates=discover_events(image('home-event-broken-outline'),REGION)
    interior=[c for c in candidates if contained_signal_on_known_icon(c,candidates)]
    assert len(interior)==1 and not interior[0].qualified
    assert not contained_signal_on_known_icon(interior[0],interior)
    outside=replace(interior[0],box=BoundingBox(680,270,13,16))
    assert not contained_signal_on_known_icon(outside,candidates)
    strong=replace(interior[0],rim_confidence=.4)
    assert not contained_signal_on_known_icon(strong,candidates)


def test_current_icon_core_matches_real_animation_without_threshold_relaxation():
    before=image('home-event-before-animation')
    after=image('home-event-after-animation')
    known={}
    for c in discover_events(before,REGION):
        if c.qualified:
            known[c.fingerprint]=icon_core_image(before,c.icon_box)
    fresh=[c for c in discover_events(after,REGION) if c.qualified]
    assert len(fresh)==len(known)==5
    assert all(len(matching_icon_cores(icon_core_image(after,c.icon_box),known))==1 for c in fresh)
    assert len({matching_icon_cores(icon_core_image(after,c.icon_box),known)[0] for c in fresh})==5
    core=icon_core_image(after,fresh[0].icon_box)
    assert matching_icon_cores(core,{'first':core,'duplicate':core})==('first','duplicate')
    assert not matching_icon_cores(np.zeros_like(core),known)
    assert not matching_icon_cores(255-core,known)


@pytest.mark.parametrize('kind,text,expected',[
    ('event-world-countdown','Sap bat dau','COUNTDOWN_INFORMATION'),
    ('event-schedule','10/02 10/03 10/04 10/05','SCHEDULE'),
])
def test_positive_nonreward_body_contracts_need_paired_functional_evidence(kind,text,expected):
    im=image(kind)
    assert contract(im,text)==expected
    assert contract(im,text+' Nhan')=='UNSUPPORTED'
    assert contract(im,'Unknown body')=='UNSUPPORTED'
    label=body_label_box(im,'world-list-label' if kind=='event-world-countdown' else 'schedule-value')
    assert label
    im[label.y:label.y+label.height,label.x:label.x+label.width]=40
    assert contract(im,text)=='UNSUPPORTED'


def test_schedule_with_extra_green_reward_stays_unknown():
    im=image('event-schedule')
    cv2.rectangle(im,(400,780),(650,850),(50,180,80),-1)
    assert contract(im,'10/02 10/03 10/04 10/05')=='UNSUPPORTED'


def test_duplicate_functional_label_remains_unknown():
    im=image('event-world-countdown')
    label=body_label_box(im,'world-list-label')
    im[300:300+label.height,100:100+label.width]=im[label.y:label.y+label.height,label.x:label.x+label.width]
    assert contract(im,'Sap bat dau')=='UNSUPPORTED'


def test_positive_task_coverage_never_hides_unqualified_complete_rows():
    im=image('task-list-after-partial-prefix')
    template=cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    rows=task_reward_rows(im,template,reader=lambda _: [{'text':'Den'}])
    assert rows and contract(im,'Den',rows)=='TASK_LIST'
    assert contract(im,'Den',rows[:-1])=='UNSUPPORTED'
    assert contract(im,'Den',({**rows[0],'state':'UNKNOWN'},*rows[1:]))=='UNSUPPORTED'


def test_qualified_menu_scroll_uses_current_box_once(monkeypatch):
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep',lambda _:None)
    box=BoundingBox(390,734,137,230)
    scroll=Control('menu-list-vertical',box,('event-shell','qualified-menu-grid','current-card-list'),'scroll')
    frame=EventFrame('fresh',(13,'test','explicit','boot'),'event:unknown-season:current','view',(scroll,))
    port=object.__new__(DynamicEventPort)
    port.current=frame
    sent=[]
    port.transport=SimpleNamespace(last=object(),dispatch=lambda *args:sent.append(args))
    port.navigate(frame,scroll)
    assert sent[0][1:]==('swipe',(458,906,458,792,450))
    assert port.current is None
    with pytest.raises(SafetyError):
        port.navigate(frame,scroll)
    assert len(sent)==1
    unsafe=replace(scroll,evidence=('unknown-grid',))
    current=replace(frame,controls=(unsafe,))
    port.current=current
    with pytest.raises(SafetyError):
        port.navigate(current,unsafe)
    assert len(sent)==1


def home_port(tmp_path,monkeypatch):
    import top_heroes_auto.app.dynamic_event_port as module
    from top_heroes_auto.vision.models import ScreenState

    pictures=iter([image('home-event-before-animation'),image('home-event-after-animation')])
    monkeypatch.setattr(module,'portrait',lambda _:next(pictures))
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    port=object.__new__(DynamicEventPort)
    port.current=None
    port.entered=None
    port.home_icon_cores={}
    port.rows=()
    source=iter([tmp_path/'first.png',tmp_path/'fresh.png'])
    sent=[]

    def observe():
        c=SimpleNamespace(index=13,name='fixture',serial='explicit',boot_id='boot',source_image=next(source))
        return SimpleNamespace(captured=c,page='home',
            box=lambda name: BoundingBox(550,0,150,70) if name=='home-shop-entry' else None,
            overlay=SimpleNamespace(state=ScreenState.UNKNOWN),evidence=lambda:{})

    port.transport=SimpleNamespace(observe=observe,last=object(),dispatch=lambda *args:sent.append(args))
    return port,sent


def test_production_home_recheck_uses_qualified_live_icon_despite_pixel_rounding(tmp_path,monkeypatch):
    port,sent=home_port(tmp_path,monkeypatch)
    frame=port.observe()
    assert frame.coverage_known and not frame.blocked
    assert len(frame.controls)==5 and all(c.kind=='event' for c in frame.controls)
    animated=next(c for c in frame.controls if c.box==BoundingBox(533,289,74,76))
    port.navigate(frame,animated)
    assert len(sent)==1 and sent[0][1:]==('tap',animated.box.center)
    assert port.entered==animated.identity


def test_multiple_cached_artwork_matches_are_blocked_before_input(tmp_path,monkeypatch):
    port,sent=home_port(tmp_path,monkeypatch)
    core=icon_core_image(image('home-event-before-animation'),BoundingBox(533,289,74,76))
    port.home_icon_cores={'first':core,'duplicate':core}
    frame=port.observe()
    assert 'AMBIGUOUS_ICON_CORE' in frame.blocked and not frame.coverage_known
    assert not any(c.box==BoundingBox(533,289,74,76) for c in frame.controls)
    assert not sent

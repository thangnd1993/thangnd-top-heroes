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
    menu_view_key,
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
    frame=EventFrame('fresh',(13,'test','explicit','boot'),'event:unknown-season:current','view',(scroll,),coverage_known=True)
    port=object.__new__(DynamicEventPort)
    port.current=frame
    sent=[]
    port.transport=SimpleNamespace(last=SimpleNamespace(captured=SimpleNamespace(
        original=np.zeros((1280,720,3),np.uint8),rotated_from_portrait=False)),
        dispatch=lambda *args:sent.append(args))
    port.observe=lambda: frame
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


def test_scroll_fingerprint_distinguishes_new_artwork_from_same_grid_and_ignores_clock():
    before=image('event-gallery-badged-corner')
    tick=before.copy()
    tick[940:970,55:300]=50  # Timer, outside card artwork core.
    assert menu_view_key(before)==menu_view_key(tick)
    new=before.copy()
    new[825:920,440:640]=before[520:615,80:280]
    assert menu_view_key(before)!=menu_view_key(new)


def test_current_calendar_accepts_pointed_green_timeline_not_free_button():
    im=image('event-current-calendar')
    assert contract(im,'10/03 10/04 10/05 10/06')=='SCHEDULE'
    cv2.rectangle(im,(400,680),(650,750),(50,180,80),-1)
    assert contract(im,'10/03 10/04 10/05 10/06')=='UNSUPPORTED'


def test_current_calendar_rejects_free_text_or_missing_footer():
    im=image('event-current-calendar')
    assert contract(im,'10/03 10/04 10/05 10/06 Nhan')=='UNSUPPORTED'
    assert contract(im,'Unknown date row')=='UNSUPPORTED'
    b=body_label_box(im,'schedule-footer')
    im[b.y:b.y+b.height,b.x:b.x+b.width]=40
    assert contract(im,'10/03 10/04 10/05 10/06')=='UNSUPPORTED'


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows local OCR evidence')
def test_current_antialiased_header_and_calendar_with_independent_real_ocr():
    from top_heroes_auto.vision.dynamic_events import event_shell
    from top_heroes_auto.vision.local_ocr import read_words

    im=image('event-current-antialiased-header')
    shell=event_shell(im,BoundingBox(34,1209,52,47),reader=read_words)
    assert shell and shell['page'].startswith('event:')
    assert not shell['tabs']  # Navigation shell creates no reward permission.
    gallery=image('event-current-gallery')
    assert event_shell(gallery,BoundingBox(34,1209,52,47),reader=read_words)
    im=image('event-current-calendar')
    template=cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    assert event_body_contract(im,[],template,reader=read_words)=='SCHEDULE'


def test_reputation_summary_owns_only_current_tasks_notification():
    from top_heroes_auto.vision.dynamic_events import reputation_information, side_task_navigation

    im=image('event-current-antialiased-header')
    nav=side_task_navigation(im)
    assert nav and nav['box']==BoundingBox(634,322,37,29)
    assert reputation_information(im)
    assert contract(im,'')=='REPUTATION_INFORMATION'
    assert nav['evidence'] and not any('free' in e for e in nav['evidence'])
    cv2.circle(im,(100,420),10,(255,255,255),-1)
    cv2.circle(im,(100,420),7,(0,0,240),-1)
    assert not reputation_information(im)


def test_tasks_navigation_moves_with_current_visual_anchors():
    from top_heroes_auto.vision.dynamic_events import side_task_navigation

    im=image('event-current-antialiased-header')
    tile=im[295:382,607:702].copy()
    im[295:382,607:702]=40
    im[395:482,527:622]=tile
    nav=side_task_navigation(im)
    assert nav and nav['box']==BoundingBox(554,422,37,29)


def test_tasks_navigation_partial_duplicate_or_no_badge_stays_closed():
    from top_heroes_auto.vision.dynamic_events import side_task_navigation

    for mode in ('label','core','badge','duplicate'):
        im=image('event-current-antialiased-header')
        if mode=='duplicate':
            im[400:429,100:137]=im[322:351,634:671]
        else:
            b={'label':BoundingBox(607,356,94,25),'core':BoundingBox(634,322,37,29),
               'badge':BoundingBox(666,297,24,24)}[mode]
            im[b.y:b.y+b.height,b.x:b.x+b.width]=40
        assert side_task_navigation(im) is None


def test_reputation_summary_extra_green_action_is_not_exhausted():
    from top_heroes_auto.vision.dynamic_events import reputation_information

    im=image('event-current-antialiased-header')
    cv2.rectangle(im,(400,450),(650,520),(50,180,80),-1)
    assert not reputation_information(im)
    assert contract(im,'Nhan')=='UNSUPPORTED'


def test_known_guild_reminder_is_out_of_scope_and_has_no_claim_permission():
    im=image('event-guild-reminder')
    assert contract(im,'Boss Hoi Den Doc het')=='GUILD_REMINDER_OUT_OF_SCOPE'
    assert contract(im,'Boss Hoi Nhan')=='UNSUPPORTED'
    cv2.rectangle(im,(400,680),(650,750),(50,180,80),-1)
    assert contract(im,'Boss Hoi Den Doc het')=='UNSUPPORTED'


def test_guild_reminder_new_row_or_missing_functional_role_stays_unknown():
    im=image('event-guild-reminder')
    b=body_label_box(im,'reminder-guild-boss')
    im[700:700+b.height,100:100+b.width]=im[b.y:b.y+b.height,b.x:b.x+b.width]
    assert contract(im,'Boss Hoi Den Doc het')=='UNSUPPORTED'
    im=image('event-guild-reminder')
    b=body_label_box(im,'reminder-timezone')
    im[b.y:b.y+b.height,b.x:b.x+b.width]=40
    assert contract(im,'Boss Hoi Den Doc het')=='UNSUPPORTED'


def test_event_popup_uses_existing_home_back_policy_and_bounded_budget(monkeypatch):
    from top_heroes_auto.automation.overlays import OverlayBudget
    from top_heroes_auto.vision.models import ScreenState

    p=DynamicEventPort.__new__(DynamicEventPort)
    p.overlay_budget=OverlayBudget()
    p.current=SimpleNamespace(popup=True)
    overlay=SimpleNamespace(state=ScreenState.HOME_OVERLAY,evidence=())
    observed=SimpleNamespace(captured=object(),overlay=overlay)
    calls=[]
    p.transport=SimpleNamespace(last=observed,dispatch=lambda o,a,v:calls.append((a,v)))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.dismiss_overlay_bottom_left',
                        lambda c,d:(58,1203))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep',lambda _:None)
    p.dismiss(p.current)
    p.current=SimpleNamespace(popup=True)  # New qualified frame after the tap.
    p.dismiss(p.current)
    assert calls==[('tap',(58,1203)),('keyevent',(4,))]
    p.current=SimpleNamespace(popup=True)
    with pytest.raises(SafetyError,match='limit'):
        p.dismiss(p.current)
    assert len(calls)==2


def test_generic_known_receipt_never_gets_home_back_fallback(monkeypatch):
    from top_heroes_auto.automation.overlays import OverlayBudget
    from top_heroes_auto.vision.models import ScreenState

    p=DynamicEventPort.__new__(DynamicEventPort)
    p.overlay_budget=OverlayBudget()
    calls=[]
    observed=SimpleNamespace(captured=object(),overlay=SimpleNamespace(
        state=ScreenState.REWARD_RECEIPT,evidence=()))
    p.transport=SimpleNamespace(last=observed,dispatch=lambda o,a,v:calls.append((a,v)))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.dismiss_overlay_bottom_left',
                        lambda c,d:(58,1203))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep',lambda _:None)
    for _ in range(2):
        p.current=SimpleNamespace(popup=True)
        p.dismiss(p.current)
    assert calls==[('tap',(58,1203)),('tap',(58,1203))]
    p.current=SimpleNamespace(popup=False)
    with pytest.raises(SafetyError):
        p.dismiss(p.current)


def test_real_interior_ribbon_requires_unique_current_owner_and_forked_shape():
    from top_heroes_auto.vision.dynamic_events import interior_ribbon_shape

    im=image('home-current-owned-ribbon')
    candidates=discover_events(im,BoundingBox(490,70,230,442))
    ribbons=[c for c in candidates if interior_ribbon_shape(im,c)]
    assert len(ribbons)==1
    ribbon=ribbons[0]
    owner=[c for c in candidates if c.qualified and c.icon_box==ribbon.icon_box]
    assert len(owner)==1 and .2<=ribbon.rim_confidence<.3
    assert contained_signal_on_known_icon(ribbon,candidates,image=im)
    assert not contained_signal_on_known_icon(ribbon,(),image=im)
    assert not contained_signal_on_known_icon(ribbon,(*candidates,owner[0]),image=im)
    assert not contained_signal_on_known_icon(replace(ribbon,rim_confidence=.4),candidates,image=im)
    assert not contained_signal_on_known_icon(replace(ribbon,qualified=True),candidates,image=im)
    assert not contained_signal_on_known_icon(owner[0],candidates,image=im)
    damaged=im.copy()
    b=ribbon.box
    damaged[b.y:b.y+b.height,b.x:b.x+b.width]=40
    assert not contained_signal_on_known_icon(ribbon,candidates,image=damaged)


@pytest.mark.parametrize('variant',['large','small'])
def test_rank_announcement_is_strict_paired_capture_only_transition(variant):
    from top_heroes_auto.vision.dynamic_events import competitive_rank_transition

    im=image('competitive-rank-transition-'+variant)
    found=competitive_rank_transition(im)
    assert found and found['permission']=='WAIT_ONLY'
    assert found['state']=='COMPETITIVE_RANK_TRANSITION'
    assert found['confidence']==min(found['anchor_confidences'].values())>=.98
    assert set(found['anchors'])=={'rank-word','personal-record','challenge'}
    for role in found['anchors']:
        damaged=im.copy()
        b=found['anchors'][role]
        damaged[b['y']:b['y']+b['height'],b['x']:b['x']+b['width']]=40
        assert competitive_rank_transition(damaged) is None
    b=found['anchors']['rank-word']
    duplicate=im.copy()
    duplicate[400:400+b['height'],b['x']:b['x']+b['width']]=im[b['y']:b['y']+b['height'],b['x']:b['x']+b['width']]
    assert competitive_rank_transition(duplicate) is None


@pytest.mark.parametrize('name',['competitive-event','event-current-gallery','home-current-owned-ribbon','event-current-calendar'])
def test_unrelated_body_cannot_gain_rank_wait_permission(name):
    from top_heroes_auto.vision.dynamic_events import competitive_rank_transition

    assert competitive_rank_transition(image(name)) is None


def test_real_unbadged_ribbon_does_not_hide_missing_or_weak_notification():
    from top_heroes_auto.vision.dynamic_events import decorative_ribbon_on_icon

    im=image('home-current-new-icons')
    candidates=discover_events(im,REGION)
    ribbon=[c for c in candidates if decorative_ribbon_on_icon(im,c)]
    assert len(ribbon)==1
    c=ribbon[0]
    assert not c.qualified
    assert not decorative_ribbon_on_icon(im,replace(c,icon_box=None))
    assert not decorative_ribbon_on_icon(im,replace(c,rim_confidence=.4))
    assert not decorative_ribbon_on_icon(im,replace(c,qualified=True))
    damaged=im.copy()
    b=c.box
    damaged[b.y:b.y+b.height,b.x:b.x+b.width]=40
    assert not decorative_ribbon_on_icon(damaged,c)


@pytest.mark.skipif(__import__('sys').platform!='win32',reason='Windows local OCR evidence')
def test_current_gallery_timer_ocr_is_independent_of_full_body_artwork():
    from top_heroes_auto.vision.dynamic_events import gallery_timer_evidence, menu_card_boxes
    from top_heroes_auto.vision.local_ocr import read_words

    im=image('event-current-gallery-timer')
    cards=menu_card_boxes(im)
    assert gallery_timer_evidence(im,cards,reader=read_words)
    template=cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    assert event_body_contract(im,[],template,reader=read_words)=='MENU_GRID'
    assert not gallery_timer_evidence(im,cards,reader=lambda _: [{'text':'Unrelated text'}])
    readings=__import__('itertools').cycle([{'text':'27Ngay'},{'text':'28Ngay'}])
    assert not gallery_timer_evidence(im,cards,reader=lambda _: [next(readings)])

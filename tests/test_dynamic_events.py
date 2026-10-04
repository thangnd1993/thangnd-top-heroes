"""Dynamic traversal and current-frame discovery; no live device calls."""
from dataclasses import replace

import cv2
import numpy as np
import pytest

from top_heroes_auto.automation.dynamic_events import (
    Control,
    DynamicEventExplorer,
    EventFrame,
    Limits,
    free_geometry,
)
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.dynamic_events import discover_badges
from top_heroes_auto.vision.models import BoundingBox

BOX = BoundingBox(100,100,30,30)
IDENTITY = (13,'user name','emulator-6000','boot')


def control(name, kind='child', **kw):
    return Control(name,BOX,('context','target','available'),kind,**kw)


def frame(page, n, controls=(), **kw):
    return EventFrame(str(n),IDENTITY,page,f'{page}:{n}',tuple(controls),coverage_known=True,**kw)


class Port:
    def __init__(self, frames, journal='VERIFIED'):
        self.frames = iter(frames)
        self.calls = []
        self.journal = journal
        self.last = None

    def observe(self):
        try:
            self.last = next(self.frames)
        except StopIteration:
            if self.last.page != 'home':
                raise
            self.last = replace(self.last,capture=self.last.capture+'-fresh')
        return self.last

    def navigate(self, f, c):
        self.calls.append((f.page,c.kind,c.identity,c.box.center))

    def claim(self, f, c):
        self.calls.append((f.page,'reward',c.identity,c.box.center))
        return dict(journal=self.journal,claim_dispatched=True,reward=c.identity)

    def dismiss(self, f):
        self.calls.append((f.page,'dismiss'))


def test_multiple_tabs_stay_inside_event_and_rediscover_home():
    event, tab1, tab2 = control('new-art','event'),control('one'),control('two')
    reward1 = control('free-diamonds','reward',cost='FREE',available=True,diamond_reward=True)
    reward2 = replace(reward1,identity='sibling')
    parent = control('back','parent')
    p = Port([frame('home',0,[event]),frame('event',1,[tab1,tab2]),
              frame('tab1',2,[reward1],parent=parent),frame('tab1',3,[],parent=parent),
              frame('event',4,[tab1,tab2],parent=parent),frame('tab2',5,[reward2],parent=parent),
              frame('tab2',6,[],parent=parent),frame('event',7,[tab1,tab2],parent=parent),frame('home',8)])
    result = DynamicEventExplorer().run(p)
    assert result.result == 'SUCCESS'
    assert len(result.rewards) == 2
    assert sum(c[1]=='event' for c in p.calls) == 1
    assert result.events['new-art']['result'] == 'EXHAUSTED'


def test_popup_preserves_event_context():
    e,r,b = control('icon','event'),control('r','reward',cost='FREE',available=True),control('back','parent')
    p = Port([frame('home',0,[e]),frame('page',1,[r]),frame('receipt',2,popup=True),
              frame('page',3,[],parent=b),frame('home',4)])
    assert DynamicEventExplorer().run(p).result == 'SUCCESS'
    assert [c[1] for c in p.calls] == ['event','reward','dismiss','parent']


@pytest.mark.parametrize('cost',['DIAMONDS','MONEY','TICKETS','RESOURCE','PREMIUM'])
def test_paid_targets_never_dispatched(cost):
    e,r,b = control('icon','event'),control('paid','reward',cost=cost,available=True),control('back','parent')
    p = Port([frame('home',0,[e]),frame('page',1,[r],parent=b),frame('home',2)])
    result = DynamicEventExplorer().run(p)
    assert len(result.paid_rejected) == 1
    assert not result.rewards
    assert all(c[1] != 'reward' for c in p.calls)


@pytest.mark.parametrize('change',[dict(cost='UNKNOWN'),dict(evidence=('word',)),
                                     dict(forbidden=(BOX,)),dict(available=False)])
def test_ambiguous_free_or_paid_overlap_rejected(change):
    r = control('r','reward',cost='FREE',available=True)
    with pytest.raises(SafetyError):
        free_geometry(replace(r,**change))


def test_free_diamond_contents_are_not_diamond_cost():
    assert free_geometry(control('diamond','reward',cost='FREE',available=True,diamond_reward=True)) == BOX.center


def test_unknown_never_tapped_or_counted_exhausted():
    p = Port([frame('home',0,[control('new','event')]),frame('UNKNOWN',1)])
    result = DynamicEventExplorer().run(p)
    assert result.result == 'BLOCKED'
    assert len(p.calls) == 1
    assert result.blocked[-1]['reason'] == 'UNKNOWN_SCREEN'


def test_no_badge_does_not_enter_event():
    p = Port([frame('home',0)])
    assert DynamicEventExplorer().run(p).result == 'SUCCESS'
    assert not p.calls


def test_repeated_state_terminates_no_progress():
    a=frame('home',0,[control('new','event')])
    p=Port([a,replace(a,capture='fresh')])
    result=DynamicEventExplorer().run(p)
    assert result.blocked[-1]['reason']=='NO_PROGRESS'
    assert len(p.calls)==1


def test_stale_capture_or_identity_change_fail_closed():
    a=frame('home',0,[control('new','event')])
    for b in (a,replace(a,capture='fresh',identity=(14,*IDENTITY[1:]))):
        p=Port([a,b])
        assert DynamicEventExplorer().run(p).result=='BLOCKED'
        assert len(p.calls)==1


@pytest.mark.parametrize('axis',['horizontal','vertical'])
def test_scroll_reacquires_changed_target_coordinates(axis):
    e,s,b = control('e','event'),control(axis,'scroll'),control('back','parent')
    r = control('r','reward',cost='FREE',available=True)
    r = replace(r,box=BoundingBox(300,400,40,40))
    a=frame('page',4,[s],parent=b)
    p=Port([frame('home',0,[e]),frame('page',1,[s]),frame('page',2,[s,r]),
            a,replace(a,capture='5'),frame('home',6)])
    result=DynamicEventExplorer().run(p)
    assert result.result=='SUCCESS'
    assert next(c for c in p.calls if c[1]=='reward')[-1]==(320,420)


def test_depth_limit_does_not_visit_child():
    p=Port([frame('home',0,[control('e','event')]),frame('page',1,[control('nested')],
            parent=control('back','parent')),frame('home',2)])
    result=DynamicEventExplorer(Limits(depth=1)).run(p)
    assert any(b['reason']=='DEPTH_LIMIT' for b in result.blocked)
    assert all(c[1]!='child' for c in p.calls)


def test_action_limit_stops_before_next_input():
    p=Port([frame('home',0,[control('e','event')]),frame('page',1,[control('nested')])])
    result=DynamicEventExplorer(Limits(actions=1)).run(p)
    assert len(p.calls)==1
    assert result.blocked[-1]['reason']=='LIMIT_REACHED'


def test_unqualified_coverage_cannot_pass():
    p=Port([replace(frame('home',0),coverage_known=False)])
    assert DynamicEventExplorer().run(p).result=='BLOCKED'


def test_duplicate_runtime_identity_fails_closed():
    e=control('same','event')
    p=Port([frame('home',0,[e,replace(e,box=BoundingBox(200,100,30,30))])])
    result=DynamicEventExplorer().run(p)
    assert not p.calls
    assert result.blocked[-1]['reason']=='AMBIGUOUS_EVENT_IDENTITY'


def badge_image(x=600,y=120,number=False):
    image=np.full((1280,720,3),40,np.uint8)
    # Unknown seasonal artwork below/left; no icon template is supplied.
    cv2.rectangle(image,(x-40,y+15),(x-5,y+50),(200,170,20),-1)
    cv2.circle(image,(x,y),11,(250,250,250),-1)
    cv2.circle(image,(x,y),9,(15,20,245),-1)
    if number:
        cv2.putText(image,'3',(x-5,y+5),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
    return image


@pytest.mark.parametrize('number',[False,True])
def test_dot_and_numbered_badge_on_unfamiliar_icon(number):
    found=discover_badges(badge_image(number=number),BoundingBox(480,60,240,480))
    assert len(found)==1 and found[0].qualified
    assert found[0].box.center==(600,120)


def test_moving_icon_uses_current_box_and_same_fingerprint():
    a=discover_badges(badge_image(),BoundingBox(480,60,240,480))[0]
    b=discover_badges(badge_image(550,250),BoundingBox(480,60,240,480))[0]
    assert a.fingerprint==b.fingerprint
    assert a.box!=b.box


def test_red_art_without_notification_rim_is_not_qualified():
    image=np.full((1280,720,3),40,np.uint8)
    cv2.circle(image,(600,120),10,(0,0,255),-1)
    found=discover_badges(image,BoundingBox(480,60,240,480))
    assert found and not any(c.qualified for c in found)


def test_registry_uses_existing_pipeline():
    from top_heroes_auto.app.flow_registry import production_registry
    flows=production_registry().snapshot()
    assert flows[-1].id=='events'
    assert flows[-1].rewards==('dynamic-event-exploration',)


def test_development_scope_is_random_only(monkeypatch):
    from top_heroes_auto.app import automation_fleet, diagnostic, main
    calls=[]
    monkeypatch.setattr(diagnostic,'_manager',lambda _:object())
    monkeypatch.setattr(automation_fleet,'run',lambda *a,**kw:calls.append(kw))
    main.main(['automation-acceptance','--random-test','--development-flow','events'])
    assert calls[0]['random_test']
    assert {k for k,v in calls[0]['enabled'].items() if v}=={'events'}
    with pytest.raises(ValueError):
        main.main(['automation-acceptance','--confirm-non-protected','--development-flow','events'])
    assert len(calls)==1


def test_production_port_cannot_claim_unqualified_event():
    from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
    port=object.__new__(DynamicEventPort)
    with pytest.raises(SafetyError):
        port.claim(None,None)


def test_saved_home_badges_are_discovered_without_event_names():
    image=cv2.imread('tests/fixtures/phase7/home-live.png')
    found=discover_badges(image,BoundingBox(490,65,230,445))
    qualified=[c for c in found if c.qualified]
    assert len(qualified)==6
    assert all(c.box.x>490 and c.box.y<510 for c in qualified)


def test_event_requires_separate_outlined_icon_not_just_badge():
    from top_heroes_auto.vision.dynamic_events import discover_events
    region=BoundingBox(490,65,230,445)
    assert not any(c.qualified for c in discover_events(badge_image(),region))
    image=cv2.imread('tests/fixtures/phase7/home-live.png')
    events=[c for c in discover_events(image,region) if c.qualified]
    assert len(events)==6
    assert all(c.icon_box and c.icon_box.width>c.box.width*2 for c in events)


def test_actual_icons_relocated_keep_current_derived_boxes():
    from top_heroes_auto.vision.dynamic_events import discover_events
    image=cv2.imread('tests/fixtures/phase7/home-live.png')
    moved=cv2.warpAffine(image,np.float32([[1,0,-60],[0,1,40]]),(720,1280))
    a=[c for c in discover_events(image,BoundingBox(490,65,230,445)) if c.qualified]
    b=[c for c in discover_events(moved,BoundingBox(430,105,290,445)) if c.qualified]
    assert len(a)==len(b)==6
    assert [c.fingerprint for c in a]==[c.fingerprint for c in b]
    assert [(c.icon_box.x-60,c.icon_box.y+40) for c in a]==[(c.icon_box.x,c.icon_box.y) for c in b]


def test_tabs_share_one_continuous_visit_without_back_between_tabs():
    event=control('e','event')
    t1,t2=control('tab-one','tab'),control('tab-two','tab')
    back=control('back','parent')
    p=Port([frame('home',0,[event]),frame('event:initial',1,[t1,t2],parent=back),
            frame('event:one',2,[t2],parent=back),frame('event:two',3,[t1],parent=back),frame('home',4)])
    result=DynamicEventExplorer().run(p)
    assert result.result=='SUCCESS'
    assert [c[1] for c in p.calls]==['event','tab','tab','parent']


def test_real_shared_event_shell_discovers_both_badged_tabs():
    from top_heroes_auto.vision.dynamic_events import event_shell
    image=cv2.imread('tests/fixtures/phase8/event-shell.png')
    shell=event_shell(image,BoundingBox(34,1209,52,47),reader=lambda _: [{'text':'Event'}])
    assert shell and len(shell['tabs'])==2 and len(shell['selected'])==1
    assert shell['tabs'][0].icon_box.x < shell['tabs'][1].icon_box.x
    # Body Boss/Guild 'Go' is never a tab or an authorized claim target.
    assert all(c.icon_box.y>1170 for c in shell['tabs'])


def test_shared_shell_needs_no_predeclared_event_name():
    from top_heroes_auto.vision.dynamic_events import event_shell
    image=cv2.imread('tests/fixtures/phase8/event-shell.png')
    shell=event_shell(image,BoundingBox(34,1209,52,47),reader=lambda _: [{'text':'Future seasonal title'}])
    assert shell['title']=='future seasonal title'


def test_unreadable_or_conflicting_header_is_unknown():
    from top_heroes_auto.vision.dynamic_events import event_shell
    image=cv2.imread('tests/fixtures/phase8/event-shell.png')
    words=iter([[{'text':'Event'}],[{'text':'Different'}]])
    assert event_shell(image,BoundingBox(34,1209,52,47),reader=lambda _: next(words)) is None
    assert event_shell(image,BoundingBox(34,1209,52,47),reader=lambda _: []) is None
    assert event_shell(image,None,reader=lambda _: [{'text':'Event'}]) is None


def test_gold_header_alone_does_not_qualify_a_page():
    from top_heroes_auto.vision.dynamic_events import event_shell
    image=cv2.imread('tests/fixtures/phase8/event-shell.png')
    image[:100]=40
    assert event_shell(image,BoundingBox(34,1209,52,47),reader=lambda _: [{'text':'Event'}]) is None


def test_identical_tab_icons_in_nested_groups_do_not_suppress_each_other():
    event=control('e','event')
    tab=control('same-icon','tab')
    child=control('submenu')
    back=control('back','parent')
    p=Port([frame('home',0,[event]),frame('outer',1,[tab],parent=back),
            frame('outer:selected',2,[child],parent=back),frame('inner',3,[tab],parent=back),
            frame('inner:selected',4,[],parent=back),frame('outer:selected',5,[child],parent=back),frame('home',6)])
    assert DynamicEventExplorer().run(p).result=='SUCCESS'
    assert sum(c[1]=='tab' for c in p.calls)==2


def test_clock_or_art_animation_is_not_navigation_progress():
    origin=frame('home',0,[control('e','event')])
    changed=replace(origin,capture='fresh',fingerprint='clock-ticked')
    p=Port([origin,changed])
    result=DynamicEventExplorer().run(p)
    assert result.blocked[-1]['reason']=='NO_PROGRESS'
    assert len(p.calls)==1


def test_long_gold_title_uses_complete_isolated_glyphs():
    from top_heroes_auto.vision.dynamic_events import event_shell
    image=cv2.imread('tests/fixtures/phase8/event-long-header.png')
    crops=[]

    def reader(crop):
        crops.append(crop)
        return [{'text':'Trin Chien Chqng V?ng'}]

    shell=event_shell(image,BoundingBox(34,1209,52,47),reader=reader)
    assert shell and shell['title']=='trin chien chqng v?ng'
    assert len(crops)==2 and crops[1].shape[1]==2*crops[0].shape[1]
    assert crops[0].shape[1] > image.shape[1]*.84
    assert set(np.unique(crops[0])) <= {0,255}
    assert np.all(crops[0][:20]==255)
    # This header qualifies navigation, never any body reward.
    assert all(c.icon_box.y > 1170 for c in shell['tabs'])


def test_long_header_still_rejects_inconsistent_readings():
    from top_heroes_auto.vision.dynamic_events import event_shell
    image=cv2.imread('tests/fixtures/phase8/event-long-header.png')
    readings=iter([[{'text':'Long title'}],[{'text':'Other title'}]])
    assert event_shell(image,BoundingBox(34,1209,52,47),reader=lambda _:next(readings)) is None


def test_real_badged_tile_grid_uses_current_closed_card():
    from top_heroes_auto.vision.dynamic_events import discover_menu_tiles
    image=cv2.imread('tests/fixtures/phase8/event-long-header.png')
    found=discover_menu_tiles(image)
    assert len(found)==1 and found[0].icon_box==BoundingBox(14,714,342,290)
    moved=cv2.warpAffine(image,np.float32([[1,0,20],[0,1,-40]]),(720,1280))
    shifted=discover_menu_tiles(moved)
    assert any(c.icon_box==BoundingBox(34,674,342,290) for c in shifted)
    assert found[0].fingerprint in {c.fingerprint for c in shifted}


def test_badge_without_closed_menu_grid_cannot_be_a_child():
    from top_heroes_auto.vision.dynamic_events import discover_menu_tiles
    assert not discover_menu_tiles(badge_image())
    image=cv2.imread('tests/fixtures/phase8/event-long-header.png')
    image[710:1010,:365]=40
    assert not discover_menu_tiles(image)


def task_rows(image,words='Nhan'):
    from top_heroes_auto.vision.dynamic_events import task_reward_rows
    return task_reward_rows(image,cv2.imread('assets/tasks/phase8/personal-task-tab.png'),
        reader=lambda _: [{'text':words}])


def test_real_task_claim_requires_context_items_and_separate_free_column():
    image=cv2.imread('tests/fixtures/phase8/task-reward-list.png')
    rows=task_rows(image)
    assert len(rows)==1 and rows[0]['state']=='AVAILABLE'
    assert rows[0]['box']==BoundingBox(537,557,151,67)
    assert rows[0]['box'].center==(612,590)
    # Paid diamond refresh and all blue Go controls are excluded.
    assert all(r['box'].y<1000 for r in rows)
    shifted=cv2.warpAffine(image,np.float32([[1,0,0],[0,1,20]]),(720,1280))
    moved=task_rows(shifted)
    assert moved[0]['identity']==rows[0]['identity']
    assert moved[0]['box'].y==rows[0]['box'].y+20


@pytest.mark.parametrize('words',['Nhan 100','Nhan VND','Nhan 10 diamonds','Activate','Buy','Nhan tickets','Nhan wood'])
def test_attached_cost_or_activation_label_is_not_a_free_action(words):
    assert not task_rows(cv2.imread('tests/fixtures/phase8/task-reward-list.png'),words)


def test_task_claim_rejects_attached_currency_icon_and_missing_reward_context():
    image=cv2.imread('tests/fixtures/phase8/task-reward-list.png')
    currency=image.copy()
    cv2.rectangle(currency,(548,570),(576,604),(255,180,20),-1)
    assert not task_rows(currency)
    absent=image.copy()
    absent[410:470]=40
    assert not task_rows(absent)
    items=image.copy()
    items[548:640,130:395]=40
    assert not task_rows(items)


def test_task_row_completion_keeps_identity_independent_of_action_label():
    image=cv2.imread('tests/fixtures/phase8/task-reward-list.png')
    before=task_rows(image)[0]
    # Actual blue Go UI from the next row replaces the available control.
    image[557:624,537:688]=image[726:793,537:688]
    after=task_rows(image,'Den')
    row=next(r for r in after if r['identity']==before['identity'])
    assert row['state']=='NOT_AVAILABLE' and row['box']==before['box']


def test_conflicting_action_ocr_does_not_authorize_claim():
    from top_heroes_auto.vision.dynamic_events import task_reward_rows
    calls=iter([{'text':'Nhan'},{'text':'Buy'}]*3)
    assert not task_reward_rows(cv2.imread('tests/fixtures/phase8/task-reward-list.png'),
        cv2.imread('assets/tasks/phase8/personal-task-tab.png'),reader=lambda _:[next(calls)])


def test_production_list_swipe_is_inside_current_cards_and_consumes_frame(monkeypatch):
    from types import SimpleNamespace

    from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep',lambda _:None)
    surface=BoundingBox(150,500,270,450)
    scroll=Control('task-list-vertical',surface,('context','list','excluded-paid'),'scroll')
    current=frame('event:new-season:personal-tasks',1,[scroll])
    port=object.__new__(DynamicEventPort)
    port.current=current
    sent=[]
    port.transport=SimpleNamespace(last=object(),dispatch=lambda *args:sent.append(args))
    port.navigate(current,scroll)
    assert sent[0][1:] == ('swipe',(285,838,285,612,450))
    assert port.current is None
    with pytest.raises(SafetyError):
        port.navigate(current,scroll)
    assert len(sent)==1

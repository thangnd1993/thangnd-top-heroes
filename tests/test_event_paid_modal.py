"""Paid offer evidence permits only safe close, never reward or coverage PASS."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.event_paid_modal import paid_modal_navigation
from top_heroes_auto.vision.models import ScreenState

ROOT = Path(__file__).parent/'fixtures/phase8'


def image(name='paid-offer-one'):
    return cv2.imread(str(ROOT/(name+'.png')))


@pytest.mark.parametrize('name',['paid-offer-one','paid-offer-two'])
def test_current_paid_modal_only_qualifies_close(name):
    im=image(name)
    result=paid_modal_navigation(im)
    assert result and result['permission']=='NAVIGATION_ONLY'
    assert not result['coverage_known'] and not result['claim_authorized']
    assert result['close'].y<result['paid_region'].y
    # A red gift badge elsewhere remains unqualified, never assumed inactive.
    assert 'notification_observed' not in result


@pytest.mark.parametrize('role',['close','remaining','vnd'])
@pytest.mark.parametrize('mode',['missing','weak','duplicate'])
def test_ambiguous_paid_modal_has_no_close_permission(role,mode):
    im=image()
    # Qualified functional crop locations are fixture mutations, never runtime coordinates.
    box={'close':(638,115,45,46),'remaining':(270,937,181,27),'vnd':(259,1009,40,18)}[role]
    if role!='close':
        from top_heroes_auto.vision.resources import template_folder
        refs={'remaining':'purchase-remaining','vnd':'vnd-word'}
        ref=cv2.imread(str(template_folder().parent/'tasks/phase8/paid-modal'/(refs[role]+'.png')),0)
        hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
        mask=(cv2.inRange(hsv,(0,90,70),(25,255,220)) if role=='remaining'
              else cv2.inRange(hsv,(0,0,180),(179,110,255)))
        _,_,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(mask,ref,cv2.TM_CCOEFF_NORMED))
        box=(x,y,ref.shape[1],ref.shape[0])
    x,y,w,h=box
    patch=im[y:y+h,x:x+w].copy()
    if mode=='duplicate':
        im[400:400+h,100:100+w]=patch
    else:
        im[y:y+h,x:x+w]=cv2.GaussianBlur(patch,(15,15),5) if mode=='weak' else 0
    assert paid_modal_navigation(im) is None


def test_modal_can_move_and_price_digits_can_change():
    im=image()
    current=paid_modal_navigation(im)
    b=current['paid_region']
    im[b.y+10:b.y+b.height-10,b.x+90:b.x+b.width-15]=im[b.y+5,b.x+60]
    # Preserve the VND glyph; no digits authorize navigation or purchase.
    assert paid_modal_navigation(im)
    moved=im.copy()
    c=current['close']
    patch=moved[c.y:c.y+c.height,c.x:c.x+c.width].copy()
    moved[c.y:c.y+c.height,c.x:c.x+c.width]=0
    moved[c.y+8:c.y+8+c.height,c.x-6:c.x-6+c.width]=patch
    new=paid_modal_navigation(moved)
    assert new and new['close']==replace(current['close'],x=current['close'].x-6,y=current['close'].y+8)


@pytest.mark.parametrize('name',['world-map-one','world-attack-confirmation','task-grid-tall-fraction'])
def test_unrelated_free_world_and_attack_screens_do_not_qualify_paid_close(name):
    assert paid_modal_navigation(image(name)) is None


def port(tmp_path,monkeypatch):
    im=image()
    captured=SimpleNamespace(index=13,name='fixture',serial='explicit',boot_id='boot',
        source_image=tmp_path/'current.png',original=im,rotated_from_portrait=False)
    observed=SimpleNamespace(captured=captured,page='UNKNOWN',box=lambda _:None,
        overlay=SimpleNamespace(state=ScreenState.UNKNOWN),evidence=lambda:{'state':'UNKNOWN'})
    p=DynamicEventPort.__new__(DynamicEventPort)
    p.current=None
    p.entered='qualified-event'
    p.rows=()
    p.home_icon_cores={}
    p.menu_icon_cores={}
    p.pending_claim_ids=set()
    p.unavailable_observations={}
    p.task_context=cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    p.session=SimpleNamespace(index=13,target={'persistent_identity':'disk'},
        manager=SimpleNamespace(namespace='fixture',store=SimpleNamespace(reward_claims=lambda *a:())))
    sent=[]
    p.transport=SimpleNamespace(observe=lambda:observed,last=observed,dispatch=lambda *a:sent.append(a))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.read_words',lambda _:[])
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep',lambda _:None)
    return p,sent


def test_production_navigation_remains_blocked_and_sends_only_one_close(tmp_path,monkeypatch):
    p,sent=port(tmp_path,monkeypatch)
    frame=p.observe()
    assert frame.page.endswith(':paid-modal') and not frame.coverage_known
    assert frame.controls==() and frame.parent.kind=='parent'
    assert 'UNQUALIFIED_PAID_MODAL_CONTENT' in frame.blocked and not sent
    p.navigate(frame,frame.parent)
    assert len(sent)==1 and sent[0][1:]==('tap',frame.parent.box.center)
    assert p.current is None
    with pytest.raises(SafetyError):
        p.navigate(frame,frame.parent)
    assert len(sent)==1


@pytest.mark.parametrize('change',['identity','close','popup','coverage','controls'])
def test_fresh_capture_conflict_sends_no_input(tmp_path,monkeypatch,change):
    p,sent=port(tmp_path,monkeypatch)
    frame=p.observe()
    kwargs={'identity':dict(identity=(14,'other','other-explicit','boot')),
            'close':dict(parent=replace(frame.parent,box=replace(frame.parent.box,x=200))),
            'popup':dict(popup=True),'coverage':dict(coverage_known=True),
            'controls':dict(controls=(replace(frame.parent,kind='reward'),))}[change]
    fresh=replace(frame,**kwargs)
    p.observe=lambda:fresh
    with pytest.raises(SafetyError):
        p.navigate(frame,frame.parent)
    assert not sent



def test_unqualified_modal_is_not_exhausted_but_independent_event_continues():
    from test_dynamic_events import Port, control, frame

    from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer
    first,second=control('unqualified-offer','event'),control('independent-event','event')
    close=control('paid-close','parent')
    back=control('back','parent')
    reward=control('free','reward',cost='FREE',available=True)
    blocked=replace(frame('event:offer:paid-modal',1,parent=close),coverage_known=False,
                    blocked=('UNQUALIFIED_PAID_MODAL_CONTENT',))
    p=Port([frame('home',0,[first,second]),blocked,frame('home',2,[first,second]),
            frame('event:independent',3,[reward],parent=back),
            frame('event:independent',4,[],parent=back),frame('home',5,[])])
    result=DynamicEventExplorer().run(p)
    assert result.events[first.identity]['result']=='BLOCKED'
    assert result.events[second.identity]['result']=='EXHAUSTED'
    assert result.result!='SUCCESS'
    assert len(result.rewards)==1 and result.rewards[0]['journal']=='VERIFIED'
    assert [c[1] for c in p.calls]==['event','parent','event','reward','parent']


def test_uncertain_paid_close_is_consumed_and_never_retried(tmp_path,monkeypatch):
    p,sent=port(tmp_path,monkeypatch)
    frame=p.observe()
    def fail(*args):
        sent.append(args)
        raise OSError('Uncertain transport')
    p.transport.dispatch=fail
    with pytest.raises(OSError):
        p.navigate(frame,frame.parent)
    assert p.current is None and len(sent)==1
    with pytest.raises(SafetyError):
        p.navigate(frame,frame.parent)
    assert len(sent)==1

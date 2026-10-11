from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.relic_expedition import quick_send


def fixture():
    return cv2.imread(str(Path(__file__).parent/'fixtures/phase8/relic-quick-send.png'))


def detect(image):
    return quick_send(image,cv2.imread('assets/tasks/phase8/personal-task-tab.png'),reader=None)


def test_real_quick_send_is_separate_from_diamond_refresh():
    result = detect(fixture())
    assert result and result['box'].center == (586,1104)
    assert result['forbidden'][0].x+result['forbidden'][0].width < result['box'].x


@pytest.mark.parametrize('defect',['title','occluded','duplicate','paid','green'])
def test_unsafe_send_stays_unqualified(defect):
    image = fixture()
    if defect == 'title':
        image[135:190,25:325] = 0
    elif defect == 'occluded':
        image[1078:1132,505:672] = 0
    elif defect == 'duplicate':
        image[1062:1146,30:238] = image[1062:1146,482:690].copy()
    elif defect == 'paid':
        image[1105:1134,490:520] = image[1105:1134,294:324].copy()
    else:
        crop=image[1062:1146,482:690]
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        hsv[:,:,0][hsv[:,:,1]>60]=55
        image[1062:1146,482:690]=cv2.cvtColor(hsv,cv2.COLOR_HSV2BGR)
    assert detect(image) is None


def test_current_geometry_moves_with_button():
    image=fixture()
    button=image[1058:1150,478:696].copy()
    image[1058:1150,478:696]=0
    image[1052:1144,478:696]=button
    assert detect(image)['box'].y == 1056


def test_mission_dispatch_intent_is_durable_and_cannot_repeat(rig,tmp_path):
    manager,_,store=rig
    port=object.__new__(DynamicEventPort)
    port.session=SimpleNamespace(manager=manager,index=7,name='Farm',target={'persistent_identity':'fixture-disk-7'})
    port.folder=tmp_path
    action=Control('relic-expedition-confirm-send',BoundingBox(482,1062,208,84),
        ('context','qualified-button','free-mission'),'mission',cost='FREE',available=True)
    original=EventFrame('original',(7,'fixture-disk-7','explicit','boot'),'event:personal-tasks','a',(action,))
    fresh=replace(original,capture='fresh')
    after=replace(original,capture='after')
    frames=iter([fresh,after,fresh])
    def observe():
        port.current=next(frames)
        return port.current
    port.observe=observe
    calls=[]
    def dispatch(*a,**k):
        k['before_input']()
        assert store.reward_claims(manager.namespace,7)[0]['dispatch_state']=='POSSIBLE'
        calls.append(a)
    port.transport=SimpleNamespace(last=object(),dispatch=dispatch)
    port.current=original
    first=port.send_mission(original,action)
    assert first['mission_dispatched'] and first['journal']=='RESERVED'
    assert first['first_post_capture']=='after' and first['action_type']=='MISSION_SEND_NOT_REWARD'
    port.current=original
    second=port.send_mission(original,action)
    assert not second['mission_dispatched'] and second['result']=='ALREADY_ATTEMPTED'
    assert len(calls)==1


def test_real_confirm_requires_title_checks_and_free_button():
    from top_heroes_auto.vision.relic_expedition import confirm_send
    image=cv2.imread('tests/fixtures/phase8/relic-send-confirm.png')
    proof=confirm_send(image)
    assert proof and 1 <= proof['qualified_selected_checks'] <= 4
    assert proof['box'].center == (360,1013)
    image[215:260,275:450]=0
    assert confirm_send(image) is None


def test_generic_confirm_or_no_selected_mission_is_not_authorized():
    from top_heroes_auto.vision.relic_expedition import confirm_send
    image=cv2.imread('tests/fixtures/phase8/relic-send-confirm.png')
    image[300:830,50:120]=0
    assert confirm_send(image) is None


def test_confirm_modal_observation_exposes_only_mission_action(tmp_path,monkeypatch):
    from top_heroes_auto.app import dynamic_event_port as module
    from top_heroes_auto.vision.models import ScreenState
    port=object.__new__(DynamicEventPort)
    image=cv2.imread('tests/fixtures/phase8/relic-send-confirm.png')
    capture=SimpleNamespace(original=image,rotated_from_portrait=False,index=7,serial='explicit',boot_id='boot',source_image=tmp_path/'fresh.png')
    observed=SimpleNamespace(captured=capture,page='UNKNOWN',box=lambda _:None,
        overlay=SimpleNamespace(state=ScreenState.UNKNOWN),evidence=lambda:{})
    port.transport=SimpleNamespace(observe=lambda:observed)
    port.session=SimpleNamespace(target={'persistent_identity':'disk'},manager=SimpleNamespace(
        namespace='n',store=SimpleNamespace(reward_claims=lambda *a:[])),index=7)
    port.current=None
    port.entered='current-event'
    port.task_context=cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    monkeypatch.setattr(module,'read_words',lambda _:[])
    frame=port.observe()
    assert frame.page=='event:relic-expedition:confirm' and frame.coverage_known
    assert [c.kind for c in frame.controls]==['mission'] and not frame.blocked


def test_quick_send_only_opens_modal_without_reserving_reward(rig,tmp_path,monkeypatch):
    manager,_,store=rig
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep',lambda _:None)
    port=object.__new__(DynamicEventPort)
    port.session=SimpleNamespace(manager=manager,index=7,name='Farm',target={'persistent_identity':'fixture-disk-7'})
    port.folder=tmp_path
    action=Control('relic-expedition-quick-send',BoundingBox(482,1062,208,84),
        ('context','qualified-button','free-mission'),'mission',cost='FREE',available=True)
    original=EventFrame('original',(7,'fixture-disk-7','explicit','boot'),'event:personal-tasks','a',(action,))
    confirmation=replace(action,identity='relic-expedition-confirm-send')
    after=replace(original,capture='after',page='event:relic-expedition:confirm',controls=(confirmation,))
    frames=iter([replace(original,capture='fresh'),after])
    def observe():
        port.current=next(frames)
        return port.current
    port.observe=observe
    calls=[]
    port.transport=SimpleNamespace(last=object(),dispatch=lambda *a,**k:calls.append(a))
    port.current=original
    result=port.send_mission(original,action)
    assert result['result']=='NAVIGATION_SUCCESS' and not result['mission_dispatched']
    assert result['navigation_dispatched'] and len(calls)==1
    assert store.reward_claims(manager.namespace,7)==[]


def test_claim_precedes_quick_send_and_uncertain_confirmation_never_repeats():
    from test_dynamic_events import Port, control, frame

    from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer
    class MissionPort(Port):
        def send_mission(self,f,c):
            self.calls.append((f.page,'mission',c.identity,c.box.center))
            return dict(result='NAVIGATION_SUCCESS' if c.identity=='open' else 'ACTION_DISPATCHED_UNVERIFIED',
                        mission_dispatched=c.identity=='confirm',journal='RESERVED' if c.identity=='confirm' else 'NONE')
    event=control('event','event')
    reward=control('free','reward',cost='FREE',available=True)
    opening=control('open','mission',cost='FREE',available=True)
    confirm=control('confirm','mission',cost='FREE',available=True)
    back=control('back','parent')
    port=MissionPort([frame('home',0,[event]),frame('tasks',1,[opening,reward]),
        frame('tasks',2,[opening]),frame('confirm',3,[confirm]),
        frame('tasks',4,[opening],parent=back),frame('home',5)])
    result=DynamicEventExplorer().run(port)
    assert [c[1] for c in port.calls]==['event','reward','mission','mission','parent']
    assert len(result.rewards)==1
    assert result.result=='BLOCKED'
    assert any(b['reason']=='ACTION_DISPATCHED_UNVERIFIED' for b in result.blocked)


def test_current_refresh_amount_keeps_send_qualified_without_lower_threshold():
    image=cv2.imread('tests/fixtures/phase8/relic-quick-send-current.png')
    proof=detect(image)
    assert proof and proof['box'].center==(586,1104)
    assert proof['forbidden'][0].center[0]<proof['box'].center[0]

"""Wood is the only authorized Technology cost; every input uses a fresh frame."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.flow_registry import COMPLETE
from top_heroes_auto.app.guild_mail_port import GuildMailPort
from top_heroes_auto.automation.guild_mail_claims import Opportunity, process
from top_heroes_auto.vision.guild_mail import GuildMailDetector, portrait
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.screenshot import ScreenshotService


@pytest.fixture(scope='module')
def visual():
    detector = GuildMailDetector(number_reader=lambda *a,**kw:18)
    frames = {}
    for name in ('donation','donation-live','donation-stone'):
        path = Path(__file__).parent/'fixtures/phase7'/f'{name}.png'
        frames[name] = detector.observe(ScreenshotService(lambda _:path.read_bytes()).take(
            Target(17,'offline','explicit','boot')))
    return detector,frames


@pytest.mark.parametrize('name',['donation','donation-live'])
def test_supplied_and_live_brown_log_are_wood(visual,name):
    detector,frames = visual
    frame = replace(frames[name],values={})
    view = detector.availability(frame,'guild-technology')
    resource = frame.values['donation_resource']
    assert view.state == 'AVAILABLE' and resource['resource'] == 'WOOD'
    assert resource['evidence']['WOOD']['score'] >= .97
    assert resource['authorized'] and view.box is not None
    assert view.box.x > view.forbidden[0].x+view.forbidden[0].width


def test_real_gray_stone_is_rejected_despite_green_button(visual):
    detector,frames = visual
    frame = replace(frames['donation-stone'],values={})
    view = detector.availability(frame,'guild-technology')
    assert view.state == 'RESOURCE_NOT_AUTHORIZED' and view.box is None
    assert frame.values['donation_resource']['resource'] == 'STONE'
    assert not frame.values['donation_resource']['authorized']
    assert detector.control(frame,'donation-green','green') is not None


@pytest.mark.parametrize('replacement',['diamond','unknown','duplicate_wood','conflicting_stone'])
def test_current_cost_is_local_unique_and_never_authorized_by_color(visual,replacement):
    detector,frames = visual
    frame = replace(frames['donation-live'],values={})
    green = detector.control(frame,'donation-green','green')
    wood = detector.button_anchor(frame,'donation-wood',green).normalized_box
    pixels = frame.captured.normalized.copy()
    if replacement in {'diamond','unknown'}:
        pixels[wood.y-2:wood.y+wood.height+2,wood.x-2:wood.x+wood.width+2] = (95,175,145)
    if replacement != 'unknown':
        role = {'diamond':'donation-diamond','duplicate_wood':'donation-wood',
                'conflicting_stone':'donation-stone'}[replacement]
        template = detector.templates[role]
        h,w = template.shape[:2]
        x,y = wood.x,wood.y if replacement=='diamond' else wood.y+65
        pixels[y:y+h,x:x+w] = template
    frame = replace(frame,captured=replace(frame.captured,normalized=pixels))
    result = detector.donation_resource(frame,green)
    assert result != 'WOOD'
    assert not frame.values['donation_resource']['authorized']
    assert detector.availability(frame,'guild-technology').state == 'RESOURCE_NOT_AUTHORIZED'
    if replacement == 'diamond':
        assert result == 'DIAMOND'


def test_wood_elsewhere_cannot_authorize_current_stone_cost(visual):
    detector,frames = visual
    frame = replace(frames['donation-stone'],values={})
    pixels = frame.captured.normalized.copy()
    template = detector.templates['donation-wood']
    h,w = template.shape[:2]
    pixels[40:40+h,40:40+w] = template  # Deliberately outside the current button.
    frame = replace(frame,captured=replace(frame.captured,normalized=pixels))
    assert detector.availability(frame,'guild-technology').state == 'RESOURCE_NOT_AUTHORIZED'
    assert frame.values['donation_resource']['resource'] == 'STONE'


def test_disabled_green_is_not_an_authorized_donation(visual):
    detector,frames = visual
    original = frames['donation-live']
    green = detector.control(original,'donation-green','green')
    pixels = portrait(original.captured).copy()
    part = pixels[green.y:green.y+green.height,green.x:green.x+green.width]
    part[:] = cv2.cvtColor(cv2.cvtColor(part,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
    png = cv2.imencode('.png',pixels)[1].tobytes()
    frame = detector.observe(ScreenshotService(lambda _:png).take(Target(17,'offline','explicit','boot')))
    assert not detector.green_enabled(frame,green)
    assert detector.availability(frame,'guild-technology').state != 'AVAILABLE'


class WoodPort:
    def __init__(self,states,*,fail=False):
        self.states = iter(states)
        self.number = 0
        self.inputs = []
        self.fail = fail
        self.qualified = None
        self.base = datetime.now(timezone.utc)

    def observe(self):
        self.number += 1
        captured = SimpleNamespace(index=7,name='Farm-007',serial='emulator-test',boot_id='boot',
            source_image=Path(f'{self.number}.png'),timestamp=(self.base+timedelta(seconds=self.number)).isoformat())
        return SimpleNamespace(captured=captured,page='donation',values={},
                               evidence=lambda:dict(capture=str(captured.source_image),timestamp=captured.timestamp))

    def opportunity(self,reward,initial=None):
        frame = self.observe()
        state,count = next(self.states)
        frame.values['donation_resource'] = dict(resource='WOOD' if state=='AVAILABLE' else 'STONE')
        view = Opportunity(reward,state,'donation-green',BoundingBox(100+self.number,200,80,40),count,reward)
        self.qualified = (frame,view)
        return frame,view

    def geometry(self,frame,view):
        return dict(tap=list(view.box.center))

    def claim(self,frame,view,*,before_input):
        assert self.qualified[0] is frame and self.qualified[1] is view
        assert view.state == 'AVAILABLE'
        before_input()
        self.inputs.append((frame.captured.source_image,view.box.center))
        self.qualified = None
        if self.fail:
            raise TimeoutError('Uncertain input')


def run(rig,port):
    manager,_,store = rig
    task = store.create_task_run(manager.namespace,'guild',7,'Farm-007')
    report = {}
    process(port,store,manager.namespace,task,'guild-technology','disk',report,lambda:None)
    return report


def test_twenty_wood_inputs_reacquire_geometry_and_stop_at_zero(rig):
    states = []
    for n in range(20,0,-1):
        post = 'AVAILABLE' if n>1 else 'NOT_AVAILABLE'
        states.extend([('AVAILABLE',n),(post,n-1),(post,n-1)])
    port = WoodPort(states)
    report = run(rig,port)
    assert report['result'] == 'SUCCESS' and report['start_remaining'] == 20 and report['end_remaining'] == 0
    assert len(port.inputs) == report['claim_count'] == 20
    assert len({capture for capture,point in port.inputs}) == 20
    assert len({point for capture,point in port.inputs}) == 20
    assert all(row['status']=='VERIFIED' for row in rig[2].reward_claims(rig[0].namespace,7))
    again = WoodPort([('NOT_AVAILABLE',0)])
    assert run(rig,again)['result'] == 'NOT_AVAILABLE' and not again.inputs


def test_cost_change_verifies_prior_wood_progress_then_stops_immediately(rig):
    port = WoodPort([('AVAILABLE',20),('RESOURCE_NOT_AUTHORIZED',19),('RESOURCE_NOT_AUTHORIZED',19)])
    report = run(rig,port)
    assert report['result'] == 'RESOURCE_NOT_AUTHORIZED' and report['journal'] == 'VERIFIED'
    assert (report['start_remaining'],report['end_remaining']) == (20,19)
    assert report['claim_count'] == len(port.inputs) == 1
    assert report['resource']['resource'] == 'STONE'


def test_nonwood_initial_cost_creates_no_reservation_or_input(rig):
    port = WoodPort([('RESOURCE_NOT_AUTHORIZED',20)])
    report = run(rig,port)
    assert report['result'] == 'RESOURCE_NOT_AUTHORIZED' and report['result'] in COMPLETE
    assert not port.inputs and not rig[2].reward_claims(rig[0].namespace,7)


def test_wood_uncertainty_stays_locked_on_resume(rig):
    first = WoodPort([('AVAILABLE',20)],fail=True)
    assert run(rig,first)['result'] == 'ACTION_DISPATCHED_UNVERIFIED'
    second = WoodPort([('AVAILABLE',20)])
    assert run(rig,second)['result'] == 'ALREADY_ATTEMPTED' and not second.inputs
    assert len(rig[2].reward_claims(rig[0].namespace,7)) == 1


def test_production_dispatch_requires_current_wood_evidence():
    port = object.__new__(GuildMailPort)
    frame = SimpleNamespace(values={'donation_resource':{'resource':'STONE'}})
    view = Opportunity('guild-technology','AVAILABLE',remaining=20)
    port.qualified = (frame,view)
    port.last = frame
    with pytest.raises(Exception,match='positively authorized WOOD'):
        port.claim(frame,view,before_input=lambda:pytest.fail('No nonwood input'))


@pytest.mark.parametrize('stale',['frame','qualification'])
def test_production_port_cannot_reuse_previous_donation_geometry(stale):
    port = object.__new__(GuildMailPort)
    previous = SimpleNamespace(values={'donation_resource':{'resource':'WOOD'}})
    current = SimpleNamespace(values={'donation_resource':{'resource':'WOOD'}})
    view = Opportunity('guild-technology','AVAILABLE',remaining=20)
    port.qualified = (previous if stale=='frame' else current,view)
    port.last = current
    with pytest.raises(Exception,match='Stale|current qualified'):
        port.claim(previous,view,before_input=lambda:pytest.fail('Stale geometry must not dispatch'))

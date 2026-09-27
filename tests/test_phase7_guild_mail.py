"""Offline Guild/Mail qualification; no emulator, transport or real journals."""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.flow_registry import production_registry
from top_heroes_auto.automation.guild_mail_claims import Opportunity, process, qualified_progress, relic_cycle
from top_heroes_auto.vision.guild_mail import GuildMailDetector
from top_heroes_auto.vision.local_ocr import counter
from top_heroes_auto.vision.models import BoundingBox, ScreenState
from top_heroes_auto.vision.screenshot import ScreenshotService

FIXTURES = Path(__file__).parent/'fixtures/phase7'
BASE_TIME = datetime.now(timezone.utc)


def capture(name):
    return ScreenshotService(lambda _: (FIXTURES/f'{name}.png').read_bytes()).take(
        Target(7,'Farm-007','emulator-test','boot'))


@pytest.fixture(scope='module')
def detector():
    return GuildMailDetector(number_reader=lambda image,**kw: 18)


@pytest.fixture(scope='module')
def frames(detector):
    return {name:detector.observe(capture(name)) for name in (
        'home','guild','territory','relic','loot','member','technology','donation','mail','mail-empty')}


@pytest.mark.parametrize('name,page', [
    ('home','home'),('guild','guild'),('territory','territory'),('relic','relic'),
    ('loot','gifts-loot'),('member','gifts-member'),('technology','technology'),
    ('donation','donation'),('mail','mail'),('mail-empty','mail'),
])
def test_qualified_reference_pages(frames,name,page):
    assert frames[name].page == page


def test_mail_modal_is_not_generic_home_popup(frames):
    assert frames['mail'].overlay.state == ScreenState.UNKNOWN
    assert frames['mail-empty'].overlay.state == ScreenState.UNKNOWN


def test_wood_donation_geometry_excludes_paid_button(detector,frames):
    view = detector.availability(frames['donation'],'guild-technology')
    assert view.state == 'AVAILABLE' and view.remaining == 18
    assert view.box.x > view.forbidden[0].x+view.forbidden[0].width
    geometry = detector.action_geometry(frames['donation'],view.role,view.box,view.forbidden)
    x,y = geometry['tap']
    assert view.box.x < x < view.box.x+view.box.width and view.box.y < y < view.box.y+view.box.height


def test_donation_requires_wood_and_diamond_exclusion(detector,frames):
    original = frames['donation']
    anchors = dict(original.anchors)
    anchors['donation-wood'] = replace(anchors['donation-wood'],matched=False,device_box=None)
    assert detector.availability(replace(original,anchors=anchors),'guild-technology').state == 'UNKNOWN'


def test_technology_marker_is_associated_with_one_tree_node(frames):
    node = frames['technology'].box('technology-node')
    marker = frames['technology'].box('technology-like')
    assert node and marker and node.y < 800 and node.width > marker.width*2


def test_forbidden_geometry_rejected(detector,frames):
    box = BoundingBox(10,10,50,50)
    with pytest.raises(ValueError):
        detector.action_geometry(frames['guild'],'forged',box,(BoundingBox(30,30,40,40),))


def test_missing_page_anchor_fails_closed(detector):
    frame = capture('guild')
    image = frame.normalized.copy()
    label = detector.anchor(frame,'guild-declaration').normalized_box
    image[label.y:label.y+label.height,label.x:label.x+label.width] = 0
    assert detector.observe(replace(frame,normalized=image)).page == 'UNKNOWN'


def test_shifted_anchor_current_bbox_and_duplicate_rejected(detector):
    frame = capture('guild')
    template = detector.templates['guild-gifts']
    h,w = template.shape[:2]
    image = np.zeros_like(frame.normalized)
    image[80:80+h,180:180+w] = template
    result = detector.anchor(replace(frame,normalized=image),'guild-gifts')
    assert result.matched and (result.normalized_box.x,result.normalized_box.y) == (180,80)
    image[400:400+h,700:700+w] = template
    assert not detector.anchor(replace(frame,normalized=image),'guild-gifts').matched


@pytest.mark.parametrize('texts,expected', [
    (['18','18'],18),(['18','19'],None),(['18120','18120'],None),
    (['1 8','18'],None),(['O','0'],None),(['21','21'],None),
])
def test_counter_consensus_never_guesses(texts,expected):
    values = iter(texts)
    result = counter(np.full((30,60,3),200,np.uint8),maximum=20,
                     reader=lambda image:[{'text':next(values)}])
    assert result == expected


def test_relic_vietnam_reset():
    before = datetime(2026,9,27,1,59,tzinfo=timezone.utc)
    after = before+timedelta(minutes=1)
    assert '2026-09-26T02:00' in relic_cycle(before)
    assert '2026-09-27T02:00' in relic_cycle(after)
    with pytest.raises(ValueError):
        relic_cycle(before.replace(tzinfo=None))


def fake_frame(number,page='gifts-loot',**overrides):
    values = dict(index=7,name='Farm-007',serial='emulator-test',boot_id='boot',
                  source_image=Path(f'{number}.png'),
                  timestamp=(BASE_TIME+timedelta(seconds=number)).isoformat())
    values.update(overrides)
    captured = SimpleNamespace(**values)
    return SimpleNamespace(captured=captured,page=page,evidence=lambda:dict(
        index=captured.index,source=str(captured.source_image),page=page))


class Port:
    def __init__(self,states,reward='guild-gifts-loot',*,fail=False):
        self.states = iter(states)
        self.reward = reward
        self.number = 0
        self.taps = 0
        self.fail = fail

    def opportunity(self,reward,initial=None):
        self.number += 1
        state,count = next(self.states)
        return fake_frame(self.number,'donation' if reward == 'guild-technology' else 'gifts-loot'),Opportunity(
            reward,state,'button',BoundingBox(100,100,50,30),count,reward)

    def geometry(self,*args):
        return {'tap':[125,115]}

    def claim(self,frame,view,before_input):
        before_input()
        self.taps += 1
        if self.fail:
            raise TimeoutError('transport outcome uncertain')

    def observe(self):
        return fake_frame(80)


def execute(rig,port,reward='guild-gifts-loot'):
    manager,_,store = rig
    task = store.create_task_run(manager.namespace,'guild',7,'Farm-007')
    result = {}
    process(port,store,manager.namespace,task,reward,'disk',result,lambda:None)
    return result


def test_batch_progress_two_claims_then_exhausted(rig):
    port = Port([('AVAILABLE',3),('AVAILABLE',2),('AVAILABLE',2),
                 ('AVAILABLE',2),('NOT_AVAILABLE',0),('NOT_AVAILABLE',0)])
    result = execute(rig,port)
    assert port.taps == result['claim_count'] == 2 and result['result'] == 'SUCCESS'
    rows = rig[2].reward_claims(rig[0].namespace,7)
    assert len(rows) == 2 and all(r['status'] == 'VERIFIED' for r in rows)
    assert rows[1]['cycle_key'] == f"progress:after-verified-{rows[0]['id']}"


@pytest.mark.parametrize('post',[('UNKNOWN',None),('AVAILABLE',3),('AVAILABLE',4)])
def test_popup_no_progress_or_increase_cannot_verify_or_retry(rig,post):
    first = Port([('AVAILABLE',3),post,post])
    result = execute(rig,first)
    assert result['result'] == 'ACTION_DISPATCHED_UNVERIFIED'
    second = Port([('AVAILABLE',3)])
    locked = execute(rig,second)
    assert locked['result'] == 'ALREADY_ATTEMPTED' and second.taps == 0
    assert rig[2].reward_claims(rig[0].namespace,7)[0]['dispatch_state'] == 'POSSIBLE'


def test_transport_uncertainty_is_locked(rig):
    port = Port([('AVAILABLE',3)],fail=True)
    result = execute(rig,port)
    assert result['result'] == 'ACTION_DISPATCHED_UNVERIFIED' and port.taps == 1
    assert execute(rig,Port([('AVAILABLE',3)]))['result'] == 'ALREADY_ATTEMPTED'


def test_unknown_no_journal_or_input(rig):
    port = Port([('UNKNOWN',None)])
    assert execute(rig,port)['result'] == 'UNKNOWN'
    assert not port.taps and not rig[2].reward_claims(rig[0].namespace,7)


def test_donation_exact_decrement_only(rig):
    port = Port([('AVAILABLE',2),('AVAILABLE',1),('AVAILABLE',1),
                 ('AVAILABLE',1),('NOT_AVAILABLE',0),('NOT_AVAILABLE',0)])
    result = execute(rig,port,'guild-technology')
    assert result['result'] == 'SUCCESS' and port.taps == 2


def test_donation_skipped_counter_fails_closed(rig):
    result = execute(rig,Port([('AVAILABLE',3),('AVAILABLE',1),('AVAILABLE',1)]),'guild-technology')
    assert result['result'] == 'ACTION_DISPATCHED_UNVERIFIED'


@pytest.mark.parametrize('changes',[
    {'source_image':Path('1.png')},{'boot_id':'other'},{'serial':'other'},
    {'name':'other'},{'index':0},{'timestamp':'2026-09-27T05:02:00+00:00'},
])
def test_postcondition_requires_fresh_same_target_evidence(changes):
    before = Opportunity('guild-gifts-loot','AVAILABLE',remaining=3,context='loot')
    after = replace(before,state='NOT_AVAILABLE',remaining=0)
    assert not qualified_progress(fake_frame(1),before,fake_frame(2,**changes),after)


def test_phase7_registered_with_existing_instance_pipeline():
    plan = production_registry().snapshot()
    assert [f.id for f in plan] == ['vip','ranking','shop','guild','mail']
    assert next(f for f in plan if f.id == 'mail').rewards == tuple(
        f'mail-{name}' for name in ('war','guild','system','reports','collection'))


def test_journal_survives_later_reporting_failure(rig):
    result = execute(rig,Port([('AVAILABLE',1),('NOT_AVAILABLE',0),('NOT_AVAILABLE',0)]))
    before = json.dumps(rig[2].reward_claims(rig[0].namespace,7),sort_keys=True)
    result['recovery'] = 'FAILED'
    result['cleanup'] = 'FAILED'
    assert json.dumps(rig[2].reward_claims(rig[0].namespace,7),sort_keys=True) == before



def test_numbered_mail_badges_cannot_be_treated_as_absent(frames):
    detector = GuildMailDetector(number_reader=lambda *a,**k:None)
    tabs = detector.mail_tabs(frames['mail'])
    assert tabs['guild']['count'] == 3 and tabs['system']['count'] == 6
    assert tabs['reports']['count'] is None  # Unread number is UNKNOWN, never zero.
    assert tabs['war']['count'] == tabs['collection']['count'] == 0


def test_single_digit_fallback_does_not_read_six_inside_sixty(frames):
    detector = GuildMailDetector(number_reader=lambda *a,**k:None)
    assert detector.mail_tabs(frames['mail'])['reports']['count'] is None


def test_gray_quick_control_is_positive_unavailable(detector):
    original = cv2.imdecode(np.frombuffer((FIXTURES/'loot.png').read_bytes(),np.uint8),1)
    # Synthetic disabled control; keep page anchors intact and remove its badge.
    part = original[931:995,222:399]
    gray = cv2.cvtColor(part,cv2.COLOR_BGR2GRAY)
    original[931:995,222:399] = cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    original[923:951,378:411] = original[935,420]
    original[420:850,30:540] = original[840,20]  # Exhausted list, no remaining free rows.
    png = cv2.imencode('.png',original)[1].tobytes()
    frame = ScreenshotService(lambda _:png).take(Target(7,'Farm-007','emulator-test','boot'))
    view = detector.availability(detector.observe(frame),'guild-gifts-loot')
    assert view.state == 'NOT_AVAILABLE' and view.remaining == 0


def test_forbidden_navigation_never_dispatches(frames):
    from top_heroes_auto.app.guild_mail_port import GuildMailPort

    port = object.__new__(GuildMailPort)
    with pytest.raises(Exception,match='No qualified navigation'):
        port.navigate(frames['guild'],'guild-trial-forbidden','trial')


def test_stale_claim_never_dispatches():
    from top_heroes_auto.app.guild_mail_port import GuildMailPort

    port = object.__new__(GuildMailPort)
    port.qualified = None
    with pytest.raises(Exception,match='current qualified'):
        port.claim(None,None,before_input=lambda:pytest.fail('Unexpected input'))


def test_undispatched_reservation_is_released_without_unlocking_possible(rig):
    class NotSent(Port):
        def claim(self,*args,**kwargs):
            raise ValueError('Guard rejected before transport')
    port = NotSent([('AVAILABLE',3)])
    result = execute(rig,port)
    assert result['result'] == 'SAFETY_BLOCKED' and result['journal'] == 'NONE'
    assert not rig[2].reward_claims(rig[0].namespace,7)


def test_verified_relic_not_replayed_same_period(rig):
    first = Port([('AVAILABLE',1),('NOT_AVAILABLE',0),('NOT_AVAILABLE',0)])
    assert execute(rig,first,'guild-relic')['journal'] == 'VERIFIED'
    second = Port([('AVAILABLE',1)])
    assert execute(rig,second,'guild-relic')['result'] == 'ALREADY_VERIFIED'
    assert second.taps == 0


def test_donation_bounded_even_if_charges_refill(rig):
    states = [('AVAILABLE',20),('AVAILABLE',19),('AVAILABLE',19)]*20
    port = Port(states)
    result = execute(rig,port,'guild-technology')
    assert result['result'] == 'BOUNDED_LIMIT' and port.taps == 20


def test_foreign_prior_identity_prevents_new_batch(rig):
    execute(rig,Port([('AVAILABLE',1),('NOT_AVAILABLE',0),('NOT_AVAILABLE',0)]))
    manager,_,store = rig
    task = store.create_task_run(manager.namespace,'guild',7,'Farm-007')
    port = Port([('AVAILABLE',3)])
    result = {}
    process(port,store,manager.namespace,task,'guild-gifts-loot','other disk',result,lambda:None)
    assert result['result'] == 'IDENTITY_CONTINUITY_UNPROVEN' and port.taps == 0



def test_dimmed_mail_under_another_modal_is_not_actionable(detector):
    frame = capture('mail')
    image = (frame.normalized.astype(float)*.55).astype(np.uint8)
    assert detector.observe(replace(frame,normalized=image)).page == 'UNKNOWN'


def test_portable_includes_local_counter_reader():
    import ast

    root = Path(__file__).resolve().parents[1]
    spec = ast.parse((root/'TopHeroesAutoManager.spec').read_text(encoding='utf-8'))
    analysis = next(n.value for n in spec.body if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id == 'a' for t in n.targets))
    data = next(k.value for k in analysis.keywords if k.arg == 'datas')
    bindings = eval(compile(ast.Expression(data),'<portable-datas>','eval'),{'root':root})
    assert (str(root/'assets/tools'),'assets/tools') in bindings
    assert (root/'assets/tools/read-image-text.ps1').is_file()


def test_delayed_ui_update_waits_without_second_dispatch(rig):
    port = Port([('AVAILABLE',1),('AVAILABLE',1),('NOT_AVAILABLE',0),('NOT_AVAILABLE',0)])
    result = execute(rig,port)
    assert result['result'] == 'SUCCESS' and result['journal'] == 'VERIFIED'
    assert port.taps == 1 and len(result['actions'][0]['post_observations']) == 2

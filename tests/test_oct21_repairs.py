"""Current-run regressions; no transport, gameplay or live journal mutation."""
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.guild_mail import GuildMailDetector
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.screenshot import ScreenshotService


@pytest.fixture(scope='module')
def empty_gifts():
    path = Path(__file__).parent/'fixtures/phase7/member-empty-current.png'
    captured = ScreenshotService(lambda _: path.read_bytes()).take(Target(8,'fixture','serial','boot'))
    detector = GuildMailDetector(number_reader=lambda *a, **k: None)
    return detector, detector.observe(captured)


def test_positive_empty_member_page_is_unavailable_despite_green_button(empty_gifts):
    detector, frame = empty_gifts
    assert frame.page == 'gifts-member'
    assert frame.anchors['gifts-empty-label'].matched
    assert detector.control(frame,'gifts-quick','green')
    view = detector.availability(frame,'guild-gifts-member')
    assert view.state == 'NOT_AVAILABLE' and view.remaining == 0


def test_missing_empty_text_cannot_infer_unavailable_from_missing_badge(empty_gifts):
    detector, frame = empty_gifts
    anchors = dict(frame.anchors)
    anchors['gifts-empty-label'] = replace(anchors['gifts-empty-label'],matched=False,score=0)
    assert detector.availability(replace(frame,anchors=anchors),'guild-gifts-member').state == 'UNKNOWN'


def test_empty_label_conflicting_with_positive_batch_fails_closed(empty_gifts,monkeypatch):
    detector, frame = empty_gifts
    monkeypatch.setattr(detector,'local_badge',lambda *a,**k: 3)
    assert detector.availability(frame,'guild-gifts-member').state == 'UNKNOWN'


def test_visit_does_not_load_historical_possible_claims(monkeypatch,tmp_path):
    # Any attempt to load old claims at initialization is forbidden here.
    class Store:
        def reward_claims(self,*args):
            raise AssertionError('Historical POSSIBLE is not a current-visit pending action')
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.FixedRewardPort',lambda *a:SimpleNamespace())
    session = SimpleNamespace(manager=SimpleNamespace(store=Store()),snapshot=None,index=8,name='fixture',
                              check=lambda:None,cancelled=lambda:False)
    assert DynamicEventPort(session,tmp_path).pending_claim_ids == set()


def test_stop_during_guild_reward_skips_siblings_and_home(rig,tmp_path,monkeypatch):
    from top_heroes_auto.app import guild_mail_flows
    from top_heroes_auto.automation.recovery import RecoveryStatus

    manager, _, store = rig
    calls=[]
    stopped=False
    session=SimpleNamespace(manager=manager,index=7,name='Farm-007',target={'persistent_identity':'disk'},
        cancelled=lambda:stopped,check=lambda:None,
        recover=lambda:(SimpleNamespace(status=RecoveryStatus.SUCCESS,adb_target='serial'),tmp_path,False))
    class Port:
        def open_reward(self,reward):
            nonlocal stopped
            calls.append(reward)
            stopped=True
            raise SafetyError('Run cancelled.')
        def home(self):
            calls.append('home')
        def observe_settled(self):
            calls.append('audit')
            raise AssertionError('No captures after Stop')
    with pytest.raises(SafetyError,match='cancelled'):
        guild_mail_flows.run(session,tmp_path/'mail',('mail-guild','mail-system'),port_factory=lambda *a:Port())
    assert calls == ['mail-guild']
    assert not store.reward_claims(manager.namespace,7)


def test_entry_retains_binding_but_consumes_action_frame(monkeypatch,tmp_path):
    from top_heroes_auto.automation.phase6_navigation import ManagerEntryPort

    target = Target(8,'fixture','serial','boot')
    calls=[]
    manager = SimpleNamespace(
        capture_verified=lambda *a,**k: (calls.append(k) or (target,b'png')),
        execute=lambda *a,**k:None)
    monkeypatch.setattr('top_heroes_auto.automation.phase6_navigation.ScreenshotService',
                        lambda *a:SimpleNamespace(take=lambda *a:SimpleNamespace()))
    port=ManagerEntryPort(manager,None,8,'fixture',tmp_path)
    first=port.observe('first')
    port.tap(first,(5,5))
    with pytest.raises(SafetyError,match='stale'):
        port.tap(first,(5,5))
    port.observe('fresh')
    with pytest.raises(SafetyError,match='stale'):
        port.tap(first,(5,5))
    assert calls == [{},{'observed_target':target}]


def test_guild_stop_after_uncertain_dispatch_preserves_lock(rig):
    from test_phase7_guild_mail import Port

    from top_heroes_auto.automation.guild_mail_claims import process

    manager,_,store=rig
    class StoppedPort(Port):
        def check_cancelled(self):
            if self.taps:
                raise SafetyError('Run cancelled.')
    port=StoppedPort([('AVAILABLE',3)],fail=True)
    task=store.create_task_run(manager.namespace,'guild',7,'Farm-007')
    with pytest.raises(SafetyError,match='cancelled'):
        process(port,store,manager.namespace,task,'guild-gifts-loot','disk',{},lambda:None)
    rows=store.reward_claims(manager.namespace,7)
    assert port.taps==1 and len(rows)==1 and rows[0]['dispatch_state']=='POSSIBLE'


@pytest.mark.skipif(sys.platform!='win32',reason='Windows local OCR qualification')
def test_current_two_digit_system_badge_uses_complete_numeral():
    path=Path(__file__).parent/'fixtures/phase7/mail-system-badge-20.png'
    frame=SimpleNamespace(captured=ScreenshotService(lambda _:path.read_bytes()).take(
        Target(8,'fixture','serial','boot')),anchors={})
    assert GuildMailDetector().local_badge(frame,BoundingBox(10,19,121,82),numbered=True)==20


def test_moving_technology_tree_uses_last_stable_current_box():
    from top_heroes_auto.app.guild_mail_port import GuildMailPort

    def frame(y):
        return SimpleNamespace(page='technology',box=lambda _:BoundingBox(20,y,100,100))
    port=object.__new__(GuildMailPort)
    first,second,third=frame(600),frame(545),frame(545)
    frames=iter((second,third))
    port.check_cancelled=lambda:None
    port.observe_settled=lambda:next(frames)
    assert port.stable_technology_node(first) is third


def test_unstable_technology_tree_never_authorizes_input():
    from top_heroes_auto.app.guild_mail_port import GuildMailPort

    port=object.__new__(GuildMailPort)
    port.check_cancelled=lambda:None
    positions=iter((550,500,450))
    port.observe_settled=lambda:SimpleNamespace(page='technology',box=lambda _:BoundingBox(20,next(positions),100,100))
    with pytest.raises(SafetyError,match='stabilize'):
        port.stable_technology_node(SimpleNamespace(box=lambda _:BoundingBox(20,600,100,100)))


def test_owned_monthly_current_raster_keeps_independent_free_daily_target():
    from top_heroes_auto.vision.fixed_rewards import MONTHLY_DAILY, FixedRewardDetector, claim_geometry

    path=Path(__file__).parent/'fixtures/phase6_fixed/monthly-owned-current.png'
    frame=FixedRewardDetector().observe(ScreenshotService(lambda _:path.read_bytes()).take(
        Target(4,'fixture','serial','boot')))
    detector=FixedRewardDetector()
    state,core,_=detector.availability(frame,MONTHLY_DAILY)
    assert state=='AVAILABLE' and frame.anchors['monthly-owned-label'].score>=.98
    geometry=claim_geometry(frame,MONTHLY_DAILY,core)
    assert geometry['inside_allowed'] and geometry['outside_forbidden']
    anchors=dict(frame.anchors)
    anchors['monthly-owned-label']=replace(anchors['monthly-owned-label'],matched=False,score=0)
    assert detector.availability(replace(frame,anchors=anchors),MONTHLY_DAILY)[0]=='UNKNOWN'


@pytest.fixture(scope='module')
def zero_donation():
    from datetime import datetime, timedelta, timezone

    detector=GuildMailDetector(number_reader=lambda *a,**k:None)
    frames=[]
    start=datetime.now(timezone.utc)
    for n,name in enumerate(('before','after','confirmation')):
        path=Path(__file__).parent/f'fixtures/phase7/donation-quick-zero-{name}.png'
        captured=ScreenshotService(lambda _,p=path:p.read_bytes()).take(Target(4,'fixture','serial','boot'))
        captured=replace(captured,source_image=path,timestamp=(start+timedelta(seconds=n)).isoformat())
        frames.append(detector.observe(captured))
    return detector,frames


def test_two_original_zero_frames_prove_quick_consumption_without_ocr_guess(zero_donation):
    from top_heroes_auto.automation.guild_mail_claims import qualified_progress

    detector,frames=zero_donation
    detector.number_reader=lambda *a,**k:19
    before=detector.availability(frames[0],'guild-technology')
    detector.number_reader=lambda *a,**k:None
    assert before.state=='AVAILABLE' and before.role=='donation-quick'
    for frame in frames[1:]:
        after=detector.availability(frame,'guild-technology')
        assert after.state=='NOT_AVAILABLE' and after.remaining==0
        assert frame.anchors['donation-zero-fraction'].score>=.98
        assert qualified_progress(frames[0],before,frame,after)


def test_zero_substring_cannot_cover_larger_counter_gap(zero_donation):
    detector,frames=zero_donation
    frame=frames[1]
    anchors=dict(frame.anchors)
    label=anchors['donation-counter-label']
    anchors['donation-counter-label']=replace(label,device_box=replace(label.device_box,x=label.device_box.x-14))
    assert detector.availability(replace(frame,anchors=anchors),'guild-technology').state=='UNKNOWN'
    assert detector.availability(frames[0],'guild-technology').state=='UNKNOWN'

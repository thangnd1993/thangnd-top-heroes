from dataclasses import replace
from pathlib import Path

import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.free_reward_tasks import _load_profile_details
from top_heroes_auto.app.vip_gift import gift_profile, gift_state
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.overlays import OverlayBudget, dismiss_overlay_bottom_left
from top_heroes_auto.automation.phase6_visual import FrameRewardAdapter, ManagerRewardPort
from top_heroes_auto.automation.recovery import HomeRecoveryEngine, RecoveryObservation, RecoveryStatus
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService

FIXTURES = Path(__file__).parent / 'fixtures/phase6_vip'
TARGET = Target(2, '5-Emmmmm', 'emulator-5558', 'fixture-boot')


def test_packaged_acceptance_requires_exact_explicit_index2_command(monkeypatch):
    from top_heroes_auto.app import diagnostic, main, vip_acceptance

    calls = []
    monkeypatch.setattr(diagnostic, '_manager', lambda _: 'mock-manager')
    monkeypatch.setattr(vip_acceptance, 'run', lambda manager, data: calls.append(manager))
    with pytest.raises(ValueError):
        main.main(['vip-acceptance'])
    with pytest.raises(ValueError):
        main.main(['vip-acceptance', '--confirm-index2', '--index', '0'])
    assert calls == []
    assert main.main(['vip-acceptance', '--confirm-index2']) == 0
    assert calls == ['mock-manager']


def screen(name='receipt-reference.png'):
    return ScreenshotService(lambda _: (FIXTURES / name).read_bytes()).take(TARGET)


def receipt():
    captured = screen()
    return captured, RecoveryScreenDetector().detect(captured)


@pytest.mark.parametrize('size,point', [((720,1280),(58,1203)), ((1080,1920),(86,1805)), ((1280,720),(102,677))])
def test_normalized_bottom_left_uses_device_orientation(size, point):
    captured, detection = receipt()
    assert dismiss_overlay_bottom_left(replace(captured, device_size=size), detection) == point


@pytest.mark.parametrize('state', [ScreenState.UNKNOWN, ScreenState.GAME_HOME, ScreenState.FREE_REWARD_PAGE,
                                  ScreenState.POPUP_GENERIC, ScreenState.PROMO_LOADING])
def test_unknown_paid_confirmation_normal_pages_never_generic_dismiss(state):
    captured, detection = receipt()
    with pytest.raises(SafetyError):
        dismiss_overlay_bottom_left(captured, replace(detection, state=state))


def test_receipt_requires_both_unique_anchors_and_rejects_vip_page():
    captured, detection = receipt()
    assert detection.state == ScreenState.REWARD_RECEIPT
    assert len(detection.evidence) == 2
    assert RecoveryScreenDetector().detect(screen('index2-vip-claimable.png')).state != ScreenState.REWARD_RECEIPT
    damaged = captured.normalized.copy()
    box = detection.evidence[0].normalized_box
    damaged[box.y:box.y+box.height, box.x:box.x+box.width] = 0
    assert RecoveryScreenDetector().detect(replace(captured, normalized=damaged)).state != ScreenState.REWARD_RECEIPT


class RecoveryPort:
    def __init__(self, states):
        self.states = iter(states)
        self.captured, self.known = receipt()
        self.actions = []
        self.observations = 0

    def observe(self, step):
        state = next(self.states)
        self.observations += 1
        self.current = replace(self.known, state=state, timestamp=str(step))
        return RecoveryObservation(self.current, Path(f'{step}.png'), TARGET.serial, TARGET.boot_id)

    def dismiss_overlay(self, observation):
        assert observation.detection is self.current
        point = dismiss_overlay_bottom_left(self.captured, self.current)
        self.actions.append((self.observations, point))
        return point


def test_multiple_known_promos_fresh_capture_after_each_then_home():
    port = RecoveryPort([ScreenState.PROMO_AD]*2 + [ScreenState.EVENT_PROMO]*2 + [ScreenState.GAME_HOME])
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert port.actions == [(2,(58,1203)), (4,(58,1203))]
    assert port.observations == 5


def test_same_popup_bounded_retry_and_unknown_after_dismiss_stops():
    port = RecoveryPort([ScreenState.EVENT_PROMO]*4)
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.PROMO_BLOCKING
    assert len(port.actions) == 2 and port.observations == 4
    port = RecoveryPort([ScreenState.EVENT_PROMO]*2 + [ScreenState.UNKNOWN])
    result = HomeRecoveryEngine(sleep=lambda _: None).ensure_game_home(port)
    assert result.status == RecoveryStatus.UNKNOWN_SCREEN
    assert len(port.actions) == 1 and port.observations == 3


def test_total_overlay_count_is_bounded_even_for_distinct_anchors():
    _, detection = receipt()
    budget = OverlayBudget()
    for i in range(4):
        budget.reserve(replace(detection, evidence=tuple(replace(e, anchor_id=f'{i}-{e.anchor_id}') for e in detection.evidence)))
    with pytest.raises(SafetyError):
        budget.reserve(detection)


def test_vip_receipt_dismiss_gets_fresh_underlying_frame_without_claim(rig, tmp_path, monkeypatch):
    manager, _, _ = rig
    frames = iter(['receipt-reference.png', 'index2-vip-claimable.png'])
    monkeypatch.setattr(manager, 'capture_verified', lambda *args: (TARGET,(FIXTURES / next(frames)).read_bytes()))
    taps = []
    monkeypatch.setattr(manager, 'execute', lambda index, action, **kwargs: taps.append((index,action,kwargs)))
    profile, _ = _load_profile_details('vip-reward')
    port = ManagerRewardPort(manager, RunSnapshot(manager.namespace, ((2,TARGET.name),),True), 2,TARGET.name,profile,tmp_path)
    before = port.observe()
    after = port.dismiss_receipts(before, sleep=lambda _: None)
    assert after.capture_id != before.capture_id
    assert len(taps) == 1 and taps[0][2]['values'] == (58,1203)
    assert taps[0][2]['observed_target'] == TARGET
    assert port.overlay_events[0]['after'] == after.capture_id
    assert after.rewards  # Still claimable: receipt did not manufacture success.


def test_upper_gift_current_icon_and_badge_required():
    profile, _ = _load_profile_details('vip-reward')
    adapter = FrameRewardAdapter(gift_profile(profile))
    captured = screen('index2-vip-claimable.png')
    before = adapter.observe(captured)
    assert gift_state(before.screen) == 'FREE_CLAIMABLE'
    badge = before.evidence['available'].normalized_box
    changed = captured.normalized.copy()
    changed[badge.y:badge.y+badge.height,badge.x:badge.x+badge.width] = (20,40,70)
    after = adapter.observe(replace(captured, normalized=changed))
    assert gift_state(after.screen) == 'NOT_AVAILABLE'
    assert gift_state(adapter.observe(screen()).screen) == 'UNKNOWN'


def test_vip_receipt_then_claimed_state_is_independently_verified(rig, tmp_path, monkeypatch):
    import cv2

    from top_heroes_auto.automation.free_rewards import ClaimOutcome
    manager, _, _ = rig
    profile, _ = _load_profile_details('vip-reward')
    adapter = FrameRewardAdapter(profile)
    before = adapter.observe(screen('index2-vip-claimable.png'))
    a, b = before.evidence['available'].normalized_box, before.evidence['claim'].normalized_box
    changed = before.captured.normalized.copy()
    changed[min(a.y,b.y):max(a.y+a.height,b.y+b.height),min(a.x,b.x):max(a.x+a.width,b.x+b.width)] = (20,35,55)
    template = cv2.imread(str(profile.anchor_map['post'].template))
    changed[a.y:a.y+template.shape[0],a.x:a.x+template.shape[1]] = template
    portrait = cv2.rotate(changed,cv2.ROTATE_90_COUNTERCLOCKWISE)
    payload = cv2.imencode('.png',portrait)[1].tobytes()
    frames = iter([(FIXTURES/'receipt-reference.png').read_bytes(),payload])
    monkeypatch.setattr(manager,'capture_verified',lambda *args:(TARGET,next(frames)))
    taps=[]
    monkeypatch.setattr(manager,'execute',lambda *args,**kwargs:taps.append(kwargs['values']))
    port = ManagerRewardPort(manager,RunSnapshot(manager.namespace,((2,TARGET.name),),True),2,TARGET.name,profile,tmp_path)
    popup=port.observe()
    after=port.dismiss_receipts(popup,sleep=lambda _:None)
    assert taps == [(58,1203)]
    assert port.classify_claim(before.screen,after,before.screen.rewards[0]) == ClaimOutcome.CLAIMED


def test_receipt_transport_error_cannot_reuse_frame(rig,tmp_path,monkeypatch):
    manager,_,_=rig
    profile,_=_load_profile_details('vip-reward')
    monkeypatch.setattr(manager,'capture_verified',lambda *args:(TARGET,(FIXTURES/'receipt-reference.png').read_bytes()))
    calls=[]
    def uncertain(*args,**kwargs):
        calls.append(kwargs['values'])
        raise OSError('uncertain input')
    monkeypatch.setattr(manager,'execute',uncertain)
    port=ManagerRewardPort(manager,RunSnapshot(manager.namespace,((2,TARGET.name),),True),2,TARGET.name,profile,tmp_path)
    popup=port.observe()
    with pytest.raises(OSError):
        port.dismiss_receipts(popup,sleep=lambda _:None)
    with pytest.raises(SafetyError,match='reuse'):
        port.dismiss_receipts(popup,sleep=lambda _:None)
    assert len(calls)==1


def test_upper_gift_journal_is_one_shot_and_independent_of_daily(rig,tmp_path,monkeypatch):
    from types import SimpleNamespace

    from top_heroes_auto.app import vip_gift
    from top_heroes_auto.app.vip_fleet import PROTECTED
    manager,process,store=rig
    process.listing='\n'.join(f'{i},{name},0,0,0,-1,-1' for i,name in {**PROTECTED,2:TARGET.name}.items())
    manager.refresh()
    manager.select(2,True)
    profile,_=_load_profile_details('vip-reward')
    adapter=FrameRewardAdapter(gift_profile(profile))
    before=adapter.observe(screen('index2-vip-claimable.png'))
    badge=before.evidence['available'].normalized_box
    changed=before.captured.normalized.copy()
    changed[badge.y:badge.y+badge.height,badge.x:badge.x+badge.width]=(20,40,70)
    after=adapter.observe(replace(before.captured,normalized=changed,timestamp='after'))
    frames=iter([before.screen,after.screen])
    calls=[]
    def claim(*args,before_input):
        before_input()
        calls.append('claim')
    port=SimpleNamespace(set_entry_geometry=lambda _:None,observe=lambda:next(frames),
        validate_claim=lambda *args:None,geometry_report={},claim=claim,
        dismiss_receipts=lambda frame:frame,overlay_events=[{'receipt':'qualified'}])
    monkeypatch.setattr(vip_gift,'reward_port_factory',lambda *args:port)
    task=store.create_task_run(manager.namespace,'vip-reward',2,TARGET.name)
    snap=RunSnapshot(manager.namespace,((2,TARGET.name),),True)
    row={}
    vip_gift.run_upper_gift(manager,snap,2,TARGET.name,profile,tmp_path,None,task,row)
    assert row['journal_state']=='VERIFIED'
    retry={}
    vip_gift.run_upper_gift(manager,snap,2,TARGET.name,profile,tmp_path,None,task,retry)
    assert retry['result']=='ALREADY_VERIFIED' and calls==['claim']
    assert [r['reward_id'] for r in store.reward_claims(manager.namespace,2)]==['vip-upper-gift']


def test_late_promo_at_vip_entry_boundary_dismisses_then_reverifies_home():
    from top_heroes_auto.automation.phase6_navigation import (
        EntryFrame,
        GuardedEntryNavigator,
        NavigationResult,
        NavigationStatus,
    )
    captured, known = receipt()
    frames = iter(EntryFrame(TARGET, replace(captured, timestamp=str(n))) for n in range(3))
    taps=[]
    class Port:
        def observe(self,tag):
            return next(frames)
        def tap(self,frame,point):
            taps.append(point)
    def detect(frame):
        return replace(known,state=ScreenState.GAME_HOME if frame.timestamp=='2' else ScreenState.EVENT_PROMO)
    navigator=GuardedEntryNavigator(Port(),None,detect,sleep=lambda _:None)
    result=NavigationResult(NavigationStatus.BLOCKED)
    home=navigator._home(result,'late-promo')
    assert home.screen.timestamp=='2' and taps==[(58,1203)]
    assert len(set(result.captures))==3


def test_upper_gift_pulsing_background_does_not_weaken_confidence_threshold():
    import cv2
    profile,_=_load_profile_details('vip-reward')
    adapter=FrameRewardAdapter(gift_profile(profile))
    current=screen('index2-vip-claimable.png')
    portrait=cv2.rotate(current.normalized,cv2.ROTATE_90_COUNTERCLOCKWISE)
    pulse=cv2.imread(str(FIXTURES/'gift-pulse.png'))
    portrait[155:250,600:705]=pulse
    fresh=replace(current,normalized=cv2.rotate(portrait,cv2.ROTATE_90_CLOCKWISE))
    observed=adapter.observe(fresh)
    assert gift_state(observed.screen)=='FREE_CLAIMABLE'
    assert all(e.score>=.96 for key,e in observed.evidence.items() if key in {'claim','free','available'})
    assert adapter.profile.anchor_map['free'].threshold==.96

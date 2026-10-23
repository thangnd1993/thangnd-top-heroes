"""Original run17 pixels and isolated production policy; no live transport."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.guild_mail_port import GuildMailPort
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.vision.event_collaboration_hub import collaboration_hub
from top_heroes_auto.vision.guild_mail import GuildMailDetector
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService

FIXTURES = Path(__file__).parent/'fixtures/run17'


def capture(name, image=None):
    payload = (FIXTURES/f'{name}.png').read_bytes() if image is None else cv2.imencode('.png',image)[1].tobytes()
    return ScreenshotService(lambda _: payload).take(Target(51,'unrelated-label','explicit-fixture','boot'))


@pytest.fixture(scope='module')
def recovery():
    return RecoveryScreenDetector()


@pytest.fixture(scope='module')
def mail():
    detector = GuildMailDetector(number_reader=lambda *a, **k: None)
    return detector, detector.observe(capture('mail-ticker')), detector.observe(capture('mail-system'))


def test_ticker_over_mail_is_unknown_without_generic_dismissal(mail):
    _, frame, _ = mail
    assert frame.page == 'UNKNOWN'
    assert frame.anchors['mail-title'].matched and frame.anchors['modal-close'].matched
    assert frame.overlay.state == ScreenState.UNKNOWN
    with pytest.raises(SafetyError):
        dismiss_overlay_bottom_left(frame.captured,frame.overlay)


def test_mail_settles_ticker_by_capture_only_then_retains_sibling_tabs(mail,monkeypatch):
    _, obscured, clear = mail
    port = object.__new__(GuildMailPort)
    port.dismissals = 0
    port.cancelled = lambda: False
    port.observe = lambda: clear
    calls = []
    port.dispatch = lambda *a: calls.append(a)
    monkeypatch.setattr('top_heroes_auto.app.guild_mail_port.wait', lambda *a,**k: None)
    assert port.settle(obscured) is clear
    assert not calls


def test_persistent_obscured_mail_wait_is_bounded_no_input(mail,monkeypatch):
    _, obscured, _ = mail
    port = object.__new__(GuildMailPort)
    port.dismissals = 0
    port.cancelled = lambda: False
    calls = []
    port.observe = lambda: (calls.append('capture') or obscured)
    port.dispatch = lambda *a: pytest.fail('No input on obscured Mail')
    monkeypatch.setattr('top_heroes_auto.app.guild_mail_port.wait', lambda *a,**k: None)
    assert port.settle(obscured) is obscured
    assert len(calls) == 6


@pytest.mark.parametrize('shift', [0, 12])
def test_original_system_nine_badge_is_positive_current_glyph(shift):
    image = cv2.imread(str(FIXTURES/'mail-system.png'))
    if shift:
        image = cv2.warpAffine(image,np.float32([[1,0,shift],[0,1,0]]),(720,1280))
    detector = GuildMailDetector(number_reader=lambda *a,**k: None)
    frame = detector.observe(capture('mail-system',image))
    tabs = detector.mail_tabs(frame)
    assert tabs['system']['count'] == 9 and tabs['system']['selected'] is False
    assert tabs['reports']['count'] is None  # Unqualified 42 is never guessed.


def test_badge_ocr_conflict_cannot_be_rescued_by_nine_template(mail):
    detector, _, frame = mail
    readings = iter([9,8,9])
    other = GuildMailDetector(number_reader=lambda *a,**k: next(readings))
    assert other.local_badge(frame,detector.mail_tabs(frame)['system']['box'],numbered=True) is None


def test_stale_navigation_frame_cannot_skip_capture(mail):
    _, old, current = mail
    port = object.__new__(GuildMailPort)
    port.last = current
    with pytest.raises(SafetyError,match='unconsumed'):
        port.opportunity('mail-system',initial=old)


def test_navigation_frame_avoids_redundant_capture_but_not_visual_qualification(mail):
    detector, _, current = mail
    port = object.__new__(GuildMailPort)
    port.last, port.detector = current, detector
    port.settle = lambda frame: frame
    port.observe_settled = lambda: pytest.fail('No second capture before an intervening input')
    frame, view = port.opportunity('mail-system',initial=current)
    assert frame is current and view.state == 'UNKNOWN'  # Tab is not selected.


def test_current_collaboration_caption_variants_discover_only_indicated_children():
    image = cv2.imread(str(FIXTURES/'collaboration-hub.png'))
    result = collaboration_hub(image)
    assert result['permission'] == 'NAVIGATION_HUB'
    assert {name for name,_ in result['children']} == {'treasure-caption','training-rewards-caption'}
    assert 'rewards' not in result


def test_collaboration_variant_duplicate_is_not_rescued():
    image = cv2.imread(str(FIXTURES/'collaboration-hub.png'))
    image[400:443,18:114] = image[277:320,18:114]
    assert collaboration_hub(image) is None


def test_collaboration_missing_caption_stays_unknown():
    image = cv2.imread(str(FIXTURES/'collaboration-hub.png'))
    image[277:321,617:719] = 0
    assert collaboration_hub(image) is None


@pytest.mark.parametrize('name,state', [('rank-notice',ScreenState.EVENT_PROMO),
                                     ('expedition-receipt',ScreenState.REWARD_RECEIPT)])
def test_actual_run17_overlay_variants_are_dismissible_but_not_claim_proof(recovery,name,state):
    screen = capture(name)
    result = recovery.detect(screen)
    assert result.state == state and result.confidence >= .98
    assert len(result.evidence) >= 2
    assert dismiss_overlay_bottom_left(screen,result) == (58,1203)


@pytest.mark.parametrize('name,box', [('rank-notice',(217,155,283,52)),
                                   ('rank-notice',(261,986,202,30)),
                                   ('expedition-receipt',(238,35,242,43)),
                                   ('expedition-receipt',(257,1137,208,40))])
def test_partial_overlay_never_authorizes_dismissal(recovery,name,box):
    image = cv2.imread(str(FIXTURES/f'{name}.png'))
    x,y,w,h = box
    image[y:y+h,x:x+w] = 0
    result = recovery.detect(capture(name,image))
    assert result.state not in {ScreenState.EVENT_PROMO,ScreenState.REWARD_RECEIPT}


def test_rank_notice_does_not_become_reward_receipt(recovery):
    assert recovery.detect(capture('rank-notice')).state != ScreenState.REWARD_RECEIPT


def test_compact_receipt_reversed_anchor_layout_is_not_dismissible(recovery):
    image = cv2.imread(str(FIXTURES/'expedition-receipt.png'))
    title = image[35:78,238:480].copy()
    prompt = image[1137:1177,257:465].copy()
    image[35:78,238:480] = 0
    image[1137:1177,257:465] = 0
    image[900:943,238:480] = title
    image[200:240,257:465] = prompt
    assert recovery.detect(capture('expedition-receipt',image)).state != ScreenState.REWARD_RECEIPT


def test_owned_daily_free_button_does_not_require_an_individual_red_badge():
    from top_heroes_auto.vision.fixed_rewards import MONTHLY_DAILY, FixedRewardDetector, claim_geometry

    path = FIXTURES.parent/'phase6_fixed/monthly-owned-current.png'
    screen = ScreenshotService(lambda _:path.read_bytes()).take(Target(51,'unrelated','explicit','boot'))
    detector = FixedRewardDetector()
    frame = detector.observe(screen)
    state, core, _ = detector.availability(frame,MONTHLY_DAILY)
    assert state == 'AVAILABLE'
    geometry = claim_geometry(frame,MONTHLY_DAILY,core)
    assert geometry['inside_allowed'] and geometry['outside_forbidden']


def test_process_consumes_navigation_observation_once(rig,mail):
    from top_heroes_auto.automation.guild_mail_claims import Opportunity, process

    manager, _, store = rig
    _, _, frame = mail
    # Use a test target matching the isolated rig, no real DB or device.
    frame = replace(frame,captured=replace(frame.captured,index=7,name='Farm-007'))
    task = store.create_task_run(manager.namespace,'mail',7,'Farm-007')
    calls = []
    def opportunity(reward, *, initial):
        calls.append(initial)
        return initial, Opportunity(reward,'NOT_AVAILABLE',remaining=0,context=reward)
    port = SimpleNamespace(opportunity=opportunity)
    outcome = {}
    process(port,store,manager.namespace,task,'mail-war','disk',outcome,lambda:None,initial=frame)
    assert calls == [frame] and outcome['result'] == 'NOT_AVAILABLE'
    assert not store.reward_claims(manager.namespace,7)


def test_expedition_receipt_alone_cannot_verify_or_repeat_the_claim(monkeypatch):
    from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
    from top_heroes_auto.automation.dynamic_events import Control, EventFrame
    from top_heroes_auto.vision.models import BoundingBox

    before = EventFrame('before',(51,'disk','serial','boot'),'event:relic:personal-tasks','view')
    target = Control('reward',BoundingBox(10,10,20,20),('selected-task-context','free','current'),
                     'reward',cost='FREE',available=True)
    following = iter([replace(before,capture='receipt',popup=True),
                      *(replace(before,capture=f'unknown-{n}',page='UNKNOWN') for n in range(4))])
    port = object.__new__(DynamicEventPort)
    port.rows = ()
    port.observe = lambda: next(following)
    port.transport = SimpleNamespace(last=SimpleNamespace(overlay=SimpleNamespace(state=ScreenState.REWARD_RECEIPT)))
    calls = []
    port.dismiss = lambda frame: calls.append(('dismiss',frame.capture))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.pause',lambda *a:None)
    assert port._claim_postcondition(before,target,'relic') == []
    assert calls == [('dismiss','receipt')]

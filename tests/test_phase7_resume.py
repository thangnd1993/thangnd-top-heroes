"""Saved fleet regressions. No LDPlayer or live store access."""
import sys
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.vision.guild_mail import GuildMailDetector, portrait
from top_heroes_auto.vision.models import ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService

ROOT = Path(__file__).parent/'fixtures/phase7_resume'


def capture(name):
    return ScreenshotService(lambda _: (ROOT/f'{name}.png').read_bytes()).take(
        Target(37,'offline-random','explicit-fixture','boot'))


@pytest.mark.parametrize('name,count', [('member-3',3),('member-4',6),('loot-post-one',1)])
def test_current_small_badge_without_ocr_is_qualified(name,count):
    detector = GuildMailDetector(number_reader=lambda *a,**kw:None)
    frame = detector.observe(capture(name))
    view = detector.availability(frame,'guild-'+frame.page)
    assert view.state == 'AVAILABLE' and view.remaining == count
    assert view.box == detector.control(frame,'gifts-quick','green')
    assert detector.action_geometry(frame,view.role,view.box)['tap'] == list(view.box.center)


def test_member_rows_do_not_define_availability():
    detector = GuildMailDetector(number_reader=lambda *a,**kw:None)
    frame = capture('member-3')
    image = portrait(frame).copy()
    image[460:1060,40:670] = 150
    changed = ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
        Target(84,'different-layout','explicit-fixture','boot'))
    observation = detector.observe(changed)
    view = detector.availability(observation,'guild-gifts-member')
    assert observation.page == 'gifts-member' and view.state == 'AVAILABLE' and view.remaining == 3


@pytest.mark.parametrize('mode',['duplicate','unrelated','weak'])
def test_badge_ambiguity_never_authorizes_quick_claim(mode):
    detector = GuildMailDetector(number_reader=lambda *a,**kw:None)
    original = detector.observe(capture('member-3'))
    box = detector.control(original,'gifts-quick','green')
    badge = detector.local_badge(original,box)
    image = portrait(original.captured).copy()
    patch = image[badge.y-2:badge.y+badge.height+2,badge.x-2:badge.x+badge.width+2].copy()
    if mode != 'duplicate':
        image[badge.y-4:badge.y+badge.height+4,badge.x-4:badge.x+badge.width+4] = 140
    if mode == 'weak':
        patch = cv2.GaussianBlur(patch,(9,9),4)
        image[badge.y-2:badge.y+badge.height+2,badge.x-2:badge.x+badge.width+2] = patch
    else:
        x = box.x+round(box.width*.65) if mode == 'duplicate' else 80
        image[badge.y-2:badge.y-2+patch.shape[0],x:x+patch.shape[1]] = patch
    changed = ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
        Target(37,'offline-random','explicit-fixture','boot'))
    frame = detector.observe(changed)
    assert detector.availability(frame,'guild-gifts-member').state == 'UNKNOWN'


def test_conflicting_badge_crops_fail_closed():
    readings = iter([3,4,3])
    detector = GuildMailDetector(number_reader=lambda *a,**kw:next(readings))
    frame = detector.observe(capture('member-3'))
    assert detector.availability(frame,'guild-gifts-member').state == 'UNKNOWN'


def test_mail_small_three_is_local_number_not_neighbor_text():
    detector = GuildMailDetector(number_reader=lambda *a,**kw:None)
    frame = detector.observe(capture('mail-10'))
    tabs = detector.mail_tabs(frame)
    assert set(tabs) == {'war','guild','system','reports','collection'}
    assert tabs['guild']['count'] == 3 and tabs['guild']['selected'] is False
    assert tabs['war']['count'] == tabs['collection']['count'] == 0
    assert tabs['system']['count'] is None and tabs['reports']['count'] is None


@pytest.mark.skipif(sys.platform != 'win32',reason='Saved runtime Windows OCR regression')
@pytest.mark.parametrize('name,expected',[
    ('loot-489',489),('mail-3',{'guild':3,'system':22,'reports':85}),
    ('mail-10',{'guild':3,'system':12,'reports':63}),
    ('mail-system-9',{'guild':3,'system':15,'reports':66}),
    ('mail-system-4',{'guild':3,'system':17,'reports':62}),
])
def test_saved_multidigit_badges_with_real_local_ocr(name,expected):
    detector = GuildMailDetector()
    frame = detector.observe(capture(name))
    if isinstance(expected,int):
        view = detector.availability(frame,'guild-gifts-loot')
        assert view.state == 'AVAILABLE' and view.remaining == expected
    else:
        tabs = detector.mail_tabs(frame)
        assert {tab:tabs[tab]['count'] for tab in expected} == expected


def test_known_assistance_popup_requires_paired_underlying_home():
    detector = RecoveryScreenDetector()
    frame = capture('home-assistance')
    result = detector.detect(frame)
    assert result.state == ScreenState.HOME_OVERLAY
    assert {e.anchor_id for e in result.evidence} == {'covered-home-shop','covered-home-world'}
    assert all(e.matched and e.score >= .98 for e in result.evidence)
    for evidence in result.evidence:
        image = frame.normalized.copy()
        b = evidence.normalized_box
        image[b.y:b.y+b.height,b.x:b.x+b.width] = 0
        assert detector.detect(replace(frame,normalized=image)).state == ScreenState.POPUP_GENERIC


def test_shop_daily_rocking_badge_remains_paired_to_current_free_gift():
    from top_heroes_auto.vision.fixed_rewards import FixedRewardDetector, claim_geometry

    detector = FixedRewardDetector()
    frame = detector.observe(capture('shop-daily-rocking'))
    state,core,badge = detector.availability(frame,'shop-daily-gift')
    assert state == 'AVAILABLE' and core.score > .98 and badge.score > .98
    geometry = claim_geometry(frame,'shop-daily-gift',core)
    assert geometry['inside_allowed'] and geometry['outside_forbidden']
    image = frame.captured.normalized.copy()
    b = badge.normalized_box
    image[b.y-5:b.y+b.height+5,b.x-5:b.x+b.width+5] = 0
    changed = detector.observe(replace(frame.captured,normalized=image))
    assert detector.availability(changed,'shop-daily-gift')[0] == 'UNKNOWN'


def test_home_overlay_allows_only_one_bounded_back_after_fresh_proof():
    from test_overlay_dismissal import RecoveryPort

    from top_heroes_auto.automation.recovery import HomeRecoveryEngine, RecoveryStatus

    port = RecoveryPort([ScreenState.HOME_OVERLAY]*3+[ScreenState.GAME_HOME])
    backs = []
    port.dismiss_home_overlay_back = lambda observation: backs.append(observation)
    result = HomeRecoveryEngine(sleep=lambda _:None).ensure_game_home(port)
    assert result.status == RecoveryStatus.SUCCESS
    assert len(port.actions) == len(backs) == 1
    assert 'dismiss_home_overlay_back' in result.actions
    for state in (ScreenState.UNKNOWN,ScreenState.POPUP_GENERIC):
        port = RecoveryPort([state]*3)
        port.dismiss_home_overlay_back = lambda observation: pytest.fail('Blind Back')
        result = HomeRecoveryEngine(sleep=lambda _:None).ensure_game_home(port)
        assert result.status != RecoveryStatus.SUCCESS and not port.actions


def test_production_back_requires_current_paired_home_and_never_reuses_frame():
    from types import SimpleNamespace

    from top_heroes_auto.app.recovery_cli import DiagnosticRecoveryPort
    from top_heroes_auto.automation.guard import SafetyError

    port = object.__new__(DiagnosticRecoveryPort)
    frame = capture('home-assistance')
    detection = RecoveryScreenDetector().detect(frame)
    target = Target(frame.index,frame.name,frame.serial,frame.boot_id)
    calls = []
    port.index,port.name,port.snapshot = frame.index,frame.name,'snapshot'
    port.manager = SimpleNamespace(execute=lambda *a,**kw:calls.append((a,kw)))
    for state in (ScreenState.UNKNOWN,ScreenState.POPUP_GENERIC):
        other = replace(detection,state=state)
        port._overlay_frame = target,frame,other
        with pytest.raises(SafetyError):
            port.dismiss_home_overlay_back(SimpleNamespace(detection=other))
    assert not calls
    port._overlay_frame = target,frame,detection
    observation = SimpleNamespace(detection=detection)
    port.dismiss_home_overlay_back(observation)
    assert calls == [((frame.index,'keyevent'),dict(values=(4,),snapshot='snapshot',observed_target=target))]
    assert port._after_overlay and port._overlay_frame is None
    with pytest.raises(SafetyError):
        port.dismiss_home_overlay_back(observation)


@pytest.mark.parametrize('tab', ['war', 'guild'])
def test_mail_two_badge_on_selected_and_inactive_tab(tab):
    detector = GuildMailDetector(number_reader=lambda *a, **kw: None)
    frame = detector.observe(capture('mail-two'))
    assert frame.page == 'mail'
    tabs = detector.mail_tabs(frame)
    assert tabs[tab]['count'] == 2
    assert tabs[tab]['selected'] is (tab == 'war')
    assert tabs['collection']['count'] == 0
    assert tabs['system']['count'] is None and tabs['reports']['count'] is None


def test_mail_two_conflicting_ocr_does_not_use_template():
    readings = iter([2, 3, 2])
    detector = GuildMailDetector(number_reader=lambda *a, **kw: None)
    frame = detector.observe(capture('mail-two'))
    box = detector.mail_tabs(frame)['guild']['box']
    detector.number_reader = lambda *a, **kw: next(readings)
    assert detector.local_badge(frame, box, numbered=True) is None


def test_mail_two_weak_badge_remains_unknown():
    detector = GuildMailDetector(number_reader=lambda *a, **kw: None)
    original = detector.observe(capture('mail-two'))
    box = detector.mail_tabs(original)['guild']['box']
    badge = detector.local_badge(original, box)
    image = portrait(original.captured).copy()
    image[badge.y:badge.y+badge.height, badge.x:badge.x+badge.width] = cv2.GaussianBlur(
        image[badge.y:badge.y+badge.height, badge.x:badge.x+badge.width], (9,9), 4)
    changed = ScreenshotService(lambda _: cv2.imencode('.png', image)[1].tobytes()).take(
        Target(51, 'unrelated-test-name', 'explicit-fixture', 'boot'))
    frame = detector.observe(changed)
    assert detector.local_badge(frame, box, numbered=True) is None


@pytest.mark.parametrize('shift', [0, 12])
def test_current_selected_mail_one_is_available_at_current_position(shift):
    detector = GuildMailDetector(number_reader=lambda *a, **kw: None)
    captured = capture('mail-one-selected')
    if shift:
        image = portrait(captured)
        image = cv2.warpAffine(image, np.float32([[1,0,shift],[0,1,8]]),
                               (image.shape[1],image.shape[0]))
        captured = ScreenshotService(lambda _: cv2.imencode('.png',image)[1].tobytes()).take(
            Target(62,'another-fixture','explicit-fixture','boot'))
    frame = detector.observe(captured)
    tabs = detector.mail_tabs(frame)
    assert tabs['system']['selected'] is True and tabs['system']['count'] == 1
    assert all(tabs[t]['count'] == 0 for t in ('war','guild','reports','collection'))
    view = detector.availability(frame,'mail-system')
    assert view.state == 'AVAILABLE' and view.remaining == 1
    geometry = detector.action_geometry(frame,view.role,view.box,view.forbidden)
    assert geometry['tap'] == list(view.box.center)


@pytest.mark.parametrize('mode', ['weak', 'duplicate'])
def test_mail_one_badge_uncertainty_stays_unknown(mode):
    detector = GuildMailDetector(number_reader=lambda *a, **kw: None)
    original = detector.observe(capture('mail-one-selected'))
    box = detector.mail_tabs(original)['system']['box']
    badge = detector.local_badge(original,box)
    image = portrait(original.captured).copy()
    patch = image[badge.y:badge.y+badge.height,badge.x:badge.x+badge.width].copy()
    if mode == 'weak':
        image[badge.y:badge.y+badge.height,badge.x:badge.x+badge.width] = cv2.GaussianBlur(patch,(9,9),4)
    else:
        x = badge.x+badge.width+8
        image[badge.y:badge.y+badge.height,x:x+badge.width] = patch
    changed = ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
        Target(62,'another-fixture','explicit-fixture','boot'))
    assert detector.local_badge(detector.observe(changed),box,numbered=True) is None

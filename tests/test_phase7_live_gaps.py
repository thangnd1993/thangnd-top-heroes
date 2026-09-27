"""Regressions from the original bound Guild/Mail run, without real input."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.guild_mail_port import GuildMailPort
from top_heroes_auto.vision.guild_mail import GuildMailDetector
from top_heroes_auto.vision.models import BoundingBox, ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService

ROOT = Path(__file__).parent/'fixtures/phase7'


def capture(name):
    return ScreenshotService(lambda _:(ROOT/f'{name}.png').read_bytes()).take(Target(17,'offline','explicit','boot'))


@pytest.mark.parametrize('name',['guild-receipt-current','mail-receipt-current'])
def test_receipt_text_ignores_blurred_background_but_is_paired(name):
    detector = RecoveryScreenDetector()
    frame = capture(name)
    result = detector.detect(frame)
    assert result.state == ScreenState.REWARD_RECEIPT and result.confidence > .98
    assert {e.anchor_id for e in result.evidence} == {'receipt-title','receipt-continue'}
    assert GuildMailDetector().observe(frame).page == 'UNKNOWN'


@pytest.mark.parametrize('mutation',['missing_title','missing_continue','duplicate','unrelated'])
def test_detail_receipt_is_not_permission_from_partial_or_duplicate(mutation):
    detector = RecoveryScreenDetector()
    frame = capture('mail-receipt-current')
    evidence = detector.detect(frame).evidence
    pixels = frame.normalized.copy()
    boxes = {e.anchor_id:e.normalized_box for e in evidence}
    b = boxes['receipt-title' if mutation == 'missing_title' else 'receipt-continue']
    if mutation == 'duplicate':
        patch = pixels[b.y:b.y+b.height,b.x:b.x+b.width].copy()
        pixels[20:20+b.height,400:400+b.width] = patch
    elif mutation == 'unrelated':
        pixels[:] = 100
    else:
        pixels[b.y:b.y+b.height,b.x:b.x+b.width] = 0
    assert detector.detect(replace(frame,normalized=pixels)).state == ScreenState.UNKNOWN


def test_receipt_location_comes_from_shifted_frame():
    detector = RecoveryScreenDetector()
    frame = capture('mail-receipt-current')
    matrix = cv2.getRotationMatrix2D((0,0),0,1)
    matrix[:,2] = 35,25
    moved = detector.detect(replace(frame,normalized=cv2.warpAffine(frame.normalized,matrix,frame.normalized_size)))
    assert moved.state == ScreenState.REWARD_RECEIPT
    for a,b in zip(detector.detect(frame).evidence,moved.evidence,strict=True):
        assert (b.normalized_box.x-a.normalized_box.x,b.normalized_box.y-a.normalized_box.y) == (35,25)


def test_live_green_donation_stays_separate_from_diamonds():
    detector = GuildMailDetector(number_reader=lambda *a,**kw:20)
    frame = detector.observe(capture('donation-live'))
    view = detector.availability(frame,'guild-technology')
    assert view.state == 'AVAILABLE' and view.remaining == 20
    assert frame.anchors['donation-green'].score >= .97
    assert view.box.x > view.forbidden[0].x+view.forbidden[0].width
    assert detector.action_geometry(frame,view.role,view.box,view.forbidden)['tap'] == list(view.box.center)


def test_selected_guild_tab_badge_four_qualified_without_ocr_guess():
    detector = GuildMailDetector(number_reader=lambda *a,**kw:None)
    frame = detector.observe(capture('mail-guild-live'))
    tab = detector.mail_tabs(frame)['guild']
    assert tab['count'] == 4 and tab['selected'] is True
    assert detector.availability(frame,'mail-guild').state == 'AVAILABLE'
    # The whole local red badge is required; a 6 inside 60 is not a single 6.
    assert detector.mail_tabs(frame)['reports']['count'] is None


@pytest.mark.parametrize('after_pages,expected',[(['guild','territory'],'territory'),
    (['guild','guild','guild'],None),(['UNKNOWN'],None),(['mail'],None)])
def test_navigation_waits_only_for_original_dispatch(monkeypatch,after_pages,expected):
    monkeypatch.setattr('top_heroes_auto.app.guild_mail_port.time.sleep',lambda _:None)
    origin = SimpleNamespace(page='guild',box=lambda _:BoundingBox(1,1,10,10),anchors={'guild-territory':'anchor'})
    observations = iter(SimpleNamespace(page=p) for p in after_pages)
    port = object.__new__(GuildMailPort)
    port.observe_settled = lambda:next(observations)
    inputs = []
    port.tap = lambda *a:inputs.append(a)
    if expected:
        assert port.navigate(origin,'guild-territory','territory').page == expected
    else:
        with pytest.raises(Exception,match='Navigation expected'):
            port.navigate(origin,'guild-territory','territory')
    assert len(inputs) == 1

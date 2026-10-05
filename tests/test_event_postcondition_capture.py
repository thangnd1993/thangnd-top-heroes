"""Late qualified receipts retain two fresh proof frames, never another claim."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.vision.models import BoundingBox, ScreenState

IDENTITY = (10, 'account', 'explicit-serial', 'boot')
PAGE = 'event:current:personal-tasks'


def frame(n, page=PAGE, *, popup=False, identity=IDENTITY):
    return EventFrame(str(n), identity, page, str(n), popup=popup)


def harness(monkeypatch, frames, rows=()):
    port = object.__new__(DynamicEventPort)
    port.rows = rows
    port.transport = SimpleNamespace(last=SimpleNamespace(
        overlay=SimpleNamespace(state=ScreenState.REWARD_RECEIPT)))
    captures, dismissals = [], []
    source = iter(frames)

    def observe():
        current = next(source)
        captures.append(current.capture)
        return current

    port.observe = observe
    port.dismiss = lambda current: dismissals.append(current.capture)
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep', lambda _: None)
    target = Control('reward', BoundingBox(1, 1, 10, 10), (), 'reward')
    return port, target, captures, dismissals


@pytest.mark.parametrize('receipt_at', [3, 4])
def test_late_receipt_keeps_two_underlying_frames(monkeypatch, receipt_at):
    frames = [frame(n, 'UNKNOWN') for n in range(receipt_at)]
    frames += [frame(receipt_at, popup=True), frame(receipt_at+1), frame(receipt_at+2)]
    port, target, captures, dismissals = harness(monkeypatch, frames)
    effects = []

    def effect(before, after, receipt):
        effects.append((before, after, receipt))
        return ['independent-proof']

    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.removal_effect', effect)
    assert port._claim_postcondition(frame('before'), target, 'current') == ['independent-proof']
    assert effects[0][1:] == ([str(receipt_at+1), str(receipt_at+2)], str(receipt_at))
    assert len(captures) == receipt_at+3
    assert dismissals == [str(receipt_at)]


def test_unknown_only_keeps_five_capture_budget_and_no_input(monkeypatch):
    port, target, captures, dismissals = harness(monkeypatch, [frame(n, 'UNKNOWN') for n in range(7)])
    assert port._claim_postcondition(frame('before'), target, 'current') == []
    assert len(captures) == 5
    assert dismissals == []


def test_changed_identity_popup_never_dismissed(monkeypatch):
    port, target, captures, dismissals = harness(monkeypatch, [frame(0, popup=True, identity=(10, 'account', 'other', 'boot'))])
    assert port._claim_postcondition(frame('before'), target, 'current') == []
    assert captures == ['0']
    assert dismissals == []


def test_receipt_alone_does_not_verify(monkeypatch):
    port, target, captures, dismissals = harness(monkeypatch, [frame(0, popup=True)]+[frame(n, 'UNKNOWN') for n in range(1, 7)])
    assert port._claim_postcondition(frame('before'), target, 'current') == []
    assert len(captures) == 5
    assert dismissals == ['0']


def test_still_available_stops_without_retry(monkeypatch):
    port, target, captures, dismissals = harness(monkeypatch, [frame(0)], [{'identity': 'reward', 'state': 'AVAILABLE'}])
    assert port._claim_postcondition(frame('before'), target, 'current') == []
    assert captures == ['0']
    assert dismissals == []


def test_changed_page_is_not_success(monkeypatch):
    port, target, _, dismissals = harness(monkeypatch, [frame(0, 'home')])
    assert port._claim_postcondition(frame('before'), target, 'current') == []
    assert dismissals == []


@pytest.mark.parametrize('receipt',[True,False])
def test_grid_needs_receipt_and_two_independent_unavailable_frames(monkeypatch,receipt):
    frames=([frame(0,popup=True)] if receipt else [])+[frame(n) for n in range(1,7)]
    port,target,_,dismissals=harness(monkeypatch,frames,[{'identity':'reward','state':'NOT_AVAILABLE'}])
    target=replace(target,evidence=('qualified-task-grid',))
    result=port._claim_postcondition(frame('before'),target,'current')
    assert len(result)==(2 if receipt else 0)
    assert dismissals==(['0'] if receipt else [])

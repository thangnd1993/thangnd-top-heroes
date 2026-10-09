"""A small blue Go label must not turn a known list into UNKNOWN after scrolling."""
from dataclasses import replace
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.dynamic_events import event_body_contract, task_card_boxes, task_reward_rows
from top_heroes_auto.vision.models import BoundingBox


def evidence():
    image = cv2.imread('tests/fixtures/phase8/task-list-blue-go-small-font.png')
    template = cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    return image, template


def reader_for(image, template, *, native='', second='Den', third='Den'):
    # The saved frame's one shorter card loses the native-scale OCR glyph.
    height = round(min(card.height for card in task_card_boxes(image, template)) * .65)
    calls = []

    def read(crop):
        calls.append(crop.shape[0])
        text = {height: native, height * 2: second, height * 3: third}.get(crop.shape[0], 'Den')
        return [{'text': text}] if text else []

    return read, calls, height


def test_saved_scrolled_list_requires_two_enlarged_go_readings():
    image, template = evidence()
    read, calls, height = reader_for(image, template)
    rows = task_reward_rows(image, template, reader=read)
    assert len(rows) == len(task_card_boxes(image, template)) == 3
    assert all(row['state'] == 'NOT_AVAILABLE' for row in rows)
    assert calls.count(height * 3) == 1
    assert event_body_contract(image, rows, template, reader=read) == 'TASK_LIST'


@pytest.mark.parametrize('native,second,third', [
    ('', 'Den', ''), ('', 'Den', 'Den 100'), ('', 'Den', 'Nhan'),
    ('Mua', 'Den', 'Den'), ('', 'Nhan', 'Nhan'), ('', 'Mien phi', 'Mien phi'),
])
def test_missing_conflicting_cost_or_claim_labels_stay_unqualified(native, second, third):
    image, template = evidence()
    read, _, _ = reader_for(image, template, native=native, second=second, third=third)
    rows = task_reward_rows(image, template, reader=read)
    assert len(rows) == 2
    assert all(row['state'] == 'NOT_AVAILABLE' for row in rows)
    assert event_body_contract(image, rows, template, reader=read) == 'UNSUPPORTED'


def test_original_native_go_agreement_does_not_need_third_reading():
    image, template = evidence()
    read, calls, height = reader_for(image, template, native='Den', third='Mua 100')
    assert len(task_reward_rows(image, template, reader=read)) == 3
    assert height * 3 not in calls


def test_enlarged_go_evidence_never_qualifies_a_green_claim_control():
    image, template = evidence()
    rows = task_reward_rows(image, template, reader=lambda _: [{'text': 'Den'}])
    box = rows[0]['box']
    image[box.y:box.y+box.height, box.x:box.x+box.width] = (40, 200, 70)
    read, _, _ = reader_for(image, template)
    remaining = task_reward_rows(image, template, reader=read)
    assert len(remaining) == 2
    assert all(row['state'] == 'NOT_AVAILABLE' for row in remaining)
    assert event_body_contract(image, remaining, template, reader=read) == 'UNSUPPORTED'


def scroll_rig(monkeypatch):
    image, template = evidence()
    read, _, _ = reader_for(image, template)
    rows = task_reward_rows(image, template, reader=read)
    first, last = rows[0]['row'], rows[-1]['row']
    box = BoundingBox(first.x+round(first.width*.20), first.y+20,
                      round(first.width*.40), last.y+last.height-first.y-40)
    current = Control('task-list-vertical', box,
                      ('selected-task-context', 'complete-card-list', 'outside-action-column'), 'scroll')
    previous = replace(current, box=replace(box, y=box.y-10))
    frame = EventFrame('previous', (13, 'disk', 'explicit', 'boot'),
                       'event:qualified:personal-tasks', 'before', (previous,), True)
    fresh = replace(frame, capture='fresh', fingerprint='different', controls=(current,))
    port = object.__new__(DynamicEventPort)
    sent = []
    port.transport = SimpleNamespace(
        last=SimpleNamespace(captured=SimpleNamespace(original=image, rotated_from_portrait=False)),
        dispatch=lambda *args: sent.append(args))
    port.current = frame
    port.observe = lambda: fresh
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep', lambda _: None)
    return port, frame, previous, fresh, current, sent


def test_scrolled_list_swipe_uses_fresh_geometry_not_pixel_equality(monkeypatch):
    port, frame, previous, _, current, sent = scroll_rig(monkeypatch)
    port.navigate(frame, previous)
    box = current.box
    assert sent[0][1:] == ('swipe', (box.center[0], box.y+round(box.height*.75),
                                    box.center[0], box.y+round(box.height*.25), 450))
    assert len(sent) == 1 and port.current is None


@pytest.mark.parametrize('variant', ['blocked', 'unknown', 'popup', 'duplicate', 'runtime'])
def test_scrolled_list_unsafe_fresh_frame_still_sends_no_input(monkeypatch, variant):
    port, frame, previous, fresh, current, sent = scroll_rig(monkeypatch)
    changes = {
        'blocked': dict(blocked=('EVENT_CONTENT_REQUIRES_QUALIFICATION',)),
        'unknown': dict(coverage_known=False),
        'popup': dict(popup=True),
        'duplicate': dict(controls=(current, current)),
        'runtime': dict(identity=(13, 'disk', 'different', 'boot')),
    }
    port.observe = lambda: replace(fresh, **changes[variant])
    with pytest.raises(SafetyError, match='fresh capture'):
        port.navigate(frame, previous)
    assert not sent

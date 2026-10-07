"""Saved fleet blockers must not become successful empty Event scans."""
from dataclasses import replace

import cv2
import numpy as np
import pytest

from top_heroes_auto.vision.event_task_grid import task_grid_shell
from top_heroes_auto.vision.system_dialog import system_dialog


def image(name):
    return cv2.imread('tests/fixtures/phase8/'+name+'.png')


def notice(_):
    return [{'text': "System UI isn't responding Close app Wait"}]


def test_saved_android_dialog_positive_and_unreadable_fail_closed():
    im = image('android-system-ui-blocker')
    result = system_dialog(im, reader=notice)
    assert result['reason'] == 'SYSTEM_UI_NOT_RESPONDING'
    assert not result['input_allowed']
    assert system_dialog(im, reader=lambda _: [])['reason'] == 'BLOCKING_SYSTEM_DIALOG'


@pytest.mark.parametrize('name', ['home-entry-jitter-a', 'task-grid-live-clipped',
                                 'task-grid-partial-free', 'home-event-before-animation',
                                 'match-notice', 'paid-offer-one', 'paid-offer-two'])
def test_real_game_screens_are_not_android_dialogs(name):
    assert system_dialog(image(name), reader=notice) is None


def test_production_home_false_positive_cannot_scan_or_dismiss(tmp_path, monkeypatch):
    from test_event_evidence_contracts import home_port

    p, sent = home_port(tmp_path, monkeypatch)
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.portrait',
                        lambda _: image('android-system-ui-blocker'))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.read_words', notice)
    frame = p.observe()
    assert frame.page == 'UNKNOWN' and not frame.coverage_known
    assert not frame.event_scan_performed and not frame.popup and not frame.render_pending
    assert not frame.controls and frame.parent is None
    assert frame.blocked == ('SYSTEM_UI_NOT_RESPONDING',)
    assert not sent


def test_live_grid_scroll_is_inside_current_viewport_and_disjoint_from_cards():
    im = image('task-grid-live-clipped')
    shell = task_grid_shell(im)
    assert shell and len(shell['cards']) == 3  # Clipped rewards remain ineligible.
    scroll = shell['scroll']
    assert min(b.x for b in shell['cards']) < scroll.x < max(b.x for b in shell['cards'])
    assert all(scroll.x >= b.x+b.width or scroll.x+scroll.width <= b.x for b in shell['cards'])
    shifted = cv2.warpAffine(im, np.float32([[1, 0, 8], [0, 1, 10]]), (720, 1280))
    assert task_grid_shell(shifted)['scroll'] == replace(scroll, x=scroll.x+8, y=scroll.y+10)
    # A button/overlay occupying the gesture gutter must invalidate it.
    im[scroll.y+100:scroll.y+180, scroll.x:scroll.x+scroll.width] = (0, 255, 0)
    assert task_grid_shell(im) is None


def test_android_dialog_stops_explorer_without_game_recovery():
    from test_dynamic_events import Port, control, frame

    from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer

    p = Port([frame('home', 1, [control('event', 'event')]),
              frame('UNKNOWN', 2, blocked=('SYSTEM_UI_NOT_RESPONDING',))])
    p.recover_home = lambda: pytest.fail('Android dialog must not trigger game recovery')
    result = DynamicEventExplorer().run(p)
    assert result.result == 'BLOCKED'
    assert len(p.calls) == 1 and p.calls[0][1] == 'event'
    assert any(b['reason'] == 'SYSTEM_UI_NOT_RESPONDING' for b in result.blocked)


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows OCR')
def test_saved_android_notice_real_ocr():
    from top_heroes_auto.vision.local_ocr import read_words

    assert system_dialog(image('android-system-ui-blocker'), reader=read_words)['reason'] == 'SYSTEM_UI_NOT_RESPONDING'


def grid_navigation(monkeypatch, *, qualified=True, blocked=()):
    from types import SimpleNamespace

    from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
    from top_heroes_auto.automation.dynamic_events import Control, EventFrame

    im = image('task-grid-live-clipped')
    shell = task_grid_shell(im)
    evidence = ('functional-tasks-word', 'qualified-task-grid', 'outside-task-actions') if qualified else ('qualified-menu-grid',)
    control = Control('task-grid-vertical' if qualified else 'menu-grid-vertical', shell['scroll'], evidence, 'scroll')
    parent = Control('current-back', shell['back'], ('qualified-close',), 'parent')
    old = EventFrame('before', (8, 'disk', 'explicit', 'boot'), 'event:race-task-grid', 'a',
                     (control,), True, parent)
    fresh_control = replace(control, box=replace(control.box, x=control.box.x+8, y=control.box.y+10))
    fresh = replace(old, capture='fresh', fingerprint='b', controls=(fresh_control,), blocked=blocked)
    port = object.__new__(DynamicEventPort)
    sent = []
    observed = SimpleNamespace(captured=SimpleNamespace(original=im, rotated_from_portrait=False))
    port.transport = SimpleNamespace(last=observed, dispatch=lambda *a: sent.append(a))
    port.current = old
    port.observe = lambda: fresh
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep', lambda _: None)
    return port, old, control, fresh_control, sent


def test_production_swipe_accepts_current_qualified_narrow_grid_gutter(monkeypatch):
    port, frame, control, current, sent = grid_navigation(monkeypatch)
    assert current.box.width == 4
    port.navigate(frame, control)
    b = current.box
    assert sent[0][1:] == ('swipe', (b.center[0], b.y+round(b.height*.75),
                                   b.center[0], b.y+round(b.height*.25), 450))
    assert len(sent) == 1 and port.current is None


def test_other_narrow_scroll_surfaces_remain_rejected(monkeypatch):
    from top_heroes_auto.automation.guard import SafetyError

    port, frame, control, _, sent = grid_navigation(monkeypatch, qualified=False)
    with pytest.raises(SafetyError, match='swipe ROI'):
        port.navigate(frame, control)
    assert not sent


def test_fresh_grid_blocker_prevents_scroll_dispatch(monkeypatch):
    from top_heroes_auto.automation.guard import SafetyError

    port, frame, control, _, sent = grid_navigation(monkeypatch, blocked=('UNQUALIFIED_TASK_GRID_ACTION',))
    with pytest.raises(SafetyError, match='fresh capture'):
        port.navigate(frame, control)
    assert not sent

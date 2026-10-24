"""Run20 original pixels and production regressions; no emulator access."""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.app.recovery_cli import DiagnosticRecoveryPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame, EventNavigationRejected
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.event_task_grid import task_grid_shell
from top_heroes_auto.vision.fixed_rewards import MONTHLY_DAILY, FixedRewardDetector
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.screenshot import ScreenshotService
from top_heroes_auto.vision.vip_countdown import countdown_box

FIXTURES = Path(__file__).parent/'fixtures/run20'


@pytest.mark.parametrize('name', ['vip-disabled-2', 'vip-disabled-4'])
def test_actual_run20_disabled_clocks_need_two_complete_readings(name):
    image = cv2.imread(str(FIXTURES/(name+'.png')))
    assert countdown_box(image) == BoundingBox(527, 853, 148, 55)


@pytest.mark.parametrize('last', ['20:02:43', '20:02:44', '', '25:02:43'])
def test_clock_empty_small_render_only_rescued_by_exact_padded_agreement(last):
    calls = []
    texts = iter(['', '20:02:43', last])

    def read(image):
        calls.append(image.shape)
        return [dict(text=next(texts))]

    result = countdown_box(cv2.imread(str(FIXTURES/'vip-disabled-2.png')), reader=read)
    assert bool(result) == (last == '20:02:43')
    assert len(calls) == 3 and calls[2][0] > calls[1][0]


@pytest.mark.parametrize('first', ['garbage', '20:02:44'])
def test_nonempty_conflicting_clock_is_not_replaced(first):
    texts = iter([first, '20:02:43'])
    assert countdown_box(cv2.imread(str(FIXTURES/'vip-disabled-2.png')),
                         reader=lambda _: [dict(text=next(texts))]) is None


def held_port(name='grid-held-reward'):
    data = json.loads((FIXTURES/(name+'.json')).read_text(encoding='utf-8'))
    image = cv2.imread(str(FIXTURES/(name+'.png')))
    port = object.__new__(DynamicEventPort)
    port.rows = tuple(dict(r, row=BoundingBox(**r['row']), box=BoundingBox(**r['box']))
                      for r in data['reward_rows'])
    port.navigation_image = image
    if name == 'grid-held-reward':
        box = task_grid_shell(image)['scroll']
        control = Control('task-grid-vertical', box,
            ('functional-tasks-word', 'qualified-task-grid', 'outside-task-actions'), 'scroll')
    else:
        control = Control('task-list-vertical', BoundingBox(180, 500, 100, 400),
            ('selected-task-context', 'complete-card-list', 'outside-action-column'), 'scroll')
    frame = EventFrame('old', (23, 'disk', 'explicit', 'boot'), data['page'], 'view',
                       (control,), True, blocked=tuple(data['blocked']), stable_id='disk')
    return port, frame, control


@pytest.mark.parametrize('name', ['grid-held-reward', 'expedition-held-rewards'])
def test_known_journal_block_does_not_block_independent_current_scroll(name):
    port, frame, control = held_port(name)
    before = tuple(dict(r) for r in port.rows)
    assert port._scroll_blockers_safe(frame, control)
    assert port.rows == before
    assert all(r['state'] == 'UNKNOWN' for r in port.rows if
               any('saved-reward-identity' in e for e in r['evidence']))
    assert not any(c.kind == 'reward' for c in frame.controls)


@pytest.mark.parametrize('change', ['unknown-label', 'missing-card', 'popup-blocker', 'wrong-page'])
def test_held_grid_scroll_still_rejects_unqualified_visual_evidence(change):
    port, frame, control = held_port()
    if change == 'unknown-label':
        port.rows = tuple(dict(r, evidence=('complete-reward-card',))
                          if r['state'] == 'UNKNOWN' else r for r in port.rows)
    elif change == 'missing-card':
        port.rows = tuple(r for r in port.rows if r['state'] != 'UNKNOWN')
    elif change == 'popup-blocker':
        frame = replace(frame, blocked=(*frame.blocked, 'BLOCKING_SYSTEM_DIALOG'))
    else:
        frame = replace(frame, page='UNKNOWN')
    assert not port._scroll_blockers_safe(frame, control)


def test_actual_grid_navigates_only_on_fresh_same_identity_and_keeps_reward_held(monkeypatch):
    port, frame, control = held_port()
    fresh = replace(frame, capture='fresh')
    screen = ScreenshotService(lambda _: (FIXTURES/'grid-held-reward.png').read_bytes()).take(
        Target(23, 'display', 'explicit', 'boot'))
    calls = []
    port.current = frame
    port.observe = lambda: fresh
    port.transport = SimpleNamespace(last=SimpleNamespace(captured=screen),
                                      dispatch=lambda *args: calls.append(args))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.pause', lambda *a: None)
    port.navigate(frame, control)
    assert len(calls) == 1 and calls[0][1] == 'swipe'
    assert calls[0][2][0] == calls[0][2][2] == control.box.center[0]
    assert any(r['state'] == 'UNKNOWN' for r in port.rows)
    port.current = frame
    port.observe = lambda: replace(fresh, popup=True)
    with pytest.raises(EventNavigationRejected):
        port.navigate(frame, control)
    assert len(calls) == 1


def test_metadata_cache_reads_once_but_checks_changes_addition_and_removal(tmp_path, monkeypatch):
    metadata = dict(id='one', state='UNKNOWN', template='one.png',
                    expected_region=[0, 0, 1, 1], threshold=.98)
    path = tmp_path/'one.json'
    path.write_text(json.dumps(metadata), encoding='utf-8')
    reads = []
    read = Path.read_text

    def tracked(path, *args, **kwargs):
        reads.append(path)
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', tracked)
    first = load_anchors(tmp_path)
    assert load_anchors(tmp_path) is first and len(reads) == 1
    path.write_text(json.dumps(dict(metadata, threshold=.995)), encoding='utf-8')
    assert load_anchors(tmp_path)[0].threshold == .995
    other = tmp_path/'two.json'
    other.write_text(json.dumps(dict(metadata, id='two')), encoding='utf-8')
    assert len(load_anchors(tmp_path)) == 2
    path.unlink()
    assert [a.id for a in load_anchors(tmp_path)] == ['two']
    other.write_text('invalid', encoding='utf-8')
    with pytest.raises(ValueError):
        load_anchors(tmp_path)


def test_launch_output_is_evidence_not_home_success_or_a_retry():
    port = object.__new__(DiagnosticRecoveryPort)
    calls = []
    port.index, port.name, port.package, port.snapshot = 23, 'display only', 'game.package', object()
    port.clock = lambda: 1
    port.game_launch_evidence = []
    port.manager = SimpleNamespace(execute=lambda *a, **k: calls.append(a) or 'Events injected: 0')
    port.launch_game()
    assert len(calls) == 1 and calls[0][:2] == (23, 'open_game')
    record = port.game_launch_evidence[0]
    assert record['output'] == 'Events injected: 0' and record['result'] == 'TRANSPORT_RETURNED'
    assert 'SUCCESS' not in record.values()


def test_actual_monthly_compact_received_label_and_duplicate_veto():
    image = cv2.imread(str(FIXTURES/'monthly-received.png'))
    detector = FixedRewardDetector()

    def observe(image):
        return detector.observe(ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(
            Target(23, 'display only', 'explicit', 'boot')))

    frame = observe(image)
    assert frame.page == 'shop-monthly'
    assert not frame.anchors['monthly-owned-label'].matched
    assert detector.availability(frame, MONTHLY_DAILY)[0] == 'NOT_AVAILABLE'
    # One positive label cannot mask a second copy elsewhere in the daily panel.
    duplicate = image.copy()
    duplicate[950:992,168:282] = image[1073:1115,168:282]
    assert detector.availability(observe(duplicate), MONTHLY_DAILY)[0] == 'UNKNOWN'
    hidden = image.copy()
    hidden[1073:1115,168:282] = 0
    assert detector.availability(observe(hidden), MONTHLY_DAILY)[0] == 'UNKNOWN'
    assert detector.availability(replace(frame, page='UNKNOWN'), MONTHLY_DAILY)[0] == 'UNKNOWN'


def test_initial_selected_tab_is_not_reopened_but_other_tabs_and_events_continue():
    from test_dynamic_events import Port, control, frame

    from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer

    root, other, back = control('root', 'event'), control('other', 'event'), control('back', 'parent')
    evidence = ('event-shell', 'tab-strip', 'unique-outlined-icon', 'rimmed-notification')
    # Exact Run20 index2 initial highlight and subsequent attempt to revisit it.
    initial = BoundingBox(127, 1173, 144, 100)
    first = Control('next-tab', BoundingBox(325, 1193, 67, 79), evidence, 'tab')
    revisit = Control('initial-tab', BoundingBox(157, 1192, 94, 83), evidence, 'tab')
    independent = replace(first, identity='independent', box=BoundingBox(489, 1190, 63, 82))
    p = Port([frame('home', 0, [root, other]),
        frame('page-a', 1, [first], parent=back, selected_tabs=(initial,)),
        frame('page-b', 2, [revisit, independent], parent=back),
        frame('page-c', 3, [], parent=back), frame('home', 4, [root, other]),
        frame('other-page', 5, [revisit], parent=back),
        frame('other-tab', 6, [], parent=back), frame('home', 7, [root, other])])
    result = DynamicEventExplorer().run(p)
    assert result.result == 'SUCCESS'
    assert [c[2] for c in p.calls if c[1] == 'tab'] == ['next-tab', 'independent', 'initial-tab']
    assert not result.rewards

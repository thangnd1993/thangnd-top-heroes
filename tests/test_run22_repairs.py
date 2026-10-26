"""Run22 repairs: Back-only exit from an unrecognised Event child page, and un-owned Monthly card."""
from dataclasses import replace

import pytest
from test_complete_repair import capture
from test_dynamic_events import BOX, Port, control, frame

from top_heroes_auto.app.dynamic_event_port import UNQUALIFIED_CHILD_PAGE, unqualified_child_exit
from top_heroes_auto.automation.dynamic_events import DynamicEventExplorer
from top_heroes_auto.vision.fixed_rewards import MONTHLY_DAILY, EventNavigationDetector, FixedRewardDetector
from top_heroes_auto.vision.models import BoundingBox

# Production run22 #2 evidence: gallery parent Back (34,1209) and child-page Back (35,1209).
PARENT_BACK = BoundingBox(34, 1209, 52, 47)
CHILD_BACK = BoundingBox(35, 1209, 52, 47)


def gallery(**kw):
    back = control('current-back', 'parent')
    return replace(frame('event:season:gallery', 'g', [control('c1')], parent=replace(back, box=PARENT_BACK)), **kw)


def exit_for(origin=None, back=CHILD_BACK, **kw):
    args = dict(page='UNKNOWN', entered='season', popup=False, dialog=None, rendering=False)
    args.update(kw)
    return unqualified_child_exit(gallery() if origin is None else origin, back, **args)


def test_unknown_child_page_gets_only_the_parents_back():
    exit_control = exit_for()
    assert exit_control.kind == 'parent' and exit_control.identity == 'current-back'
    assert exit_control.box == CHILD_BACK
    assert 'unqualified-child-exit-only' in exit_control.evidence


@pytest.mark.parametrize('change', [
    dict(page='event:season:known'), dict(entered=None), dict(popup=True), dict(dialog={'reason': 'X'}),
    dict(rendering=True), dict(back=None), dict(back=replace(CHILD_BACK, x=CHILD_BACK.x+30)),
    dict(back=replace(CHILD_BACK, y=CHILD_BACK.y-200)), dict(back=replace(CHILD_BACK, width=90)),
])
def test_exit_requires_every_condition(change):
    assert exit_for(**change) is None


@pytest.mark.parametrize('origin', ['none', 'home', 'popup', 'no-parent', 'other-parent', 'nested'])
def test_exit_requires_a_qualified_event_origin(origin):
    base = gallery()
    bad = dict(home=replace(base, page='home'), popup=replace(base, popup=True),
               nested=replace(base, page='event:season:unqualified-child'))
    bad['no-parent'] = replace(base, parent=None)
    bad['other-parent'] = replace(base, parent=replace(base.parent, identity='current-paid-modal-close'))
    if origin == 'none':
        assert unqualified_child_exit(None, CHILD_BACK, page='UNKNOWN', entered='season', popup=False,
                                      dialog=None, rendering=False) is None
    else:
        assert exit_for(bad[origin]) is None


@pytest.mark.parametrize('child', ['event-unqualified-child', 'event-unqualified-child-3'])
def test_real_run22_child_pages_keep_the_gallery_back_position(child):
    detector = EventNavigationDetector()
    parent = detector.observe(capture('run22/event-season-gallery')).box('back')
    current = detector.observe(capture('run22/'+child)).box('back')
    assert parent is not None and current is not None
    origin = gallery(parent=replace(control('current-back', 'parent'), box=parent))
    assert exit_for(origin, back=current) is not None


def unqualified(n, back):
    return replace(frame('event:season:unqualified-child', n, [], parent=back),
                   coverage_known=False, blocked=('EVENT_CONTENT_REQUIRES_QUALIFICATION', UNQUALIFIED_CHILD_PAGE))


def test_run22_traversal_leaves_unknown_child_and_visits_the_other_events():
    first, second = control('season', 'event'), replace(control('treasure', 'event'), box=replace(BOX, x=200))
    child1, child2 = control('card-1'), replace(control('card-2'), box=replace(BOX, y=300))
    back = control('current-back', 'parent')
    reward = control('free', 'reward', cost='FREE', available=True)
    p = Port([
        frame('home', 0, [first, second]),
        frame('event:season', 1, [child1, child2], parent=back),
        unqualified(2, back),                                   # run22 "Tháp Đuốc" page
        frame('event:season', 3, [child1, child2], parent=back),
        frame('event:season:card-2', 4, [], parent=back),
        frame('event:season', 5, [child1, child2], parent=back),
        frame('home', 6, [first, second]),
        frame('event:treasure', 7, [reward], parent=back),
        frame('event:treasure', 8, [], parent=back),
        frame('home', 9, [first, second]),
    ])
    result = DynamicEventExplorer().run(p)
    assert ('event:season:unqualified-child', 'parent', 'current-back', BOX.center) in p.calls
    assert not any(call[0] == 'event:season:unqualified-child' and call[1] != 'parent' for call in p.calls)
    assert any(call[1] == 'event' and call[2] == 'treasure' for call in p.calls)
    assert any(call[1] == 'reward' and call[2] == 'free' for call in p.calls)
    assert result.events['season']['result'] == 'BLOCKED'  # recorded, never exhausted
    assert result.events['treasure']['result'] == 'EXHAUSTED'
    assert UNQUALIFIED_CHILD_PAGE in {b['reason'] for b in result.blocked}
    assert result.result == 'BLOCKED'


def test_exit_flag_without_a_child_edge_stays_unknown():
    event, back = control('season', 'event'), control('current-back', 'parent')
    p = Port([frame('home', 0, [event]), unqualified(1, back)])
    result = DynamicEventExplorer().run(p)
    assert [c[1] for c in p.calls] == ['event']  # no Back on a page not entered from a qualified child edge
    assert result.blocked[0]['reason'] == 'UNKNOWN_SCREEN'


def production_port(tmp_path, monkeypatch, origin):
    """Real DynamicEventPort.observe on the run22 #2 child-page screenshot (no device)."""
    from pathlib import Path
    from types import SimpleNamespace

    import cv2

    from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
    from top_heroes_auto.vision.models import ScreenState

    raw = cv2.imread(str(Path(__file__).parent/'fixtures/run22/event-unqualified-child.png'))
    im = cv2.rotate(raw, cv2.ROTATE_90_COUNTERCLOCKWISE)
    captured = SimpleNamespace(index=13, name='fixture', serial='explicit', boot_id='boot',
                               source_image=tmp_path/'current.png', original=im, rotated_from_portrait=False)
    observed = SimpleNamespace(captured=captured, page='UNKNOWN', box=lambda role: CHILD_BACK if role == 'back' else None,
                               overlay=SimpleNamespace(state=ScreenState.UNKNOWN), evidence=lambda: {'state': 'UNKNOWN'})
    p = DynamicEventPort.__new__(DynamicEventPort)
    p.current, p.entered, p.rows = None, 'season', ()
    p.home_icon_cores, p.menu_icon_cores, p.pending_claim_ids, p.unavailable_observations = {}, {}, set(), {}
    p.child_origin = origin
    p.task_context = cv2.imread('assets/tasks/phase8/personal-task-tab.png')
    p.session = SimpleNamespace(index=13, target={'persistent_identity': 'disk'},
        manager=SimpleNamespace(namespace='fixture', store=SimpleNamespace(reward_claims=lambda *a: ())))
    sent = []
    p.transport = SimpleNamespace(observe=lambda: observed, last=observed, dispatch=lambda *a: sent.append(a))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.read_words', lambda _: [])
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep', lambda _: None)
    return p, sent


def test_production_port_offers_one_back_after_a_child_edge(tmp_path, monkeypatch):
    p, sent = production_port(tmp_path, monkeypatch, gallery())
    current = p.observe()
    assert current.page == 'event:season:unqualified-child' and not current.coverage_known
    assert current.controls == () and current.parent.box == CHILD_BACK
    assert UNQUALIFIED_CHILD_PAGE in current.blocked and not sent
    p.navigate(current, current.parent)
    assert len(sent) == 1 and sent[0][1:] == ('tap', CHILD_BACK.center)
    assert p.child_origin is None  # one-shot: consumed by the observation
    assert p.observe().page == 'UNKNOWN'  # a second capture without a new child edge stays UNKNOWN


def test_production_port_without_child_origin_stays_unknown(tmp_path, monkeypatch):
    p, sent = production_port(tmp_path, monkeypatch, None)
    current = p.observe()
    assert current.page == 'UNKNOWN' and current.parent is None and not sent


@pytest.fixture(scope='module')
def detector():
    return FixedRewardDetector()


def test_unowned_monthly_card_is_not_available_not_unknown(detector):
    frame_ = detector.observe(capture('run22/shop-monthly-unowned'))
    state, evidence, _ = detector.availability(frame_, MONTHLY_DAILY)
    assert state == 'NOT_AVAILABLE' and evidence.anchor_id == 'monthly-unowned-label'


@pytest.mark.parametrize('name,expected', [('phase7_resume/shop-monthly-owned', 'AVAILABLE'),
                                           ('phase6_finalization/monthly-daily-received', 'NOT_AVAILABLE')])
def test_owned_monthly_states_unchanged(detector, name, expected):
    frame_ = detector.observe(capture(name))
    assert detector.availability(frame_, MONTHLY_DAILY)[0] == expected
    assert not frame_.anchors['monthly-unowned-label'].matched


def test_unowned_label_with_a_claim_or_owned_label_is_unknown(detector):
    frame_ = detector.observe(capture('run22/shop-monthly-unowned'))
    anchors = dict(frame_.anchors)
    anchors['monthly-owned-label'] = replace(anchors['monthly-owned-label'], matched=True, score=.99)
    assert detector.availability(replace(frame_, anchors=anchors), MONTHLY_DAILY)[0] == 'UNKNOWN'
    anchors = dict(frame_.anchors)
    anchors['monthly-daily-claim'] = replace(anchors['monthly-daily-claim'], score=.99)
    assert detector.availability(replace(frame_, anchors=anchors), MONTHLY_DAILY)[0] == 'UNKNOWN'

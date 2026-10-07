"""Real jitter pair and navigation-only safety boundaries."""
from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from top_heroes_auto.app.dynamic_event_port import DynamicEventPort
from top_heroes_auto.automation.dynamic_events import Control, EventEntryUnstable, EventFrame, free_geometry
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.dynamic_events import icon_core_key
from top_heroes_auto.vision.event_reacquisition import stable_entry_match
from top_heroes_auto.vision.models import BoundingBox

OLD = BoundingBox(624, 285, 75, 75)
NEW = BoundingBox(624, 288, 75, 72)


def frames():
    return [cv2.imread(f'tests/fixtures/phase8/home-entry-jitter-{v}.png') for v in 'ab']


def test_real_pair_changes_hash_but_has_distributed_stable_artwork():
    a, b = frames()
    assert icon_core_key(a, OLD) != icon_core_key(b, NEW)
    assert stable_entry_match(a, OLD, b, NEW)
    # Match is independent of account and absolute coordinates.
    a = cv2.warpAffine(a, np.float32([[1, 0, -110], [0, 1, 70]]), (720, 1280))
    b = cv2.warpAffine(b, np.float32([[1, 0, -110], [0, 1, 70]]), (720, 1280))
    assert stable_entry_match(a, replace(OLD, x=514, y=355), b, replace(NEW, x=514, y=358))


def test_same_position_different_icon_and_badge_only_rejected():
    a, b = frames()
    b[288:360, 624:699] = cv2.resize(b[99:168, 626:703], (75, 72))
    assert not stable_entry_match(a, OLD, b, NEW)
    b[288:360, 624:699] = 40
    b[288:308, 679:699] = a[285:305, 679:699]
    assert not stable_entry_match(a, OLD, b, NEW)


def port_for(monkeypatch, tmp_path, *, controls=None, popup=False, page='home', runtime=None):
    a, b = frames()
    old = Control('old-hash', OLD, ('home', 'cluster', 'badge'), 'event')
    new = Control('new-hash', NEW, old.evidence, 'event')
    runtime = runtime or (3, 'disk', 'explicit', 'boot')
    before = EventFrame('old', (3, 'disk', 'explicit', 'boot'), 'home', 'a', (old,),
                        stable_id='disk', event_scan_performed=True)
    fresh = replace(before, capture='fresh', fingerprint='b', controls=controls or (new,),
                    popup=popup, page=page, identity=runtime)
    p = object.__new__(DynamicEventPort)
    p.current, p.entered, p.folder = before, None, tmp_path
    p.navigation_image = a
    sent, observations = [], []
    observation = object()
    p.transport = SimpleNamespace(last=observation, dispatch=lambda *args: sent.append(args))

    def observe():
        observations.append(1)
        p.navigation_image, p.current = b, fresh
        return fresh

    p.observe = observe
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.time.sleep', lambda _: None)
    return p, before, old, sent, observations, observation


def test_actual_navigation_uses_latest_box_without_reward_permission(monkeypatch, tmp_path):
    p, before, old, sent, observations, observation = port_for(monkeypatch, tmp_path)
    p.navigate(before, old)
    assert sent == [(observation, 'tap', NEW.center)]
    assert len(observations) == 1
    assert p.current is None and p.entered == old.identity
    assert (tmp_path/'entry-reacquisition.jsonl').exists()
    # Navigation does not confer any free-reward authorization.
    with pytest.raises(SafetyError):
        free_geometry(old)
    with pytest.raises(SafetyError):
        p.navigate(before, old)
    assert len(sent) == 1


@pytest.mark.parametrize('kwargs', [dict(popup=True), dict(page='UNKNOWN'), dict(page='event:new'),
                                  dict(runtime=(3, 'disk', 'explicit', 'new-boot'))])
def test_overlay_transition_runtime_prevent_input(monkeypatch, tmp_path, kwargs):
    p, frame, control, sent, _, _ = port_for(monkeypatch, tmp_path, **kwargs)
    with pytest.raises(SafetyError):
        p.navigate(frame, control)
    assert not sent


def test_duplicate_candidates_terminate_without_dispatch_or_reservation(monkeypatch, tmp_path):
    controls = tuple(Control(str(i), NEW, ('context',), 'event') for i in range(2))
    p, frame, control, sent, observed, _ = port_for(monkeypatch, tmp_path, controls=controls)
    with pytest.raises(EventEntryUnstable):
        p.navigate(frame, control)
    assert len(observed) == 3 and not sent
    assert list(tmp_path.iterdir()) == []


def test_filtered_ambiguous_core_cannot_leave_false_unique_candidate(monkeypatch,tmp_path):
    p, frame, old, sent, calls, _ = port_for(monkeypatch,tmp_path)
    observe=p.observe
    p.observe=lambda: replace(observe(),blocked=('AMBIGUOUS_ICON_CORE',))
    with pytest.raises(EventEntryUnstable):
        p.navigate(frame,old)
    assert len(calls)==3 and not sent


def test_paid_and_ambiguous_claim_guards_unchanged():
    for cost in ('UNKNOWN', 'VND', 'DIAMONDS'):
        c = Control('reward', NEW, ('a', 'b', 'c'), 'reward', cost, True)
        with pytest.raises(SafetyError):
            free_geometry(c)
    c = Control('reward', NEW, ('a', 'b', 'c'), 'reward', 'FREE', True, forbidden=(NEW,))
    with pytest.raises(SafetyError):
        free_geometry(c)


def test_similar_neighbor_is_ambiguous_even_when_geometry_prefers_original(monkeypatch, tmp_path):
    adjacent = replace(NEW, x=530)
    controls = (Control('one',NEW,('context',),'event'), Control('two',adjacent,('context',),'event'))
    p, frame, old, sent, calls, _ = port_for(monkeypatch,tmp_path,controls=controls)
    original_observe = p.observe
    def observe():
        result = original_observe()
        p.navigation_image[adjacent.y:adjacent.y+adjacent.height, adjacent.x:adjacent.x+adjacent.width] = (
            p.navigation_image[NEW.y:NEW.y+NEW.height, NEW.x:NEW.x+NEW.width].copy())
        return result
    p.observe = observe
    with pytest.raises(EventEntryUnstable):
        p.navigate(frame,old)
    assert len(calls)==3 and not sent


def test_portrait_device_tap_overlay_matches_rotated_capture(tmp_path):
    from top_heroes_auto.vision.debug import write_device_tap
    from top_heroes_auto.vision.guild_mail import portrait

    _, latest = frames()
    captured = SimpleNamespace(original=cv2.rotate(latest,cv2.ROTATE_90_CLOCKWISE),
                               rotated_from_portrait=True,device_size=(720,1280))
    assert np.array_equal(portrait(captured),latest)
    path=tmp_path/'tap.png'
    write_device_tap(captured,NEW.center,path)
    result=cv2.imread(str(path))
    assert result.shape==latest.shape
    x,y=NEW.center
    assert tuple(result[y,x])==(0,0,255)
    with pytest.raises(ValueError):
        write_device_tap(captured,(1280,720),path)

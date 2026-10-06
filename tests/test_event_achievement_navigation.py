"""Saved production gap: qualified nested trophy entry, never a reward tap."""
from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.vision.dynamic_events import achievement_navigation
from top_heroes_auto.vision.models import BoundingBox, CapturedScreen


def image():
    return cv2.imread('tests/fixtures/phase8/event-achievements-entry.png')


def test_saved_nested_entry_is_navigation_only_and_moves_with_frame():
    im = image()
    nav = achievement_navigation(im)
    assert nav['box'] == BoundingBox(637, 218, 33, 27)
    assert nav['badge'].rim_confidence >= .45
    assert 'navigation-only' in nav['evidence']
    tile = im[195:285, 600:710].copy()
    im[195:285, 600:710] = 0
    im[395:485, 450:560] = tile
    assert achievement_navigation(im)['box'] == BoundingBox(487, 418, 33, 27)


@pytest.mark.parametrize('mode', ['core', 'label', 'badge', 'duplicate', 'unrelated-badge'])
def test_missing_ambiguous_or_unowned_evidence_has_no_permission(mode):
    im = image()
    if mode == 'duplicate':
        im[500:527, 100:133] = im[218:245, 637:670]
    else:
        x, y, w, h = {'core': (637, 218, 33, 27), 'label': (604, 256, 99, 23),
                     'badge': (666, 199, 22, 22), 'unrelated-badge': (666, 199, 22, 22)}[mode]
        patch = im[y:y+h, x:x+w].copy()
        im[y:y+h, x:x+w] = 0
        if mode == 'unrelated-badge':
            im[500:500+h, 100:100+w] = patch
    assert achievement_navigation(im) is None


def test_exact_device_tap_overlay_uses_current_capture(tmp_path):
    im = image()
    original = cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE)
    captured = CapturedScreen(3, 'display', 'explicit', 'boot', original, original,
                              (1280, 720), (1280, 720), (1, 1), tmp_path/'clean.png',
                              device_size=(720, 1280), rotated_from_portrait=True)
    owner = object.__new__(FixedRewardPort)
    path = owner.save_tap_geometry(captured, (653, 231))
    saved = cv2.imread(path)
    assert saved.shape == im.shape
    assert tuple(saved[231, 653]) == (0, 0, 255)
    assert (captured.original == original).all()
    assert Path(path).exists()
    with pytest.raises(ValueError):
        owner.save_tap_geometry(replace(captured, device_size=(1280, 720)), (653, 231))


def test_production_adapter_exposes_nested_edge_without_claim_permission(tmp_path, monkeypatch):
    from test_event_paid_modal import port

    p, sent = port(tmp_path, monkeypatch)
    observed = p.transport.observe()
    observed.captured.original = image()
    shell = dict(title='fixture-title', page='event:fixture:body', selected=[], tabs=[],
                 back=BoundingBox(34, 1209, 52, 47))
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.event_shell', lambda *a, **kw: shell)
    observed.box = lambda role: shell['back'] if role == 'back' else None
    p.transport.last = observed
    frame = p.observe()
    assert not frame.coverage_known
    assert 'EVENT_CONTENT_REQUIRES_QUALIFICATION' in frame.blocked
    edge, = [c for c in frame.controls if c.identity == 'functional-achievements']
    assert edge.kind == 'child' and edge.cost == 'UNKNOWN' and not edge.available
    assert not [c for c in frame.controls if c.kind == 'reward']
    p.navigate(frame, edge)
    assert len(sent) == 1 and sent[0][1:] == ('tap', (653, 231))

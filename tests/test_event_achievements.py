"""Real achievement card schema and independent underlying claim state."""
from dataclasses import replace

import cv2
import pytest

from top_heroes_auto.vision.event_achievements import achievement_rows, achievement_shell
from top_heroes_auto.vision.models import BoundingBox


def image():
    return cv2.imread('tests/fixtures/phase8/achievement-rewards.png')


def rows(im, text='Nhan'):
    shell = achievement_shell(im)
    return achievement_rows(im, shell, reader=lambda _: [{'text': text}]) if shell else ()


def claimed_image():
    im = image()
    # Synthetic post-state from an actual claimed sibling: offline regression,
    # never proof that the real first-row reward has been dispatched/received.
    im[190:301, 472:654] = im[545:656, 472:654]
    return im


def test_actual_available_unmet_and_claimed_rows_are_distinct():
    found = rows(image())
    assert len(found) == 5
    assert [r['state'] for r in found] == ['AVAILABLE'] + ['NOT_AVAILABLE']*4
    assert found[0]['box'] == BoundingBox(472, 206, 179, 73)
    assert 'unmet-achievement' in found[1]['evidence']
    assert 'explicit-claimed-label' not in found[1]['evidence']
    assert all('explicit-claimed-label' in r['evidence'] for r in found[2:])


def test_underlying_claimed_state_preserves_reward_identity():
    before, after = rows(image())[0], rows(claimed_image())[0]
    assert before['identity'] == after['identity']
    assert after['state'] == 'NOT_AVAILABLE'
    assert {'explicit-claimed-label', 'original-green-control-absent'} <= set(after['evidence'])


@pytest.mark.parametrize('text', ['Nhan 10', 'Mua', 'VND', 'Nhan 0', 'Unknown'])
def test_price_extra_text_or_ambiguous_label_cannot_authorize_claim(text):
    assert rows(image(), text)[0]['state'] == 'UNKNOWN'


@pytest.mark.parametrize('role', ['title', 'close', 'claim', 'items'])
def test_missing_required_visual_evidence_cannot_claim(role):
    im = image()
    box = {'title': (289, 62, 141, 35), 'close': (341, 1151, 37, 35),
           'claim': (531, 237, 64, 28), 'items': (72, 198, 390, 94)}[role]
    x, y, w, h = box
    im[y:y+h, x:x+w] = 40
    assert not any(r['state'] == 'AVAILABLE' for r in rows(im))


def test_moved_modal_has_current_boxes_and_unrelated_frames_have_no_shell():
    im = image()
    moved = cv2.warpAffine(im, __import__('numpy').float32([[1, 0, -8], [0, 1, 10]]), (720, 1280))
    assert rows(moved)[0]['box'] == BoundingBox(464, 216, 179, 73)
    for name in ('paid-offer-one', 'event-achievements-entry', 'task-grid-partial-free'):
        assert achievement_shell(cv2.imread('tests/fixtures/phase8/'+name+'.png')) is None


def production_port(tmp_path, monkeypatch, im):
    from test_event_paid_modal import port

    p, sent = port(tmp_path, monkeypatch)
    p.transport.observe().captured.original = im
    monkeypatch.setattr('top_heroes_auto.app.dynamic_event_port.read_words', lambda _: [{'text': 'Nhan'}])
    return p, sent


def test_actual_production_adapter_exposes_one_free_reward_and_current_close(tmp_path, monkeypatch):
    p, sent = production_port(tmp_path, monkeypatch, image())
    frame = p.observe()
    rewards = [c for c in frame.controls if c.kind == 'reward']
    assert frame.page.endswith(':achievement-cards') and frame.coverage_known
    assert len(rewards) == 1 and rewards[0].available and rewards[0].cost == 'FREE'
    assert frame.parent.box == BoundingBox(341, 1151, 37, 35)
    assert not sent


def test_postcondition_requires_two_changed_underlying_frames(tmp_path, monkeypatch):
    p, _ = production_port(tmp_path, monkeypatch, image())
    before = p.observe()
    target = next(c for c in before.controls if c.kind == 'reward')
    assert p._claim_postcondition(before, target, 'achievements') == []  # Still green.
    p.transport.observe().captured.original = claimed_image()
    original = p.observe
    count = 0
    def fresh():
        nonlocal count
        count += 1
        return replace(original(), capture=str(tmp_path/f'after-{count}.png'))
    p.observe = fresh
    proof = p._claim_postcondition(before, target, 'achievements')
    assert len(proof) == 2 and len({q['capture'] for q in proof}) == 2
    assert all('explicit-claimed-label' in q['independent_evidence'] for q in proof)


@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows OCR')
def test_real_ocr_reads_only_free_claim_label():
    from top_heroes_auto.vision.local_ocr import read_words

    im = image()
    assert achievement_rows(im, achievement_shell(im), reader=read_words)[0]['state'] == 'AVAILABLE'


def test_saved_achievement_identity_keeps_possible_lock_and_duplicate_fails_closed(tmp_path):
    import json

    from top_heroes_auto.app.event_claim_reconciliation import bind_saved_rewards

    im = image()
    original = rows(im)[0]
    source = tmp_path/'before.png'
    source.write_bytes(cv2.imencode('.png', im)[1].tobytes())
    source.with_suffix('.event.json').write_text(json.dumps({'reward_rows': [
        {**original, 'row': vars(original['row']), 'box': vars(original['box'])}]}))
    claim = dict(reward_id='event:fixture', dispatch_state='POSSIBLE', before_evidence=json.dumps(dict(
        page='event:achievements:achievement-cards', reward=original['identity'], capture=str(source),
        identity=[13, 'disk', 'explicit', 'boot'], persistent_identity='disk')))
    current = dict(original, identity='changed-raster')
    bound = bind_saved_rewards(im, [current], [claim], persistent_identity='disk', index=13,
                               family='achievement-cards')
    assert bound[0]['identity'] == original['identity']
    ambiguous = bind_saved_rewards(im, [current, dict(current)], [claim], persistent_identity='disk',
                                   index=13, family='achievement-cards')
    assert all(r['state'] == 'UNKNOWN' for r in ambiguous)


def test_unknown_paid_icon_and_unmet_state_do_not_verify_a_claim(tmp_path, monkeypatch):
    im = image()
    cv2.rectangle(im, (488, 225), (515, 258), (255, 80, 10), -1)
    assert rows(im)[0]['state'] == 'UNKNOWN'
    p, _ = production_port(tmp_path, monkeypatch, image())
    before = p.observe()
    target = next(c for c in before.controls if c.kind == 'reward')
    underlying = image()
    underlying[190:301, 472:654] = underlying[367:478, 472:654]
    p.transport.observe().captured.original = underlying
    assert p._claim_postcondition(before, target, 'achievements') == []

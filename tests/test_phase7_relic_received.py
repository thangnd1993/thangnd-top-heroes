"""Positive gray Relic post-state from original one-shot action125."""
from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.vision.guild_mail import GuildMailDetector
from top_heroes_auto.vision.screenshot import ScreenshotService

ROOT = Path(__file__).parent/'fixtures/phase7'


def capture(name):
    return ScreenshotService(lambda _:(ROOT/f'{name}.png').read_bytes()).take(Target(19,'offline-relic','explicit','boot'))


@pytest.fixture(scope='module')
def evidence():
    detector = GuildMailDetector(number_reader=lambda *a,**kw:None)
    frames = {name:detector.observe(capture(name)) for name in
              ('relic-live-before','relic-received-1','relic-received-2')}
    return detector,frames


def test_actual_gift_changes_from_badged_available_to_gray_unavailable(evidence):
    detector,frames = evidence
    assert detector.availability(frames['relic-live-before'],'guild-relic').state == 'AVAILABLE'
    for name in ('relic-received-1','relic-received-2'):
        frame = frames[name]
        assert frame.page == 'relic'
        assert frame.anchors['relic-gift-unavailable'].score >= .98
        view = detector.availability(frame,'guild-relic')
        assert view.state == 'NOT_AVAILABLE' and view.remaining == 0


@pytest.mark.parametrize('mutation',['missing_title','missing_gift','duplicate_gift','active_conflict'])
def test_incomplete_or_conflicting_gray_evidence_is_not_exhaustion(evidence,mutation):
    detector,frames = evidence
    frame = frames['relic-received-1']
    pixels = frame.captured.normalized.copy()
    role = 'territory-title' if mutation == 'missing_title' else 'relic-gift-unavailable'
    box = frame.anchors[role].normalized_box
    if mutation.startswith('missing'):
        pixels[box.y:box.y+box.height,box.x:box.x+box.width] = 0
    else:
        patch = pixels[box.y:box.y+box.height,box.x:box.x+box.width].copy()
        if mutation == 'active_conflict':
            patch = detector.templates['relic-gift']
        h,w = patch.shape[:2]
        pixels[300:300+h,500:500+w] = patch
    current = detector.observe(replace(frame.captured,normalized=pixels))
    assert detector.availability(current,'guild-relic').state == 'UNKNOWN'


def test_gray_gift_detection_uses_current_shifted_bbox(evidence):
    detector,frames = evidence
    frame = frames['relic-received-1']
    matrix = cv2.getRotationMatrix2D((0,0),0,1)
    matrix[:,2] = -30,-20
    pixels = cv2.warpAffine(frame.captured.normalized,matrix,frame.captured.normalized_size)
    moved = detector.observe(replace(frame.captured,normalized=pixels))
    a,b = frame.anchors['relic-gift-unavailable'],moved.anchors['relic-gift-unavailable']
    assert b.matched
    assert (b.normalized_box.x-a.normalized_box.x,b.normalized_box.y-a.normalized_box.y) == (-30,-20)


def test_badge_one_is_a_complete_local_badge_not_part_of_ten():
    detector = GuildMailDetector(number_reader=lambda *a,**kw:None)
    one = detector.observe(capture('mail-system-one'))
    ten = detector.observe(capture('mail-live'))
    assert detector.mail_tabs(one)['system']['count'] == 1
    assert detector.mail_tabs(ten)['system']['count'] is None


@pytest.mark.parametrize('case',['verified','possible','old_period','wrong_identity','protected','dynamic'])
def test_relic_completion_is_current_period_only_and_needs_no_navigation(rig,case):
    import json
    from types import SimpleNamespace

    from top_heroes_auto.app.flow_registry import production_registry
    from top_heroes_auto.automation.guild_mail_claims import relic_cycle

    relic_completed = next(f.completed for f in production_registry().snapshot() if f.id == 'guild')
    manager,_,store = rig
    task = store.create_task_run(manager.namespace,'guild',7,'Farm-007')
    reward = 'guild-gifts-loot' if case == 'dynamic' else 'guild-relic'
    period = 'guild-relic:old' if case == 'old_period' else relic_cycle()
    claim = store.reserve_reward_claim(task,reward,period,json.dumps(dict(persistent_identity='disk')),
                                      expected_instance=(7,'Farm-007'),not_dispatched=True)
    store.mark_reward_dispatch(claim,task)
    if case != 'possible':
        store.verify_reward_claim(claim,task,'{}')
    if case == 'protected':
        store.protect(manager.namespace,7,True)
    session = SimpleNamespace(manager=manager,index=7,name='Farm-007',target=dict(
        persistent_identity='other' if case == 'wrong_identity' else 'disk'))
    if case == 'protected':
        with pytest.raises(Exception,match='Protected'):
            relic_completed(session,('guild-relic',reward))
    else:
        result = relic_completed(session,('guild-relic',reward))
        assert bool(result) is (case == 'verified')
        if result:
            assert result['guild-relic']['claim_dispatched'] is False

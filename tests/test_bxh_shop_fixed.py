import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app import bxh_shop_acceptance as fleet
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.automation.fixed_reward_claims import process_reward
from top_heroes_auto.automation.fixed_reward_period import current_attempts, cycle_key
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.storage.store import Store
from top_heroes_auto.vision.fixed_rewards import REWARDS, FixedRewardDetector, claim_geometry
from top_heroes_auto.vision.screenshot import ScreenshotService

ASSETS = Path(__file__).parents[1] / 'assets/tasks/phase6/fixed-rewards'


def paste(image, name, x, y):
    crop = cv2.imread(str(ASSETS / f'{name}.png'))
    crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
    h, w = crop.shape[:2]
    image[y:y+h, x:x+w] = crop


def make_frame(reward, *, badge=True, offset=0, other_badge=False, duplicate=False,
               weak=False, capture='before', page=True, received=True):
    image = np.full((1280, 720, 3), (150, 120, 70), dtype=np.uint8)
    if reward == 'ranking-chest':
        if page:
            paste(image, 'ranking-title', 324, 115)
            paste(image, 'ranking-tab', 111, 223)
        x, y, core, attention, dx, dy = 110+offset, 119, 'ranking-chest', 'ranking-attention', 54, -15
    else:
        if page:
            paste(image, 'shop-title', 313, 25)
            paste(image, 'daily-title' if reward == 'shop-daily-gift' else 'weekly-title', 35, 136)
        x, y, core, attention, dx, dy = 606-offset, 231, 'shop-gift', 'shop-attention', 51, -17
    if reward != 'ranking-chest' and not badge and received and not (weak or duplicate):
        paste(image, 'daily-received' if reward == 'shop-daily-gift' else 'weekly-received', 592-offset, 212)
    else:
        paste(image, core, x, y)
    if badge:
        paste(image, attention, x+dx, y+dy)
    if other_badge:
        paste(image, attention, 30, 310)
    if duplicate:
        paste(image, core, 420, 310)
    if weak:
        image[y:y+30, x:x+30] = 0
    c = ScreenshotService(lambda _: cv2.imencode('.png', image)[1].tobytes()).take(
        Target(13, 'renamable', 'emulator-5580', 'same-boot'))
    return replace(c, source_image=Path(capture))


@pytest.fixture(scope='module')
def detector():
    return FixedRewardDetector()


@pytest.mark.parametrize('reward', REWARDS)
@pytest.mark.parametrize('offset', [0, 27])
def test_current_frame_available_inactive_and_geometry(detector, reward, offset):
    before = detector.observe(make_frame(reward, offset=offset))
    state, core, _ = detector.availability(before, reward)
    assert state == 'AVAILABLE'
    geometry = claim_geometry(before, reward, core)
    assert geometry['tap'] == list(core.device_box.center)
    assert geometry['outside_forbidden']
    after = detector.observe(make_frame(reward, badge=False, offset=offset))
    assert detector.availability(after, reward)[0] == 'NOT_AVAILABLE'


@pytest.mark.parametrize('reward', REWARDS)
@pytest.mark.parametrize('variant', ['duplicate', 'weak', 'missing_page', 'red_elsewhere'])
def test_ambiguous_and_unrelated_badge_never_enable_claim(detector, reward, variant):
    frame = make_frame(reward, badge=False, duplicate=variant == 'duplicate',
                       weak=variant == 'weak', page=variant != 'missing_page',
                       other_badge=variant == 'red_elsewhere')
    state = detector.availability(detector.observe(frame), reward)[0]
    assert state == ('NOT_AVAILABLE' if variant == 'red_elsewhere' else 'UNKNOWN')


@pytest.mark.parametrize('reward', REWARDS[1:])
def test_closed_gift_without_badge_is_not_independent_unavailable_proof(detector, reward):
    observed = detector.observe(make_frame(reward, badge=False, received=False))
    assert detector.availability(observed, reward)[0] == 'UNKNOWN'


def test_conflicting_active_and_received_gifts_fail_closed(detector):
    active = detector.observe(make_frame('shop-daily-gift'))
    inactive = detector.observe(make_frame('shop-daily-gift', badge=False))
    conflicting = replace(active, anchors={**active.anchors, 'daily-received': inactive.anchors['daily-received']})
    assert detector.availability(conflicting, 'shop-daily-gift')[0] == 'UNKNOWN'


def test_duplicate_page_variant_cannot_be_rescued_by_another_template(detector):
    frame = make_frame('shop-daily-gift')
    image = cv2.rotate(frame.normalized, cv2.ROTATE_90_COUNTERCLOCKWISE)
    paste(image, 'shop-title', 90, 35)
    paste(image, 'shop-title-reference', 450, 90)
    frame = ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(13,'x','s','b'))
    assert detector.observe(frame).page == 'UNKNOWN'


def test_ranking_positive_empty_slot_and_conflict(detector):
    frame = make_frame('ranking-chest')
    image = cv2.rotate(frame.normalized, cv2.ROTATE_90_COUNTERCLOCKWISE)
    paste(image, 'ranking-empty-slot', 85, 100)
    frame = ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(13,'x','s','b'))
    empty = detector.observe(frame)
    assert detector.availability(empty, 'ranking-chest')[0] == 'NOT_AVAILABLE'
    active = detector.observe(make_frame('ranking-chest'))
    mixed = replace(active, anchors={**active.anchors, 'ranking-empty-slot': empty.anchors['ranking-empty-slot']})
    assert detector.availability(mixed, 'ranking-chest')[0] == 'UNKNOWN'
    image[100:180, 85:200] = 0
    frame = ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(13,'x','s','b'))
    assert detector.availability(detector.observe(frame), 'ranking-chest')[0] == 'UNKNOWN'


@pytest.mark.parametrize('style', ['avatar', 'avatar-floral'])
def test_avatar_frame_ignores_portrait_pixels_and_rejects_duplicate(detector, style):
    template = cv2.imread(str(ASSETS/f'{style}-frame.png'))
    mask = cv2.imread(str(ASSETS/f'{style}-mask.png'), 0)
    template = cv2.rotate(template, cv2.ROTATE_90_COUNTERCLOCKWISE)
    mask = cv2.rotate(mask, cv2.ROTATE_90_COUNTERCLOCKWISE)
    h, w = mask.shape
    rng = np.random.default_rng(102)
    image = rng.integers(0, 255, (1280, 720, 3), dtype=np.uint8)
    for x in (20,):
        patch = image[66:66+h, x:x+w]
        patch[mask>0] = template[mask>0]
    frame = ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(13,'changed','serial','boot'))
    evidence = detector.avatar_frame(frame)
    assert evidence.matched and evidence.device_box.x == 20
    image = rng.integers(0, 255, (1280, 720, 3), dtype=np.uint8)
    for y in (10, 118):
        image[y:y+h, 20:20+w][mask>0] = template[mask>0]
    frame = ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(13,'changed','serial','boot'))
    assert not detector.avatar_frame(frame).matched


@pytest.mark.parametrize('after_kind', ['inactive', 'still_active', 'popup_only', 'exception'])
def test_one_shot_independent_postcondition_and_persistent_lock(tmp_path, detector, after_kind):
    store = Store(tmp_path / 'claims.sqlite3')
    before = detector.observe(make_frame('ranking-chest'))
    after = detector.observe(make_frame('ranking-chest', badge=after_kind != 'inactive',
                                       page=after_kind != 'popup_only', capture='after'))
    calls = []

    def tap(frame, anchor, before_input):
        assert store.reward_claims('namespace', 13)[0]['dispatch_state'] == 'NOT_DISPATCHED'
        before_input()
        assert store.reward_claims('namespace', 13)[0]['dispatch_state'] == 'POSSIBLE'
        calls.append('claim')
        if after_kind == 'exception':
            raise OSError('ADB outcome uncertain')

    port = SimpleNamespace(detector=detector, observe_settled=lambda: before,
                           tap=tap, observe=lambda: after, settle=lambda f: f,
                           save_geometry=lambda *a: None)
    task = store.create_task_run('namespace', 'bxh-shop-fixed', 13, 'renamable')
    report = {}
    try:
        process_reward(port, store, 'namespace', task, 'ranking-chest', 'disk', report, lambda: None)
    except OSError:
        assert after_kind == 'exception'
    assert calls == ['claim']
    assert report['journal'] == ('VERIFIED' if after_kind == 'inactive' else 'RESERVED')
    assert report['result'] == ('SUCCESS' if after_kind == 'inactive' else 'ACTION_DISPATCHED_UNVERIFIED')
    second = {}
    process_reward(port, store, 'namespace', task, 'ranking-chest', 'disk', second, lambda: None)
    assert calls == ['claim']
    assert second['result'] in {'ALREADY_VERIFIED', 'ALREADY_ATTEMPTED', 'STATE_CONFLICT'}


def test_three_rewards_independent_and_unavailable_does_not_reserve(tmp_path, detector):
    store = Store(tmp_path / 'claims.sqlite3')
    task = store.create_task_run('n', 'bxh-shop-fixed', 13, 'renamable')
    for reward in REWARDS:
        frame = detector.observe(make_frame(reward, badge=False))
        port = SimpleNamespace(detector=detector, observe_settled=lambda f=frame: f)
        report = {}
        process_reward(port, store, 'n', task, reward, 'disk', report, lambda: None)
        assert report['result'] == 'NOT_AVAILABLE'
    assert store.reward_claims('n', 13) == []
    for reward in REWARDS:
        store.reserve_reward_claim(task, reward, cycle_key(reward), '{}', fixed_reward_period=True)
    assert len(store.reward_claims('n', 13)) == 3


def test_actual_daily_period_preserves_old_receipt_but_not_new_period_lock():
    now = datetime(2026, 9, 24, 3, tzinfo=timezone.utc)
    rows = [dict(reward_id='shop-daily-gift', reserved_at=(now-timedelta(days=1)).isoformat(), status='VERIFIED')]
    assert current_attempts(rows, 'shop-daily-gift', now) == []
    assert rows[0]['status'] == 'VERIFIED'
    rows[0]['reserved_at'] = now.isoformat()
    assert current_attempts(rows, 'shop-daily-gift', now) == rows
    assert cycle_key('ranking-chest', now).endswith('2026-09-24T02:00:00+00:00')


def test_random_excludes_all_protected_no_fixed_index():
    rows = [dict(index=31, name='new A', protected=False), dict(index=40, name='new B', protected=False),
            dict(index=52, name='new C', protected=True), dict(index=0, name='Queen', protected=False)]
    selected, eligible = fleet.choose_random(rows, choice=lambda values: values[-1])
    assert [r['index'] for r in eligible] == [31, 40]
    assert selected['index'] == 40
    assert fleet.choose_random(rows, exclude=(40,))[0]['index'] == 31


def test_fleet_snapshot_complete_continues_after_failure(rig, tmp_path):
    manager, process, _ = rig
    process.listing += '13,another,0,0,0,-1,-1\n14,protected new,0,0,0,-1,-1\n'
    manager.refresh()
    manager.protect(14, True)
    calls = []

    def run(manager, data, target, folder):
        calls.append(target['index'])
        if target['index'] == 7:
            process.listing += '15,joined late,0,0,0,-1,-1\n'
            raise RuntimeError('first account failed')
        return dict(index=target['index'], result='COMPLETE', rewards={})

    result = fleet.run_acceptance(manager, tmp_path, account_runner=run, identity_reader=lambda *a: 'disk')
    assert calls == [7, 13]
    assert result['max_concurrency'] == 1
    assert result['result'] == 'PARTIAL'
    assert len(result['excluded_protected']) == 2


@pytest.mark.parametrize('protect', [False, True])
def test_selection_restore_and_new_protection_overrides_cleanup(rig, tmp_path, protect):
    manager, _, _ = rig
    manager.select(7, False)
    actions = []
    original = manager.execute

    def execute(index, action, **kwargs):
        actions.append(action)
        return original(index, action, **kwargs)

    manager.execute = execute

    class Port:
        events = []

        def __init__(self, *a):
            if protect:
                manager.protect(7, True)

        def home(self):
            raise SafetyError('unknown, no input')

    row = fleet.run_account(manager, tmp_path, dict(index=7, name='Farm-007'), tmp_path,
        port_factory=Port, identity_reader=lambda *a: 'disk',
        recovery_runner=lambda *a, **k: (RecoveryResult(RecoveryStatus.SUCCESS), tmp_path/'r.json', True))
    assert not manager.store.metadata(manager.namespace, 7).selected
    assert row['selection_restored']
    if protect:
        assert row['cleanup'].startswith('FAILED')
        assert manager.store.metadata(manager.namespace, 7).protected
    else:
        assert row['cleanup'] == 'SUCCESS'
    assert all(v['claim_dispatched'] is False for v in row['rewards'].values())


def test_forbidden_route_and_stale_frame_never_dispatch(rig, tmp_path, detector):
    manager, _, _ = rig
    port = FixedRewardPort(manager, RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True),
                           7, 'Farm-007', tmp_path)
    obs = detector.observe(make_frame('shop-daily-gift'))
    with pytest.raises(SafetyError, match='annotated'):
        port.navigate(obs, 'daily-pack-tab', 'paid-page')
    with pytest.raises(SafetyError, match='Forbidden'):
        port.find_tab(obs, 'diamond-store')
    with pytest.raises(SafetyError, match='Stale'):
        port.tap(obs, obs.anchors['shop-gift'])
    assert port.events == []


def test_allowed_tab_discovered_after_bounded_scroll(rig, tmp_path, detector):
    manager, _, _ = rig
    port = FixedRewardPort(manager, RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True),
                           7, 'Farm-007', tmp_path)
    image = make_frame('shop-daily-gift').normalized
    portrait = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    paste(portrait, 'back', 35, 1215)
    paste(portrait, 'weekly-tab', 560, 1219)
    c = ScreenshotService(lambda _: cv2.imencode('.png', portrait)[1].tobytes()).take(
        Target(7, 'Farm-007', 'emulator-5568', 'boot'))
    visible = detector.observe(c)
    hidden = replace(visible, anchors={**visible.anchors, 'weekly-tab': replace(
        visible.anchors['weekly-tab'], matched=False, device_box=None)})
    calls = []
    port.dispatch = lambda *args: calls.append(args[1])
    port.observe_settled = lambda: visible
    assert port.find_tab(hidden, 'weekly-tab') is visible
    assert calls == ['swipe']
    port.observe_settled = lambda: hidden
    with pytest.raises(SafetyError, match='TAB_NOT_FOUND'):
        port.find_tab(hidden, 'weekly-tab')
    assert calls == ['swipe']  # Account traversal retains visited tab-strip states.


def test_reused_disk_identity_cannot_unlock_claim(tmp_path, detector):
    import json

    store = Store(tmp_path/'claims.sqlite3')
    task = store.create_task_run('n', 'bxh-shop-fixed', 13, 'renamable')
    store.reserve_reward_claim(task, 'ranking-chest', cycle_key('ranking-chest'),
                               json.dumps({'persistent_identity': 'old-disk'}))
    before = detector.observe(make_frame('ranking-chest'))
    port = SimpleNamespace(detector=detector, observe_settled=lambda: before)
    result = {}
    process_reward(port, store, 'n', task, 'ranking-chest', 'new-disk', result, lambda: None)
    assert result['result'] == 'IDENTITY_CONTINUITY_UNPROVEN'
    assert len(store.reward_claims('n', 13)) == 1


def test_shop_remembered_allowed_tab_is_not_misreported_as_unknown(rig, tmp_path, detector):
    manager, _, _ = rig
    port = FixedRewardPort(manager, RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True),
                           7, 'Farm-007', tmp_path)
    weekly = detector.observe(make_frame('shop-weekly-card-gift'))
    home = replace(weekly, page='home', anchors={**weekly.anchors,
        'home-shop-entry': weekly.anchors['shop-gift']})
    port.tap = lambda *a: None
    port.observe_settled = lambda: weekly
    assert port.navigate(home, 'home-shop-entry', 'shop-daily') is weekly


def ranking_receipt_frame(*, missing=None, duplicate=False, wrong_layout=False):
    image = np.full((1280, 720, 3), (55, 42, 32), np.uint8)
    for name, (x, y) in {'title': (207, 279), 'gem': (326, 414), 'continue': (259, 916)}.items():
        if name == missing:
            continue
        crop = cv2.imread(str(ASSETS.parent/'overlays'/f'ranking-receipt-{name}.png'))
        crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
        h, w = crop.shape[:2]
        if wrong_layout and name == 'gem':
            y = 970
        image[y:y+h, x:x+w] = crop
        if duplicate and name == 'title':
            image[100:100+h, x:x+w] = crop
    return ScreenshotService(lambda _: cv2.imencode('.png', image)[1].tobytes()).take(
        Target(13, 'renamable', 'emulator-5580', 'same-boot'))


def shop_receipt_frame(*, missing=False, duplicate=False):
    image = np.full((1280, 720, 3), (55, 42, 32), np.uint8)
    for name, (x, y) in {'receipt-title': (205, 282), 'receipt-continue-dim': (258, 996)}.items():
        if missing and name == 'receipt-title':
            continue
        crop = cv2.imread(str(ASSETS.parent/'overlays'/f'{name}.png'))
        crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
        h, w = crop.shape[:2]
        image[y:y+h, x:x+w] = crop
        if duplicate and name == 'receipt-continue-dim':
            image[800:800+h, x:x+w] = crop
    return ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(
        Target(13, 'renamable', 'emulator-5580', 'same-boot'))


@pytest.mark.parametrize('variant', ['good', 'missing', 'duplicate'])
def test_dim_continue_requires_independent_title_and_unique_text(detector, variant):
    frame = shop_receipt_frame(missing=variant == 'missing', duplicate=variant == 'duplicate')
    assert (detector.recovery.detect(frame).state == 'REWARD_RECEIPT') == (variant == 'good')


@pytest.mark.parametrize('variant', ['good', 'missing_title', 'missing_gem', 'missing_continue', 'duplicate', 'wrong_layout'])
def test_ranking_receipt_three_anchors_and_layout(detector, variant):
    from top_heroes_auto.vision.models import ScreenState
    frame = ranking_receipt_frame(missing=variant.removeprefix('missing_'),
                                  duplicate=variant == 'duplicate', wrong_layout=variant == 'wrong_layout')
    found = detector.recovery.detect(frame)
    assert (found.state == ScreenState.REWARD_RECEIPT) == (variant == 'good')
    assert detector.availability(detector.observe(frame), 'ranking-chest')[0] == 'UNKNOWN'


def test_final_bounded_dismissal_always_captures_fresh_screen(rig, tmp_path, detector, monkeypatch):
    manager, _, _ = rig
    port = FixedRewardPort(manager, RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True),
                           7, 'Farm-007', tmp_path)
    receipt = detector.observe(ranking_receipt_frame())
    unknown = replace(receipt, overlay=replace(receipt.overlay, state='UNKNOWN'))
    final = detector.observe(make_frame('ranking-chest', badge=False))
    frames = iter([unknown, unknown, receipt, final])
    events = []
    port.observe = lambda: (events.append('capture'), next(frames))[1]
    port.dispatch = lambda *a: events.append('dismiss')
    monkeypatch.setattr('top_heroes_auto.app.fixed_reward_port.time.sleep', lambda _: None)
    assert port.settle(unknown) is final
    assert events == ['capture', 'capture', 'capture', 'dismiss', 'capture']


@pytest.mark.parametrize('outcome', ['unavailable', 'old_claim', 'still_active', 'popup_only', 'old', 'wrong_receipt', 'disk_changed'])
@pytest.mark.parametrize('reward_id', REWARDS)
def test_recent_dispatched_receipt_reconciles_without_second_claim(tmp_path, detector, outcome, reward_id):
    store = Store(tmp_path/'claim.sqlite3')
    target = Target(13, 'renamable', 'emulator-5580', 'same-boot')

    def saved(frame, tag):
        raw = cv2.rotate(frame.normalized, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return ScreenshotService(lambda _: cv2.imencode('.png', raw)[1].tobytes()).take(target, tmp_path, tag)

    before = detector.observe(saved(make_frame(reward_id), 'before'))
    popup_frame = ranking_receipt_frame(missing='gem' if outcome == 'wrong_receipt' else None) if reward_id == 'ranking-chest' else shop_receipt_frame(missing=outcome == 'wrong_receipt')
    popup = detector.observe(saved(popup_frame, 'receipt'))
    if outcome == 'old_claim':
        old = datetime.now(timezone.utc)-timedelta(hours=2)
        before = replace(before, captured=replace(before.captured, timestamp=old.isoformat()))
        popup = replace(popup, captured=replace(popup.captured, timestamp=(old+timedelta(seconds=10)).isoformat()))
    calls = []

    def tap(frame, anchor, before_input):
        before_input()
        calls.append('one original claim')

    port = SimpleNamespace(detector=detector, observe_settled=lambda: before, tap=tap,
                           observe=lambda: popup, settle=lambda f: f, save_geometry=lambda *a: None)
    task = store.create_task_run('n', 'bxh-shop-fixed', 13, target.name)
    report = dict(persistent_identity='disk', rewards={reward_id: {}})
    path = tmp_path/'account-report.json'
    def persist():
        path.write_text(json.dumps(report), encoding='utf-8')
    process_reward(port, store, 'n', task, reward_id, 'disk', report['rewards'][reward_id], persist)
    store.finish_task_run(task, 'PARTIAL', report_path=str(path))
    current = detector.observe(saved(make_frame(reward_id, badge=outcome == 'still_active'), 'current'))
    if outcome == 'popup_only':
        current = popup
    if outcome == 'old':
        current = replace(current, captured=replace(current.captured, timestamp=(
            datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()))
    port.observe_settled = lambda: current
    result = {}
    process_reward(port, store, 'n', task, reward_id, 'other' if outcome == 'disk_changed' else 'disk', result, lambda: None)
    assert calls == ['one original claim']
    row = store.reward_claims('n', 13)[0]
    assert row['status'] == ('VERIFIED' if outcome in {'unavailable', 'old_claim'} else 'RESERVED')
    if outcome in {'unavailable', 'old_claim'}:
        assert result['claim_dispatched'] is False
        assert result['reconciliation']['claim_redispatched'] is False


def test_resume_only_unfinished_rewards_and_original_snapshot(rig, tmp_path):
    manager, process, _ = rig
    process.listing += '13,newly discovered,0,0,0,-1,-1\n'
    before = fleet.inventory(manager)
    target = next(dict(r, persistent_identity='disk') for r in before if r['index'] == 7)
    previous = dict(mode='fleet', targets=[target], after_instances=before, accounts=[dict(
        index=7, name=target['name'], result='PARTIAL', rewards={
            'ranking-chest': {'result': 'ACTION_DISPATCHED_UNVERIFIED', 'journal': 'RESERVED'},
            'shop-daily-gift': {'result': 'NOT_AVAILABLE', 'journal': 'NONE'},
            'shop-weekly-card-gift': {'result': 'BLOCKED', 'journal': 'NONE'}})])
    path = tmp_path/'previous.json'
    path.write_text(json.dumps(previous), encoding='utf-8')
    calls = []

    def run(manager, data, target, folder, *, rewards):
        calls.append((target['index'], rewards))
        return dict(index=target['index'], result='COMPLETE', rewards={
            r: dict(result='NOT_AVAILABLE', journal='NONE') for r in rewards})

    report = fleet.run_acceptance(manager, tmp_path, resume_report=path, account_runner=run,
                                  identity_reader=lambda *a: 'disk')
    assert calls == [(7, ('ranking-chest', 'shop-weekly-card-gift'))]
    assert len(report['accounts']) == 1
    assert len(report['accounts'][0]['attempt_history']) == 1
    assert json.loads(path.read_text(encoding='utf-8')) == previous
    manager.protect(7, True)
    plan = fleet.resume_plan(previous, fleet.inventory(manager))
    assert 'identity_error' in plan[0][0]


@pytest.mark.parametrize('offset', [0, 24])
def test_weekly_clean_gift_variant_uses_current_geometry(detector, offset):
    image = cv2.rotate(make_frame('shop-weekly-card-gift', badge=False, page=True).normalized,
                       cv2.ROTATE_90_COUNTERCLOCKWISE)
    image[200:440, 580:720] = (150, 120, 70)
    paste(image, 'weekly-gift-core', 625-offset, 345)
    paste(image, 'weekly-gift-attention', 681-offset, 318)
    frame = ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(13,'different','s','b'))
    obs = detector.observe(frame)
    state, core, _ = detector.availability(obs, 'shop-weekly-card-gift')
    assert state == 'AVAILABLE'
    assert claim_geometry(obs, 'shop-weekly-card-gift', core)['tap'] == list(core.device_box.center)
    paste(image, 'weekly-gift-core', 420, 300)
    duplicate = ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(13,'different','s','b'))
    assert detector.availability(detector.observe(duplicate), 'shop-weekly-card-gift')[0] == 'UNKNOWN'


@pytest.mark.parametrize('persistent', [False, True])
def test_shop_announcement_is_observation_only_and_bounded(detector, monkeypatch, persistent):
    from top_heroes_auto.automation.fixed_reward_claims import observe_reward
    ready = detector.observe(make_frame('shop-daily-gift', badge=False))
    image = cv2.rotate(ready.captured.normalized, cv2.ROTATE_90_COUNTERCLOCKWISE)
    paste(image, 'shop-notice-speaker', 40, 239)
    c = ScreenshotService(lambda _:cv2.imencode('.png', image)[1].tobytes()).take(Target(13,'x','s','b'))
    covered = detector.observe(c)
    assert detector.availability(covered, 'shop-daily-gift')[0] == 'UNKNOWN'
    captures = []
    def observe():
        captures.append('capture')
        return covered if persistent else ready
    monkeypatch.setattr('top_heroes_auto.automation.fixed_reward_claims.time.sleep', lambda _: None)
    port = SimpleNamespace(detector=detector, observe_settled=observe)
    _, state, _, _ = observe_reward(port, covered, 'shop-daily-gift')
    assert state == ('UNKNOWN' if persistent else 'NOT_AVAILABLE')
    assert len(captures) == (4 if persistent else 1)


@pytest.mark.parametrize('missing', [None, 'blood-night-title', 'blood-night-started', 'blood-night-close', 'conflicting_receipt'])
def test_event_requires_three_stable_anchors_excluding_timer(detector, missing):
    from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
    image = np.full((1280, 720, 3), (20, 40, 35), np.uint8)
    for name, (x, y) in {'blood-night-title':(64,627), 'blood-night-started':(247,768), 'blood-night-close':(320,1045)}.items():
        if name == missing:
            continue
        crop = cv2.rotate(cv2.imread(str(ASSETS.parent/'event-overlays'/f'{name}.png')),cv2.ROTATE_90_COUNTERCLOCKWISE)
        h,w = crop.shape[:2]
        image[y:y+h,x:x+w] = crop
    if missing == 'conflicting_receipt':
        for name, (x,y) in {'receipt-title':(205,282), 'receipt-continue-dim':(258,996)}.items():
            crop = cv2.rotate(cv2.imread(str(ASSETS.parent/'overlays'/f'{name}.png')),cv2.ROTATE_90_COUNTERCLOCKWISE)
            h,w = crop.shape[:2]
            image[y:y+h,x:x+w] = crop
    frame = ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(Target(13,'x','s','b'))
    detected = detector.recovery.detect(frame)
    assert (detected.state == 'EVENT_PROMO') == (missing is None)
    if missing is None:
        assert dismiss_overlay_bottom_left(frame, detected) == (58,1203)


@pytest.mark.parametrize('bad',[None,'second_tap','claimable_after','wrong_boot','stale_after'])
def test_saved_ranking_missing_report_poststate_uses_original_action_bound_empty_slot(detector,tmp_path,bad):
    from top_heroes_auto.automation.fixed_reward_reconcile import reconcile_saved_fixed_reward
    store=Store(tmp_path/'offline.sqlite3')
    task=store.create_task_run('n','bxh-shop-fixed',13,'exact')
    target=Target(13,'exact','explicit','boot')
    def save(image,label):
        frame=ScreenshotService(lambda _:cv2.imencode('.png',image)[1].tobytes()).take(target,tmp_path,label)
        return detector.observe(frame)
    raw=cv2.rotate(make_frame('ranking-chest').normalized,cv2.ROTATE_90_COUNTERCLOCKWISE)
    before=save(raw,'before')
    receipt=save(np.random.default_rng(83).integers(0,256,raw.shape,dtype=np.uint8),'receipt')  # Confetti/UNKNOWN is not proof.
    if bad!='claimable_after':
        paste(raw,'ranking-empty-slot',85,100)
    after=save(raw,'after')
    geometry=claim_geometry(before,'ranking-chest',before.anchors['ranking-chest'])
    b=dict(before.evidence(),persistent_identity='disk',geometry=geometry)
    claim=store.reserve_reward_claim(task,'ranking-chest','original',json.dumps(b),not_dispatched=True)
    store.mark_reward_dispatch(claim,task)
    outcome=dict(claim_id=claim,claim_dispatched=True,before=b,immediate_after=receipt.evidence())
    path=tmp_path/'account-report.json'
    path.write_text(json.dumps(dict(persistent_identity='disk',rewards={'ranking-chest':outcome})),encoding='utf-8')
    actions=[dict(before=b['capture'],action='tap',values=geometry['tap'],outcome='DISPATCHED'),
             dict(before=after.evidence()['capture'],action='tap',values=[358,1198],outcome='DISPATCHED')]
    if bad=='second_tap':
        actions.insert(1,dict(before=receipt.evidence()['capture'],action='tap',values=geometry['tap'],outcome='DISPATCHED'))
    if bad in {'wrong_boot','stale_after'}:
        meta=after.captured.source_image.with_suffix('.json')
        value=json.loads(meta.read_text(encoding='utf-8'))
        if bad=='wrong_boot':
            value['boot_id']='different'
        else:
            value['timestamp']=(datetime.fromisoformat(before.captured.timestamp)+timedelta(minutes=3)).isoformat()
        meta.write_text(json.dumps(value),encoding='utf-8')
    (tmp_path/'actions.json').write_text(json.dumps(actions),encoding='utf-8')
    store.finish_task_run(task,'PARTIAL',report_path=str(path))
    if bad:
        with pytest.raises(ValueError):
            reconcile_saved_fixed_reward(store,claim)
    else:
        proof=reconcile_saved_fixed_reward(store,claim)
        assert proof['result']=='VERIFIED' and not proof['claim_redispatched']
    assert len(store.reward_claims('n',13))==1
    assert store.reward_claims('n',13)[0]['status']==('RESERVED' if bad else 'VERIFIED')

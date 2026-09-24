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
               weak=False, capture='before', page=True):
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
    assert second['result'] in {'ALREADY_VERIFIED', 'ALREADY_ATTEMPTED'}


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
    assert cycle_key('ranking-chest', now).endswith('initial-period-unqualified')


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
    with pytest.raises(SafetyError, match='two tab-bar'):
        port.find_tab(hidden, 'weekly-tab')
    assert calls == ['swipe', 'swipe', 'swipe']


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

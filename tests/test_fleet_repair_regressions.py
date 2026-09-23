import json
from dataclasses import replace

import numpy as np
import pytest
from test_idle_reward import Port, detection, task

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app import task_cli
from top_heroes_auto.app.process import CommandError
from top_heroes_auto.app.recovery_cli import DiagnosticRecoveryPort
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.idle_reward import IdleRewardResult, IdleRewardStatus
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.storage.store import Store
from top_heroes_auto.vision.models import CapturedScreen, ScreenState
from top_heroes_auto.vision.screenshot import ScreenshotService


def reserve(store):
    run = store.create_task_run('install', 'idle-reward', 2, '5-Emmmmm')
    claim = store.reserve_reward_claim(run, 'idle-reward', 'cycle', 'before', not_dispatched=True)
    return run, claim


def test_release_preserves_audit_and_permits_same_cycle(tmp_path):
    store = Store(tmp_path / 'test.db')
    run, claim = reserve(store)
    store.release_undispatched_reward(claim, run, 'UNKNOWN before claim')
    assert store.reward_claims('install', 2) == []
    with store.connect() as db:
        row = db.execute('SELECT original_row,evidence FROM reward_release_audit').fetchone()
    assert json.loads(row[0])['dispatch_state'] == 'NOT_DISPATCHED'
    assert row[1] == 'UNKNOWN before claim'
    assert reserve(store)[1] > claim


@pytest.mark.parametrize('state', ['UNKNOWN', 'POSSIBLE', 'VERIFIED'])
def test_uncertain_legacy_verified_never_release(tmp_path, state):
    store = Store(tmp_path / 'test.db')
    run, claim = reserve(store)
    if state == 'VERIFIED':
        store.verify_reward_claim(claim, run, 'receipt')
    else:
        with store.connect() as db:
            db.execute('UPDATE reward_claims SET dispatch_state=? WHERE id=?', (state, claim))
    with pytest.raises(ValueError):
        store.release_undispatched_reward(claim, run, 'not authority')
    assert len(store.reward_claims('install', 2)) == 1


def test_release_other_run_and_second_dispatch_rejected(tmp_path):
    store = Store(tmp_path / 'test.db')
    run, claim = reserve(store)
    with pytest.raises(ValueError):
        store.release_undispatched_reward(claim, run + 1, 'wrong run')
    store.mark_reward_dispatch(claim, run)
    with pytest.raises(ValueError):
        store.mark_reward_dispatch(claim, run)
    with pytest.raises(ValueError):
        reserve(store)


def test_transport_exception_is_uncertain_without_retry():
    class Broken(Port):
        def tap(self, current, anchor_id):
            super().tap(current, anchor_id)
            if anchor_id == 'idle-claim-button':
                raise CommandError('transport failed after send')
    port = Broken(ScreenState.GAME_HOME, ScreenState.IDLE_ENTRY_AVAILABLE, ScreenState.IDLE_REWARD_CLAIMABLE)
    result = task().run(port)
    assert result.claim_dispatched
    assert result.status == IdleRewardStatus.ACTION_RESULT_UNCERTAIN
    assert port.actions.count(('tap', 'idle-claim-button')) == 1


@pytest.mark.parametrize('reason', ['UNKNOWN_SCREEN', 'LOADING_TIMEOUT', 'CANCELLED', 'SAFETY_BLOCKED', 'NAV_FAILED'])
def test_preclaim_task_exit_releases(rig, tmp_path, monkeypatch, reason):
    manager, process, _ = rig
    process.listing = process.listing.replace('Main-Thang', 'Queen')
    manager.refresh()
    recovery = RecoveryStatus.LOADING_TIMEOUT if reason == 'LOADING_TIMEOUT' else RecoveryStatus.ALREADY_HOME
    monkeypatch.setattr(task_cli, 'run_home_recovery', lambda *a, **k: (RecoveryResult(recovery), None, False))

    class NoClaim:
        def run(self, port, cancelled):
            if reason == 'SAFETY_BLOCKED':
                raise SafetyError('preclaim guard')
            status = IdleRewardStatus.CANCELLED if reason == 'CANCELLED' else IdleRewardStatus.UNKNOWN_SCREEN
            return IdleRewardResult(status)
    result, report, _, _ = task_cli.run_idle_reward_diagnostic(manager, tmp_path, 7, 'Farm-007', task=NoClaim())
    assert not result.claim_dispatched
    assert manager.store.reward_claims(manager.namespace, 7) == []
    assert report.is_file()
    with manager.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM reward_release_audit').fetchone()[0] == 1


def test_successful_home_recovery_survives_later_idle_unknown(rig, tmp_path, monkeypatch):
    manager, process, _ = rig
    process.listing = process.listing.replace('Main-Thang', 'Queen')
    manager.refresh()
    monkeypatch.setattr(
        task_cli,
        'run_home_recovery',
        lambda *a, **k: (RecoveryResult(RecoveryStatus.SUCCESS), None, False),
    )

    class UnknownIdle:
        def run(self, port, cancelled):
            return IdleRewardResult(IdleRewardStatus.UNKNOWN_SCREEN, error='portal not uniquely detected')

    result, report_path, _, _ = task_cli.run_idle_reward_diagnostic(
        manager, tmp_path, 7, 'Farm-007', task=UnknownIdle()
    )
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert result.status == IdleRewardStatus.UNKNOWN_SCREEN
    assert result.recovery_result == 'SUCCESS'
    assert report['recovery_result'] == 'SUCCESS'
    assert report['initial_home_recovery_result'] == 'SUCCESS'
    assert result.claim_dispatched is False
    assert result.journal_result == 'RELEASED'


def test_manager_journal_hook_after_guards_before_input(rig):
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    events = []
    process.hook = lambda args: events.append('input') if 'input' in args else None
    manager.execute(7, 'tap', values=(10, 20), observed_target=target, before_input=lambda: events.append('journal'))
    assert events == ['journal', 'input']
    events.clear()
    with pytest.raises(SafetyError):
        manager.execute(7, 'tap', values=(10, 20), observed_target=replace(target, boot_id='wrong'),
                        before_input=lambda: events.append('journal'))
    assert events == []


def test_idle_rejects_stale_detection_before_transport(rig, tmp_path):
    manager, process, _ = rig
    snapshot = RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True)
    port = task_cli.DiagnosticIdleRewardPort(manager, snapshot, 7, 'Farm-007', tmp_path)
    port.latest_detection = detection(ScreenState.GAME_HOME)
    with pytest.raises(SafetyError, match='current observation'):
        port.tap(detection(ScreenState.GAME_HOME), 'idle-adventure-portal')
    assert not any('input' in call for call in process.calls)


def test_recovery_samples_are_bounded_and_final_is_fresh(rig, tmp_path, monkeypatch):
    manager, _, _ = rig
    now = [0]
    snapshot = RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True)
    port = DiagnosticRecoveryPort(manager, snapshot, 7, 'Farm-007', tmp_path, clock=lambda: now[0])
    target = Target(7, 'Farm-007', 'emulator-5568', 'boot')
    captures = []
    def capture(*args):
        captures.append(now[0])
        return target, b'raw-' + str(now[0]).encode()
    monkeypatch.setattr(manager, 'capture_verified', capture)
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    screen = CapturedScreen(7, 'Farm-007', target.serial, 'boot', image, image, (1280, 720), (1280, 720), (1, 1))
    monkeypatch.setattr(ScreenshotService, 'take', lambda *a, **k: screen)
    port.detector.anchors = ()
    for value in range(0, 91, 5):
        now[0] = value
        port.observe(value)
    now[0] = 92
    port.persist_final()
    assert len(port.diagnostic_samples) == 5
    assert len(list(tmp_path.glob('*.png'))) == 5
    assert (tmp_path / 'final-raw.png').read_bytes() == b'raw-92'
    assert port.diagnostic_samples[-1]['detection']['state'] == 'UNKNOWN'
    assert captures[-1] == 92


def test_final_capture_failure_reported_no_retry(rig, tmp_path, monkeypatch):
    manager, _, _ = rig
    port = DiagnosticRecoveryPort(manager, RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True),
                                  7, 'Farm-007', tmp_path)
    calls = []
    def fail(*args):
        calls.append(1)
        raise SafetyError('identity changed')
    monkeypatch.setattr(manager, 'capture_verified', fail)
    port.persist_final()
    assert calls == [1]
    assert port.diagnostic_samples == [{'label': 'final', 'capture_error': 'identity changed', 'screenshot': None}]


@pytest.mark.parametrize('cancel', [False, True])
def test_production_timeout_uses_known_promo_once_and_honors_cancel(rig, tmp_path, monkeypatch, cancel):
    from test_phase6_promo_recovery import Port as PromoPort
    from test_phase6_promo_recovery import _frame, _recovery

    manager, process, _ = rig
    process.listing = process.listing.replace('Main-Thang', 'Queen')
    manager.refresh()
    target, _ = manager.capture_verified(7)
    popup = _frame(tmp_path, target, popup=True, name='popup')
    home = _frame(tmp_path, target, name='home')
    popup2 = _frame(tmp_path, target, popup=True, name='popup-fresh')
    promo_port = PromoPort([popup2, home])
    screens = iter([popup.screen, home.screen])
    monkeypatch.setattr(ScreenshotService, 'take', lambda *a, **k: next(screens))
    monkeypatch.setattr('top_heroes_auto.vision.idle_detector.IdleRewardDetector.detect',
                        lambda self, s: detection(ScreenState.GAME_HOME if s is home.screen else ScreenState.UNKNOWN))
    seen = []
    def cancelled():
        return cancel
    def factory(manager, snapshot, index, name, folder, cancelled, **kwargs):
        seen.append(cancelled)
        return _recovery(promo_port).run(index, name, cancelled, **kwargs)
    monkeypatch.setattr(task_cli, 'promo_recovery_factory', factory)
    monkeypatch.setattr(task_cli, 'run_home_recovery', lambda *a, **k: (
        RecoveryResult(RecoveryStatus.LOADING_TIMEOUT, adb_target=target.serial, boot_id=target.boot_id), None, False))
    class DetectOnly:
        def run(self, port, cancelled):
            observation = port.observe('001-game-home')
            assert observation.detection.state == ScreenState.GAME_HOME
            assert not port.promo_budget_available
            return IdleRewardResult(IdleRewardStatus.NOT_AVAILABLE)
    result, _, _, _ = task_cli.run_idle_reward_diagnostic(manager, tmp_path, 7, 'Farm-007',
                                                         cancelled=cancelled, task=DetectOnly())
    assert seen == [cancelled]
    assert len(promo_port.back_calls) == (0 if cancel else 1)
    assert not result.claim_dispatched
    assert manager.store.reward_claims(manager.namespace, 7) == []


def test_timeout_unknown_popup_does_not_send_input(rig, tmp_path, monkeypatch):
    from test_phase6_promo_recovery import _frame
    manager, process, _ = rig
    target, _ = manager.capture_verified(7)
    frame = _frame(tmp_path, target, name='unknown')
    monkeypatch.setattr(ScreenshotService, 'take', lambda *a, **k: frame.screen)
    monkeypatch.setattr('top_heroes_auto.vision.idle_detector.IdleRewardDetector.detect',
                        lambda *a: detection(ScreenState.UNKNOWN))
    port = task_cli.DiagnosticIdleRewardPort(manager, RunSnapshot(manager.namespace, ((7, 'Farm-007'),), True),
                                            7, 'Farm-007', tmp_path, require_known_promo=True)
    with pytest.raises(SafetyError, match='not the qualified known promo'):
        port.observe('001-game-home')
    assert not any('input' in call for call in process.calls)

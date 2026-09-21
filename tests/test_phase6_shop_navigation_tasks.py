from top_heroes_auto.app.phase6_shop_navigation_tasks import (
    PHASE6_TARGET,
    SHOP_NAVIGATION_TASK,
    run_phase6_shop_navigation,
)
from top_heroes_auto.app.recovery_cli import RecoveryFailure
from top_heroes_auto.automation.phase6_shop_navigation import (
    ShopNavigationResult,
    ShopNavigationStatus,
)
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus


def _target2(manager, process):
    process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)


def _recovery(manager, data, index, name, **kwargs):
    path = data / "recovery.json"
    path.write_text("{}", encoding="utf-8")
    return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, False


def _record_quit(manager, process):
    calls = []

    def execute(index, action, *args, **kwargs):
        calls.append((index, action))
        if action == "quit":
            process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
        return "quit"

    manager.execute = execute
    return calls


def _success(*args):
    return ShopNavigationResult(
        status=ShopNavigationStatus.SUCCESS,
        actions=["tap:home-shop-entry", "tap:phase6-daily-info-button", "tap:phase6-daily-info-close", "tap:phase6-daily-exit"],
        captures=["home", "daily", "popup", "daily2", "home2"],
    )


def test_navigation_task_persists_success_without_claim_or_journal(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    result = run_phase6_shop_navigation(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        navigation_factory=_success,
        recovery_runner=_recovery,
    )

    assert result.status == ShopNavigationStatus.SUCCESS.value
    assert result.report_path and result.report_path.is_file()
    assert result.claims == ()
    assert result.journal_rows == 0
    assert store.reward_claims(manager.namespace, 2) == []
    assert store.latest_task_run(manager.namespace, SHOP_NAVIGATION_TASK, 2)[2] == "SUCCESS"


def test_navigation_task_rechecks_cancel_after_home_and_skips_port(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    def cancel_recovery(*args, **kwargs):
        path = tmp_path / "recovery-cancelled.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, False

    result = run_phase6_shop_navigation(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        navigation_factory=lambda *args: calls.append(args),
        recovery_runner=cancel_recovery,
        cancelled=lambda: True,
    )

    assert result.status == ShopNavigationStatus.CANCELLED.value
    assert calls == []
    assert store.latest_task_run(manager.namespace, SHOP_NAVIGATION_TASK, 2)[2] == "CANCELLED"


def test_navigation_task_persists_recovery_failure_and_never_navigates(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    def failed_recovery(*args, **kwargs):
        path = tmp_path / "recovery-failed.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.LIMIT_REACHED, error="delayed"), path, False

    result = run_phase6_shop_navigation(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        navigation_factory=lambda *args: calls.append(args),
        recovery_runner=failed_recovery,
    )

    assert result.status == RecoveryStatus.LIMIT_REACHED.value
    assert calls == []
    assert result.report_path and result.report_path.is_file()
    assert store.latest_task_run(manager.namespace, SHOP_NAVIGATION_TASK, 2)[2] == "LIMIT_REACHED"


def test_owned_start_is_cleaned_after_navigation_failure(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)

    def started_recovery(*args, **kwargs):
        process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,3,4,1,201,202\n"
        path = tmp_path / "recovery-started.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.SUCCESS), path, True

    calls = _record_quit(manager, process)

    result = run_phase6_shop_navigation(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        navigation_factory=lambda *args: ShopNavigationResult(
            status=ShopNavigationStatus.DESTINATION_UNVERIFIED,
            error="destination missing",
        ),
        recovery_runner=started_recovery,
    )

    assert result.status == ShopNavigationStatus.DESTINATION_UNVERIFIED.value
    assert result.cleanup_attempted
    assert result.cleanup_succeeded
    assert calls == [(2, "quit")]


def test_recovery_exception_after_external_start_is_not_assumed_owned(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)

    def raising_recovery(*args, **kwargs):
        process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,3,4,1,201,202\n"
        raise RuntimeError("report write failed after launch")

    calls = _record_quit(manager, process)

    result = run_phase6_shop_navigation(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        navigation_factory=_success,
        recovery_runner=raising_recovery,
    )

    assert result.status == "HOME_RECOVERY_FAILED"
    assert not result.started_by_run
    assert not result.cleanup_attempted
    assert not result.cleanup_succeeded
    assert calls == []


def test_recovery_report_failure_with_uncertain_quit_is_not_retried(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)

    def raising_recovery(*args, **kwargs):
        report = tmp_path / "recovery-report.json"
        raise RecoveryFailure(
            "recovery report unavailable; owned cleanup failed: quit uncertain",
            started_by_run=True,
            cleanup_attempted=True,
            cleanup_succeeded=False,
            report_path=report,
        )

    calls = _record_quit(manager, process)
    result = run_phase6_shop_navigation(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        navigation_factory=_success,
        recovery_runner=raising_recovery,
    )

    assert result.status == "CLEANUP_FAILED"
    assert result.started_by_run
    assert result.cleanup_attempted
    assert not result.cleanup_succeeded
    assert result.recovery_report == tmp_path / "recovery-report.json"
    assert calls == []


def test_persistence_failure_returns_task_identity_and_fallback_cleanup(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)

    def started_recovery(*args, **kwargs):
        process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,3,4,1,201,202\n"
        path = tmp_path / "recovery-started.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.SUCCESS), path, True

    calls_recorded = _record_quit(manager, process)

    original_finish = store.finish_task_run
    calls = 0

    def fail_first_finish(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database unavailable")
        return original_finish(*args, **kwargs)

    store.finish_task_run = fail_first_finish
    result = run_phase6_shop_navigation(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        navigation_factory=_success,
        recovery_runner=started_recovery,
    )

    assert result.task_run_id is not None
    assert result.report_path and result.report_path.is_file()
    assert result.status == "PERSISTENCE_FAILED"
    assert result.cleanup_attempted
    assert result.cleanup_succeeded
    assert calls_recorded == [(2, "quit")]
    assert "claims" in result.report_path.read_text(encoding="utf-8")


def test_persistence_failure_after_cleanup_failure_is_not_reported_success(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)

    def started_recovery(*args, **kwargs):
        process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,3,4,1,201,202\n"
        path = tmp_path / "recovery-started.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.SUCCESS), path, True

    def fail_cleanup(*args, **kwargs):
        raise RuntimeError("quit dispatch uncertain")

    manager.execute = fail_cleanup
    original_finish = store.finish_task_run
    calls = 0

    def fail_first_finish(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("database unavailable")
        return original_finish(*args, **kwargs)

    store.finish_task_run = fail_first_finish
    result = run_phase6_shop_navigation(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        navigation_factory=_success,
        recovery_runner=started_recovery,
    )

    assert result.status == "CLEANUP_FAILED"
    assert result.cleanup_attempted
    assert not result.cleanup_succeeded
    assert "database unavailable" in result.error
    assert "quit dispatch uncertain" in result.error

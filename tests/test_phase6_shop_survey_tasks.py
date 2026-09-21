import json

import pytest

from top_heroes_auto.app.phase6_shop_survey_tasks import (
    PHASE6_TARGET,
    SHOP_SURVEY_TASK,
    run_phase6_shop_survey,
)
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.phase6_promo_recovery import PromoRecoveryResult, PromoRecoveryStatus
from top_heroes_auto.automation.phase6_shop import ShopSurveyResult, ShopSurveyStatus
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus


def _target2(manager, process):
    process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)


def _recovery(manager, data, *args, **kwargs):
    path = data / "recovery.json"
    path.write_text("{}", encoding="utf-8")
    return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, False


def _survey(*args):
    return ShopSurveyResult(
        status=ShopSurveyStatus.PARTIAL,
        partial_reasons=["coverage_unknown_or_dynamic", "unsupported_tabs"],
    )


def test_survey_runner_persists_partial_without_claim_or_journal(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=_survey,
    )

    assert result.status == "PARTIAL"
    assert result.survey is not None
    assert result.claims == ()
    assert result.journal_rows == 0
    assert result.report_path and result.report_path.is_file()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["claims"] == []
    assert report["journal_rows"] == 0
    assert report["survey"]["partial_reasons"] == [
        "coverage_unknown_or_dynamic",
        "unsupported_tabs",
    ]
    assert store.latest_task_run(manager.namespace, SHOP_SURVEY_TASK, 2)[2] == "PARTIAL"


def test_survey_runner_rejects_wrong_target_before_persistence(rig, tmp_path):
    manager, process, store = rig
    with pytest.raises(SafetyError, match="#2 / 5-Emmmmm"):
        run_phase6_shop_survey(manager, tmp_path, 7, "Farm-007", survey_factory=_survey)
    assert store.latest_task_run(manager.namespace, SHOP_SURVEY_TASK, 7) is None


def test_survey_runner_requires_home_and_does_not_build_survey_on_recovery_failure(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    calls = []

    def failed_recovery(manager, data, *args, **kwargs):
        calls.append("recovery")
        path = data / "recovery-failed.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.UNKNOWN_SCREEN), path, False

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=failed_recovery,
        survey_factory=lambda *args: calls.append("survey"),
    )
    assert result.status == "UNKNOWN_SCREEN"
    assert calls == ["recovery"]
    assert store.latest_task_run(manager.namespace, SHOP_SURVEY_TASK, 2)[2] == "UNKNOWN_SCREEN"


def test_survey_runner_cleans_only_owned_instance(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action))

    def owned_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-owned.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, True

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=owned_recovery,
        survey_factory=_survey,
    )
    assert result.status == "PARTIAL"
    assert result.started_by_run is True
    assert result.cleanup_attempted is True
    assert result.cleanup_succeeded is True
    assert actions == [(2, "quit")]


def test_stopped_target_timeout_uses_one_same_boot_promo_recovery(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action, kwargs))
    promo_calls = []

    def timeout_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-timeout.json"
        path.write_text("{}", encoding="utf-8")
        return (
            RecoveryResult(
                RecoveryStatus.LOADING_TIMEOUT,
                adb_target="emulator-5558",
                boot_id="boot-2",
            ),
            path,
            True,
        )

    def promo(*args, **kwargs):
        promo_calls.append(kwargs)
        assert kwargs["expected_transport"] == ("emulator-5558", "boot-2")
        return PromoRecoveryResult(PromoRecoveryStatus.SUCCESS, attempted=True, actions=["keyevent:4"])

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=timeout_recovery,
        promo_recovery_factory=promo,
        survey_factory=_survey,
    )
    assert result.status == "PARTIAL"
    assert len(promo_calls) == 1
    assert result.promo_recovery is not None
    assert [(index, action) for index, action, _ in actions] == [(2, "quit")]


def test_uncertain_promo_back_is_terminal_and_owned_cleanup_is_not_retried(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action))

    def timeout_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-uncertain.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.LOADING_TIMEOUT, adb_target="emulator-5558", boot_id="boot-2"), path, True

    promo_calls = []

    def promo(*args, **kwargs):
        promo_calls.append(kwargs)
        return PromoRecoveryResult(
            PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN,
            attempted=True,
            actions=["keyevent:4"],
            error="transport uncertain",
        )

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=timeout_recovery,
        promo_recovery_factory=promo,
        survey_factory=lambda *args: pytest.fail("uncertain promo must not survey"),
    )
    assert result.status == PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN.value
    assert len(promo_calls) == 1
    assert actions == [(2, "quit")]


def test_timeout_without_boot_identity_does_not_call_promo_fallback(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    actions = []
    manager.execute = lambda index, action, **kwargs: actions.append((index, action))
    promo_calls = []

    def timeout_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-no-boot.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.LOADING_TIMEOUT, adb_target="emulator-5558"), path, True

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=timeout_recovery,
        promo_recovery_factory=lambda *args, **kwargs: promo_calls.append(kwargs),
        survey_factory=lambda *args: pytest.fail("missing boot must not survey"),
    )
    assert result.status == RecoveryStatus.LOADING_TIMEOUT.value
    assert promo_calls == []
    assert actions == [(2, "quit")]


def test_report_persistence_and_owned_cleanup_failure_are_returned(tmp_path, rig, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    actions = []

    def fail_quit(index, action, **kwargs):
        actions.append((index, action))
        raise OSError("quit uncertain")

    manager.execute = fail_quit
    monkeypatch.setattr(store, "finish_task_run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("db down")))

    def owned_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-persist-failure.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, True

    result = run_phase6_shop_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=owned_recovery,
        survey_factory=_survey,
    )
    assert result.status == "CLEANUP_FAILED"
    assert "db down" in result.error
    assert "quit uncertain" in result.error
    assert actions == [(2, "quit")]

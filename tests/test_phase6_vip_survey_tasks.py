import json
from pathlib import Path

import pytest

from top_heroes_auto.app.phase6_vip_survey_tasks import (
    PHASE6_TARGET,
    VIP_SURVEY_TASK,
    run_phase6_vip_survey,
)
from top_heroes_auto.app.recovery_cli import RecoveryFailure
from top_heroes_auto.app.service import LifecycleAttempt
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.phase6_vip_survey import VipSurveyResult, VipSurveyStatus
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus


def _target2(manager, process):
    process.listing = "0,Queen,1,2,0,-1,-1\n2,5-Emmmmm,0,0,0,-1,-1\n"
    manager.refresh()
    manager.protect(0, True)
    manager.select(2, True)


def _recovery(manager, data: Path, *args, **kwargs):
    path = data / "recovery.json"
    path.write_text("{}", encoding="utf-8")
    return (
        RecoveryResult(
            RecoveryStatus.ALREADY_HOME,
            adb_target="emulator-5558",
            boot_id="boot-2",
        ),
        path,
        False,
    )


def _survey(*args, **kwargs):
    return VipSurveyResult(
        status=VipSurveyStatus.SUCCESS,
        captures=["home-before", "vip-after-entry", "home-after-exit"],
        actions=["tap:home-vip-entry", "tap:vip-exit"],
        serial="emulator-5558",
        boot_id="boot-2",
    )


def test_vip_task_persists_observation_only_result(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)

    result = run_phase6_vip_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=_recovery,
        survey_factory=_survey,
    )

    assert result.status == VipSurveyStatus.SUCCESS.value
    assert result.survey is not None
    assert result.receipt_available is False
    assert result.claim_readiness == "NOT_IMPLEMENTED"
    assert result.claims == ()
    assert result.journal_rows == 0
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["result"] == "SUCCESS"
    assert report["receipt_available"] is False
    assert report["claims"] == []
    assert report["journal_rows"] == 0
    assert store.latest_task_run(manager.namespace, VIP_SURVEY_TASK, 2)[2] == "SUCCESS"


def test_vip_task_cancellation_before_recovery_dispatches_nothing(rig, tmp_path):
    manager, process, _ = rig
    _target2(manager, process)
    calls = []

    def recovery(*args, **kwargs):
        calls.append("recovery")
        pytest.fail("cancelled survey must not start recovery")

    result = run_phase6_vip_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=recovery,
        cancelled=lambda: True,
    )

    assert result.status == VipSurveyStatus.CANCELLED.value
    assert calls == []
    assert store_status(manager, VIP_SURVEY_TASK) == VipSurveyStatus.CANCELLED.value


def test_vip_task_requires_recovery_identity_before_building_survey(rig, tmp_path):
    manager, process, _ = rig
    _target2(manager, process)
    calls = []

    def recovery(manager, data, *args, **kwargs):
        path = data / "recovery-no-identity.json"
        path.write_text("{}", encoding="utf-8")
        return RecoveryResult(RecoveryStatus.ALREADY_HOME), path, False

    def survey(*args, **kwargs):
        calls.append("survey")
        pytest.fail("missing recovery identity must not build survey")

    result = run_phase6_vip_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=recovery,
        survey_factory=survey,
    )

    assert result.status == VipSurveyStatus.IDENTITY_MISMATCH.value
    assert calls == []


def test_vip_task_persists_uncertain_launch_without_cleanup_or_survey(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)
    attempt = {
        "index": 2,
        "action": "launch",
        "target_name": "5-Emmmmm",
        "pre_running": False,
        "ownership": "UNKNOWN",
        "ownership_uncertain": True,
        "dispatch_attempted": True,
        "dispatches": [
            {
                "action": "launch",
                "attempted": True,
                "completed": True,
                "outcome": "DISPATCHED",
                "error": "indexed target changed identity",
            }
        ],
        "failure_stage": "post_dispatch_wait",
        "error": "indexed target changed identity",
    }

    def uncertain_recovery(*args, **kwargs):
        raise RecoveryFailure(
            "indexed launch ownership is uncertain",
            started_by_run=False,
            cleanup_attempted=False,
            cleanup_succeeded=False,
            launch_attempt=attempt,
            ownership_uncertain=True,
        )

    result = run_phase6_vip_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=uncertain_recovery,
    )

    assert result.status == "HOME_RECOVERY_FAILED"
    assert result.started_by_run is False
    assert result.ownership_uncertain is True
    assert result.launch_attempt == attempt
    assert result.survey is None
    assert result.claims == ()
    assert result.journal_rows == 0
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["launch_attempt"]["ownership"] == "UNKNOWN"
    assert report["ownership_uncertain"] is True
    assert report["cleanup_attempted"] is False
    assert report["journal_rows"] == 0
    assert store.latest_task_run(manager.namespace, VIP_SURVEY_TASK, 2)[2] == "HOME_RECOVERY_FAILED"
    assert not any(call[1] in {"launch", "quit", "-s"} for call in process.calls if len(call) > 1)


def test_vip_task_does_not_reuse_stale_launch_attempt_after_recovery_error(rig, tmp_path):
    manager, process, _ = rig
    _target2(manager, process)
    manager._last_lifecycle_attempt = LifecycleAttempt(
        index=2,
        action="launch",
        target_name="5-Emmmmm",
        pre_running=False,
        ownership="OWNED",
    )

    def failed_recovery(*args, **kwargs):
        raise RuntimeError("recovery boundary failed before dispatch")

    result = run_phase6_vip_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=failed_recovery,
    )

    assert result.status == "HOME_RECOVERY_FAILED"
    assert result.started_by_run is False
    assert result.launch_attempt is None
    assert result.ownership_uncertain is False
    assert result.cleanup_attempted is False
    assert not any(call[1] in {"launch", "quit", "-s"} for call in process.calls if len(call) > 1)


def test_vip_task_persistence_failure_cleans_owned_instance_once(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    cleanup_calls = []

    def owned_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-owned.json"
        path.write_text("{}", encoding="utf-8")
        return (
            RecoveryResult(
                RecoveryStatus.ALREADY_HOME,
                adb_target="emulator-5558",
                boot_id="boot-2",
            ),
            path,
            True,
        )

    def execute(index, action, **kwargs):
        cleanup_calls.append((index, action))

    monkeypatch.setattr(manager, "execute", execute)
    def fail_finish(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(store, "finish_task_run", fail_finish)

    result = run_phase6_vip_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=owned_recovery,
        survey_factory=_survey,
    )

    assert result.status == "PERSISTENCE_FAILED"
    assert cleanup_calls == [(2, "quit")]
    assert result.cleanup_attempted is True
    assert result.cleanup_succeeded is True
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["result"] == "PERSISTENCE_FAILED"
    assert report["cleanup_attempted"] is True
    assert report["cleanup_succeeded"] is True


def test_vip_task_cleanup_failure_is_reported_without_retry(rig, tmp_path, monkeypatch):
    manager, process, store = rig
    _target2(manager, process)
    cleanup_calls = []

    def owned_recovery(manager, data, *args, **kwargs):
        path = data / "recovery-owned-fail.json"
        path.write_text("{}", encoding="utf-8")
        return (
            RecoveryResult(
                RecoveryStatus.ALREADY_HOME,
                adb_target="emulator-5558",
                boot_id="boot-2",
            ),
            path,
            True,
        )

    def execute(index, action, **kwargs):
        cleanup_calls.append((index, action))
        raise RuntimeError("quit uncertain")

    monkeypatch.setattr(manager, "execute", execute)
    def fail_finish(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(store, "finish_task_run", fail_finish)

    result = run_phase6_vip_survey(
        manager,
        tmp_path,
        *PHASE6_TARGET,
        recovery_runner=owned_recovery,
        survey_factory=_survey,
    )

    assert result.status == "CLEANUP_FAILED"
    assert cleanup_calls == [(2, "quit")]
    assert result.cleanup_attempted is True
    assert result.cleanup_succeeded is False
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["result"] == "CLEANUP_FAILED"
    assert "quit uncertain" in report["error"]


def test_vip_task_rejects_wrong_target_before_task_run(rig, tmp_path):
    manager, process, store = rig
    _target2(manager, process)

    with pytest.raises(SafetyError, match="#2 / 5-Emmmmm"):
        run_phase6_vip_survey(manager, tmp_path, 7, "Farm-007")

    assert store.latest_task_run(manager.namespace, VIP_SURVEY_TASK, 7) is None


@pytest.mark.parametrize("guard", ("target_unselected", "target_protected", "queen_unprotected"))
def test_vip_task_requires_selection_and_protection_guards(rig, tmp_path, guard):
    manager, process, store = rig
    _target2(manager, process)
    if guard == "target_unselected":
        manager.select(2, False)
    elif guard == "target_protected":
        manager.protect(2, True)
    else:
        manager.protect(0, False)

    with pytest.raises(SafetyError):
        run_phase6_vip_survey(manager, tmp_path, *PHASE6_TARGET)

    assert store.latest_task_run(manager.namespace, VIP_SURVEY_TASK, 2) is None


def store_status(manager, task):
    return manager.store.latest_task_run(manager.namespace, task, 2)[2]

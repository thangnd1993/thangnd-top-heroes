"""Durable, observation-only Phase 6 VIP survey task.

The survey is intentionally separate from the reward task.  It records the
current VIP page evidence and performs only the qualified Home → VIP and VIP →
Home navigation actions.  It never builds a reward profile, explorer, claim
adapter, or journal port.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from top_heroes_auto.app.diagnostic import _instance, _only_target_changed, _state
from top_heroes_auto.app.recovery_cli import RecoveryFailure, run_home_recovery
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.phase6_vip_survey import (
    GuardedVipSurvey,
    ManagerVipSurveyPort,
    VipSurveyResult,
    VipSurveyStatus,
)
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.models import VisualAnchor
from top_heroes_auto.vision.resources import template_folder

VIP_SURVEY_TASK = "vip-survey"
VIP_SURVEY_LABEL = "khảo sát VIP / không nhận quà"
VIP_SURVEY_SCOPE = (
    "observation-only; Home/VIP evidence and bounded entry/exit; no claims, "
    "purchases, resource spending, or reward journal"
)
PHASE6_TARGET = (2, "5-Emmmmm")
SURVEY_SUCCESS_STATUSES = frozenset({VipSurveyStatus.SUCCESS.value})


@dataclass(frozen=True)
class VipSurveyTaskResult:
    task: str
    status: str
    task_run_id: int | None = None
    report_path: Path | None = None
    started_by_run: bool = False
    launch_attempt: dict | None = None
    ownership_uncertain: bool = False
    recovery_report: Path | None = None
    survey: VipSurveyResult | None = None
    error: str | None = None
    cleanup_attempted: bool = False
    cleanup_succeeded: bool = False
    receipt_available: bool = False
    claim_readiness: str = "NOT_IMPLEMENTED"
    claims: tuple[str, ...] = ()
    journal_rows: int = 0

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "label": VIP_SURVEY_LABEL,
            "scope": VIP_SURVEY_SCOPE,
            "result": self.status,
            "task_run_id": self.task_run_id,
            "report": str(self.report_path) if self.report_path else None,
            "started_by_run": self.started_by_run,
            "launch_attempt": self.launch_attempt,
            "ownership_uncertain": self.ownership_uncertain,
            "recovery_report": str(self.recovery_report) if self.recovery_report else None,
            "survey": self.survey.as_dict() if self.survey else None,
            "error": self.error,
            "cleanup_attempted": self.cleanup_attempted,
            "cleanup_succeeded": self.cleanup_succeeded,
            "receipt_available": self.receipt_available,
            "claim_readiness": self.claim_readiness,
            "claims": list(self.claims),
            "journal_rows": self.journal_rows,
        }


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")


def _safe_folder_name(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return value or "account"


def _merge_error(existing: str | None, detail: str) -> str:
    if not existing:
        return detail
    if detail in existing:
        return existing
    return f"{existing}; {detail}"


def phase6_asset_root() -> Path:
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
    return root / "assets" / "tasks" / "phase6"


def _anchor(folder: Path, anchor_id: str) -> VisualAnchor:
    matches = [item for item in load_anchors(folder) if item.id == anchor_id]
    if len(matches) != 1:
        raise SafetyError(f"Expected one independently verified VIP survey anchor: {anchor_id!r}.")
    return matches[0]


def vip_survey_factory(
    manager,
    snapshot,
    index,
    name,
    folder,
    *,
    expected_identity: tuple[str, str],
    cancelled: Callable[[], bool] = lambda: False,
):
    """Build and run the bounded VIP observation route from packaged anchors."""

    home = phase6_asset_root() / "home"
    vip = phase6_asset_root() / "vip"
    anchors = {
        "home_entry": _anchor(home, "home-vip-entry"),
        "page": _anchor(vip, "vip-page"),
        # This is a generic exit crop and is only actionable after the VIP
        # page identity and diagnostic anchors have been verified.
        "exit": _anchor(vip, "vip-home"),
        "home": _anchor(template_folder() / "home", "home-bottom-navigation"),
    }
    for role, anchor_id in (("free", "vip-free"), ("available", "vip-available"), ("claim", "vip-claim")):
        matches = [item for item in load_anchors(vip) if item.id == anchor_id]
        if len(matches) > 1:
            raise SafetyError(f"VIP diagnostic anchor is duplicated or ambiguous: {anchor_id!r}.")
        if matches:
            anchors[role] = matches[0]
    paid_matches = [item for item in load_anchors(vip) if item.id == "vip-paid"]
    if len(paid_matches) == 1:
        anchors["paid"] = paid_matches[0]
    elif paid_matches:
        raise SafetyError("VIP paid evidence is duplicated or ambiguous.")
    port = ManagerVipSurveyPort(manager, snapshot, index, name, expected_identity, folder)
    return GuardedVipSurvey(
        port,
        anchors,
        ScreenDetector.from_folder(template_folder()).detect,
        expected_identity,
        max_seconds=30.0,
    ).run(cancelled)


def run_phase6_vip_survey(
    manager: Manager,
    data: Path,
    index: int,
    name: str,
    *,
    survey_factory: Callable[..., VipSurveyResult] | None = None,
    recovery_runner: Callable[..., tuple[RecoveryResult, Path, bool]] = run_home_recovery,
    cancelled: Callable[[], bool] = lambda: False,
    cleanup_owned: bool = True,
) -> VipSurveyTaskResult:
    """Run one bounded, claim-free VIP observation for the exact target."""

    if (index, name) != PHASE6_TARGET:
        raise SafetyError("Phase 6 VIP survey is authorized only for #2 / 5-Emmmmm.")
    target = _instance(manager, index, name)
    queen = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, queen.index).protected:
        raise SafetyError("Queen must remain Protected before Phase 6 VIP survey.")
    metadata = manager.store.metadata(manager.namespace, target.index)
    if metadata.protected or not metadata.selected:
        raise SafetyError("Phase 6 VIP target must be selected and not Protected.")

    before = _state(manager.list_readonly())
    snapshot = RunSnapshot(manager.namespace, ((index, name),), True)
    folder = data / "diagnostics" / "tasks" / VIP_SURVEY_TASK / _safe_folder_name(name) / _stamp()
    folder.mkdir(parents=True, exist_ok=False)
    task_run_id = manager.store.create_task_run(manager.namespace, VIP_SURVEY_TASK, index, name)
    result = VipSurveyTaskResult(VIP_SURVEY_TASK, "SAFETY_BLOCKED", task_run_id=task_run_id)
    recovery_report: Path | None = None
    started_by_run = False
    launch_attempt: dict | None = None
    ownership_uncertain = False
    cleanup_attempted = False
    cleanup_succeeded = False
    survey: VipSurveyResult | None = None
    error: str | None = None
    effective_factory = survey_factory or vip_survey_factory
    prior_lifecycle_attempt = manager.last_lifecycle_attempt

    try:
        if cancelled():
            result = VipSurveyTaskResult(VIP_SURVEY_TASK, VipSurveyStatus.CANCELLED.value, task_run_id=task_run_id)
        else:
            try:
                recovery, recovery_report, started_by_run = recovery_runner(
                    manager,
                    data,
                    index,
                    name,
                    cancelled=cancelled,
                    cleanup_owned=False,
                )
            except RecoveryFailure as exc:
                started_by_run = exc.started_by_run
                launch_attempt = exc.launch_attempt
                ownership_uncertain = exc.ownership_uncertain
                cleanup_attempted = exc.cleanup_attempted
                cleanup_succeeded = exc.cleanup_succeeded
                recovery_report = exc.report_path
                error = f"Home recovery raised: {exc}"
                result = VipSurveyTaskResult(
                    VIP_SURVEY_TASK,
                    "CLEANUP_FAILED" if started_by_run and cleanup_attempted and not cleanup_succeeded else "HOME_RECOVERY_FAILED",
                    task_run_id=task_run_id,
                    started_by_run=started_by_run,
                    launch_attempt=launch_attempt,
                    ownership_uncertain=ownership_uncertain,
                    recovery_report=recovery_report,
                    error=error,
                    cleanup_attempted=cleanup_attempted,
                    cleanup_succeeded=cleanup_succeeded,
                )
                recovery = None
            except Exception as exc:  # noqa: BLE001 - ownership is unknown; do not infer cleanup
                attempt = manager.last_lifecycle_attempt
                # A custom recovery boundary may fail without dispatching a
                # lifecycle action. Do not attribute an older Manager attempt
                # to this task's failure or infer ownership from stale state.
                current_attempt = (
                    attempt
                    if attempt is not None
                    and attempt is not prior_lifecycle_attempt
                    and attempt.action == "launch"
                    else None
                )
                launch_attempt = current_attempt.as_dict() if current_attempt is not None else None
                ownership_uncertain = bool(current_attempt is not None and current_attempt.ownership_uncertain)
                started_by_run = bool(current_attempt is not None and current_attempt.ownership == "OWNED")
                error = f"Home recovery raised: {exc}; ownership and cleanup outcome are unknown"
                result = VipSurveyTaskResult(
                    VIP_SURVEY_TASK,
                    "HOME_RECOVERY_FAILED",
                    task_run_id=task_run_id,
                    started_by_run=started_by_run,
                    launch_attempt=launch_attempt,
                    ownership_uncertain=ownership_uncertain,
                    error=error,
                )
                recovery = None

            if recovery is not None and result.status == "SAFETY_BLOCKED":
                launch_attempt = recovery.launch_attempt
                ownership_uncertain = recovery.ownership_uncertain
                if recovery.status not in {RecoveryStatus.SUCCESS, RecoveryStatus.ALREADY_HOME}:
                    error = f"GAME_HOME precondition failed: {recovery.status.value}"
                    result = VipSurveyTaskResult(
                        VIP_SURVEY_TASK,
                        VipSurveyStatus.CANCELLED.value if recovery.status == RecoveryStatus.CANCELLED else recovery.status.value,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        launch_attempt=launch_attempt,
                        ownership_uncertain=ownership_uncertain,
                        recovery_report=recovery_report,
                        error=error,
                    )
                elif not recovery.adb_target or not recovery.boot_id:
                    error = "Home recovery did not provide a verified serial/boot identity; VIP survey blocked."
                    result = VipSurveyTaskResult(
                        VIP_SURVEY_TASK,
                        VipSurveyStatus.IDENTITY_MISMATCH.value,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        launch_attempt=launch_attempt,
                        ownership_uncertain=ownership_uncertain,
                        recovery_report=recovery_report,
                        error=error,
                    )
                elif cancelled():
                    result = VipSurveyTaskResult(
                        VIP_SURVEY_TASK,
                        VipSurveyStatus.CANCELLED.value,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        launch_attempt=launch_attempt,
                        ownership_uncertain=ownership_uncertain,
                        recovery_report=recovery_report,
                        error="VIP survey cancelled after Home recovery.",
                    )
                else:
                    survey = effective_factory(
                        manager,
                        snapshot,
                        index,
                        name,
                        folder,
                        expected_identity=(recovery.adb_target, recovery.boot_id),
                        cancelled=cancelled,
                    )
                    result = VipSurveyTaskResult(
                        VIP_SURVEY_TASK,
                        survey.status.value,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        launch_attempt=launch_attempt,
                        ownership_uncertain=ownership_uncertain,
                        recovery_report=recovery_report,
                        survey=survey,
                        error=survey.error,
                    )
    except Exception as exc:  # noqa: BLE001 - persist all bounded survey outcomes
        error = _merge_error(error, str(exc))
        result = VipSurveyTaskResult(
            VIP_SURVEY_TASK,
            "SAFETY_BLOCKED",
            task_run_id=task_run_id,
            started_by_run=started_by_run,
            launch_attempt=launch_attempt,
            ownership_uncertain=ownership_uncertain,
            recovery_report=recovery_report,
            survey=survey,
            error=error,
            cleanup_attempted=cleanup_attempted,
            cleanup_succeeded=cleanup_succeeded,
        )
    finally:
        if started_by_run and cleanup_owned and not cleanup_attempted:
            cleanup_attempted = True
            try:
                manager.execute(index, "quit", snapshot=snapshot)
                cleanup_succeeded = True
            except Exception as exc:  # noqa: BLE001 - cleanup is a safety boundary
                error = _merge_error(error or result.error, f"Owned-instance cleanup failed: {exc}")
                result = VipSurveyTaskResult(
                    VIP_SURVEY_TASK,
                    "CLEANUP_FAILED",
                    task_run_id=task_run_id,
                    started_by_run=started_by_run,
                    launch_attempt=launch_attempt,
                    ownership_uncertain=ownership_uncertain,
                    recovery_report=recovery_report,
                    survey=survey,
                    error=error,
                    cleanup_attempted=cleanup_attempted,
                    cleanup_succeeded=cleanup_succeeded,
                )

        after: dict | None = None
        isolation: list[int] | None = None
        inventory_status = "unavailable"
        observed_changed_indices: list[int] | None = None
        unrelated_changed_indices: list[int] | None = None
        try:
            live_instances = manager.list_readonly()
            if live_instances is not None:
                after = _state(live_instances)
                inventory_status = "available"
                changed = {
                    item
                    for item in set(before) | set(after)
                    if before.get(item) != after.get(item)
                }
                observed_changed_indices = sorted(changed)
                unrelated_changed_indices = sorted(changed - {index})
                isolation = _only_target_changed(before, after, index)
            else:
                detail = "Instance inventory unavailable; isolation was not verified."
                error = _merge_error(error or result.error, detail)
                if result.status in SURVEY_SUCCESS_STATUSES:
                    result = VipSurveyTaskResult(
                        VIP_SURVEY_TASK,
                        VipSurveyStatus.BLOCKED.value,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        launch_attempt=launch_attempt,
                        ownership_uncertain=ownership_uncertain,
                        recovery_report=recovery_report,
                        survey=survey,
                        error=error,
                        cleanup_attempted=cleanup_attempted,
                        cleanup_succeeded=cleanup_succeeded,
                    )
        except (OSError, RuntimeError, TypeError, ValueError, SafetyError) as exc:
            error = _merge_error(error or result.error, str(exc))
            if result.status in SURVEY_SUCCESS_STATUSES:
                result = VipSurveyTaskResult(
                    VIP_SURVEY_TASK,
                    VipSurveyStatus.BLOCKED.value,
                    task_run_id=task_run_id,
                    started_by_run=started_by_run,
                    launch_attempt=launch_attempt,
                    ownership_uncertain=ownership_uncertain,
                    recovery_report=recovery_report,
                    survey=survey,
                    error=error,
                    cleanup_attempted=cleanup_attempted,
                    cleanup_succeeded=cleanup_succeeded,
                )

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_run_id": task_run_id,
            "task": VIP_SURVEY_TASK,
            "label": VIP_SURVEY_LABEL,
            "scope": VIP_SURVEY_SCOPE,
            "instance": {"index": index, "name": name},
            "authorized_target": {"index": PHASE6_TARGET[0], "name": PHASE6_TARGET[1]},
            "started_by_run": started_by_run,
            "launch_attempt": launch_attempt,
            "ownership_uncertain": ownership_uncertain,
            "cleanup_requested": cleanup_owned,
            "cleanup_attempted": cleanup_attempted,
            "cleanup_succeeded": cleanup_succeeded,
            "recovery_report": str(recovery_report) if recovery_report else None,
            "before_instances": before,
            "after_instances": after,
            "inventory_status": inventory_status,
            "observed_changed_indices": observed_changed_indices,
            "unrelated_changed_indices": unrelated_changed_indices,
            "isolation_changed_indices": isolation,
            "survey": survey.as_dict() if survey else None,
            "result": result.status,
            "error": error or result.error,
            "receipt_available": False,
            "claim_readiness": "NOT_IMPLEMENTED",
            "claims": [],
            "journal_rows": 0,
        }
        report_path = folder / "report.json"
        try:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            manager.store.finish_task_run(
                task_run_id,
                result.status,
                error=error or result.error or "",
                report_path=str(report_path),
            )
        except Exception as persistence_exc:  # noqa: BLE001 - preserve evidence and cleanup state
            cleanup_error: str | None = None
            if started_by_run and not cleanup_attempted:
                cleanup_attempted = True
                try:
                    manager.execute(index, "quit", snapshot=snapshot)
                    cleanup_succeeded = True
                except Exception as cleanup_exc:  # noqa: BLE001 - never retry uncertain cleanup
                    cleanup_error = str(cleanup_exc)
            cleanup_already_failed = started_by_run and cleanup_attempted and not cleanup_succeeded
            failure_status = "CLEANUP_FAILED" if cleanup_error or cleanup_already_failed else "PERSISTENCE_FAILED"
            failure_error = _merge_error(error or result.error, str(persistence_exc))
            if cleanup_error:
                failure_error = _merge_error(failure_error, f"Owned-instance cleanup failed: {cleanup_error}")
            result = VipSurveyTaskResult(
                VIP_SURVEY_TASK,
                failure_status,
                task_run_id=task_run_id,
                report_path=report_path,
                started_by_run=started_by_run,
                launch_attempt=launch_attempt,
                ownership_uncertain=ownership_uncertain,
                recovery_report=recovery_report,
                survey=survey,
                error=failure_error,
                cleanup_attempted=cleanup_attempted,
                cleanup_succeeded=cleanup_succeeded,
            )
            failure_report = {
                **report,
                "cleanup_requested": cleanup_owned or cleanup_attempted,
                "cleanup_attempted": cleanup_attempted,
                "cleanup_succeeded": cleanup_succeeded,
                "result": failure_status,
                "error": failure_error,
                "persistence_error": str(persistence_exc),
                "cleanup_error": cleanup_error,
            }
            try:
                report_path.write_text(json.dumps(failure_report, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:  # noqa: BLE001 - best effort only
                pass
            try:
                manager.store.finish_task_run(
                    task_run_id,
                    failure_status,
                    error=failure_error,
                    report_path=str(report_path),
                )
            except Exception:  # noqa: BLE001 - preserve returned result
                pass
        else:
            result = VipSurveyTaskResult(
                VIP_SURVEY_TASK,
                result.status,
                task_run_id=task_run_id,
                report_path=report_path,
                started_by_run=started_by_run,
                launch_attempt=launch_attempt,
                ownership_uncertain=ownership_uncertain,
                recovery_report=recovery_report,
                survey=survey,
                error=error or result.error,
                cleanup_attempted=cleanup_attempted,
                cleanup_succeeded=cleanup_succeeded,
            )
    return result

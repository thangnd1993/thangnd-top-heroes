"""Persistence-safe, observation-only broader Phase 6 shop survey task.

This task is deliberately separate from Free Pack and from the fixed
daily-offer navigation task.  It builds only ``ManagerShopSurveyPort`` and
``ShopSurveyEngine``; it never constructs a reward explorer, claim adapter, or
journal port.  The packaged profile currently covers Home, the qualified
daily-offer page, and its independently qualified information popup.  Paid or
otherwise forbidden tabs are not dispatchable.  Missing safe tabs and scroll boundaries remain an
honest ``PARTIAL`` result; this task never claims rewards, purchases offers,
or scrolls content.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from top_heroes_auto.app.diagnostic import _instance, _only_target_changed, _state
from top_heroes_auto.app.phase6_runtime import pending_promo_anchor as load_pending_promo_anchor
from top_heroes_auto.app.phase6_runtime import shop_survey_factory
from top_heroes_auto.app.recovery_cli import RecoveryFailure, run_home_recovery
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.phase6_promo_recovery import PromoRecoveryResult, PromoRecoveryStatus
from top_heroes_auto.automation.phase6_shop import ShopSurveyResult, ShopSurveyStatus
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus

PHASE6_TARGET = (2, "5-Emmmmm")
SHOP_SURVEY_TASK = "shop-survey"
SHOP_SURVEY_LABEL = "khảo sát Tiệm (phạm vi một phần) / không nhận quà"
SHOP_SURVEY_SCOPE = (
    "observation-only; qualified Home/daily/help surfaces; forbidden paid tabs excluded; no "
    "claims, purchases, scrolls, or reward journal"
)
SURVEY_SUCCESS_STATUSES = frozenset(
    {ShopSurveyStatus.COMPLETE.value, ShopSurveyStatus.PARTIAL.value}
)


@dataclass(frozen=True)
class ShopSurveyTaskResult:
    task: str
    status: str
    task_run_id: int | None = None
    report_path: Path | None = None
    started_by_run: bool = False
    recovery_report: Path | None = None
    survey: ShopSurveyResult | None = None
    error: str | None = None
    cleanup_attempted: bool = False
    cleanup_succeeded: bool = False
    claims: tuple[str, ...] = ()
    journal_rows: int = 0
    promo_recovery: PromoRecoveryResult | None = None

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "label": SHOP_SURVEY_LABEL,
            "scope": SHOP_SURVEY_SCOPE,
            "result": self.status,
            "task_run_id": self.task_run_id,
            "report": str(self.report_path) if self.report_path else None,
            "started_by_run": self.started_by_run,
            "recovery_report": str(self.recovery_report) if self.recovery_report else None,
            "survey": self.survey.as_dict() if self.survey else None,
            "error": self.error,
            "cleanup_attempted": self.cleanup_attempted,
            "cleanup_succeeded": self.cleanup_succeeded,
            "claims": list(self.claims),
            "journal_rows": self.journal_rows,
            "promo_recovery": self.promo_recovery.as_dict() if self.promo_recovery else None,
        }


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")


def _safe_folder_name(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return value or "account"


def _report_folder(data: Path, name: str) -> Path:
    folder = data / "diagnostics" / "tasks" / SHOP_SURVEY_TASK / _safe_folder_name(name) / _stamp()
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def _merge_error(existing: str | None, detail: str) -> str:
    if not existing:
        return detail
    if detail in existing:
        return existing
    return f"{existing}; {detail}"


def _status_value(value) -> str:
    return getattr(value, "value", str(value))


def run_phase6_shop_survey(
    manager: Manager,
    data: Path,
    index: int,
    name: str,
    *,
    survey_factory: Callable[..., ShopSurveyResult] | None = None,
    recovery_runner: Callable[..., tuple[RecoveryResult, Path, bool]] = run_home_recovery,
    promo_recovery_factory: Callable[..., PromoRecoveryResult] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    cleanup_owned: bool = True,
) -> ShopSurveyTaskResult:
    """Run the bounded claim-free shop survey for the exact Phase 6 target."""

    if (index, name) != PHASE6_TARGET:
        raise SafetyError("Phase 6 is authorized only for #2 / 5-Emmmmm.")
    target = _instance(manager, index, name)
    queen = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, queen.index).protected:
        raise SafetyError("Queen must remain Protected before Phase 6 shop survey.")
    metadata = manager.store.metadata(manager.namespace, target.index)
    if metadata.protected or not metadata.selected:
        raise SafetyError("Phase 6 target must be selected and not Protected.")

    before = _state(manager.list_readonly())
    snapshot = RunSnapshot(manager.namespace, ((index, name),), True)
    folder = _report_folder(data, name)
    task_run_id = manager.store.create_task_run(manager.namespace, SHOP_SURVEY_TASK, index, name)
    result = ShopSurveyTaskResult(SHOP_SURVEY_TASK, "SAFETY_BLOCKED", task_run_id=task_run_id)
    recovery_report: Path | None = None
    started_by_run = False
    cleanup_attempted = False
    cleanup_succeeded = False
    survey: ShopSurveyResult | None = None
    promo_recovery: PromoRecoveryResult | None = None
    error: str | None = None
    effective_factory = survey_factory

    try:
        if cancelled():
            result = ShopSurveyTaskResult(
                SHOP_SURVEY_TASK,
                ShopSurveyStatus.CANCELLED.value,
                task_run_id=task_run_id,
            )
        else:
            recovery: RecoveryResult | None = None
            run_standard_recovery = True
            if promo_recovery_factory is not None and target.running:
                try:
                    promo_recovery = promo_recovery_factory(
                        manager,
                        snapshot,
                        index,
                        name,
                        folder,
                        cancelled,
                    )
                except Exception as exc:  # noqa: BLE001 - no safe fallback after unknown hook state
                    error = f"Known promo recovery raised: {exc}; no fallback recovery is safe"
                    result = ShopSurveyTaskResult(
                        SHOP_SURVEY_TASK,
                        "PROMO_RECOVERY_FAILED",
                        task_run_id=task_run_id,
                        error=error,
                        promo_recovery=promo_recovery,
                    )
                    run_standard_recovery = False
                else:
                    promo_status = _status_value(promo_recovery.status)
                    if promo_status == PromoRecoveryStatus.SUCCESS.value:
                        recovered_frame = promo_recovery.after or promo_recovery.before or {}
                        recovery = RecoveryResult(
                            RecoveryStatus.ALREADY_HOME,
                            adb_target=recovered_frame.get("adb_target"),
                            boot_id=recovered_frame.get("boot_id"),
                        )
                        run_standard_recovery = False
                    elif promo_status != PromoRecoveryStatus.NOT_PRESENT.value:
                        error = f"Known promo recovery failed: {promo_status}: {promo_recovery.error or ''}".strip()
                        result = ShopSurveyTaskResult(
                            SHOP_SURVEY_TASK,
                            promo_status,
                            task_run_id=task_run_id,
                            error=error,
                            promo_recovery=promo_recovery,
                        )
                        run_standard_recovery = False
            if run_standard_recovery:
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
                    cleanup_attempted = exc.cleanup_attempted
                    cleanup_succeeded = exc.cleanup_succeeded
                    recovery_report = exc.report_path
                    error = f"Home recovery raised: {exc}"
                    result = ShopSurveyTaskResult(
                        SHOP_SURVEY_TASK,
                        (
                            "CLEANUP_FAILED"
                            if started_by_run and cleanup_attempted and not cleanup_succeeded
                            else "HOME_RECOVERY_FAILED"
                        ),
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        recovery_report=recovery_report,
                        error=error,
                        cleanup_attempted=cleanup_attempted,
                        cleanup_succeeded=cleanup_succeeded,
                        promo_recovery=promo_recovery,
                    )
                    recovery = None
                except Exception as exc:  # noqa: BLE001 - ownership is unknown; never infer it
                    error = f"Home recovery raised: {exc}; ownership and cleanup outcome are unknown"
                    result = ShopSurveyTaskResult(
                        SHOP_SURVEY_TASK,
                        "HOME_RECOVERY_FAILED",
                        task_run_id=task_run_id,
                        error=error,
                        promo_recovery=promo_recovery,
                    )
                    recovery = None

            # A stopped target may remain on the known promo after bounded
            # recovery times out.  Allow one current-frame, same-boot Back
            # probe only for this exact timeout; all other recovery failures
            # remain terminal and never fall through to another input path.
            if (
                recovery is not None
                and recovery.status == RecoveryStatus.LOADING_TIMEOUT
                and promo_recovery_factory is not None
                and recovery.adb_target
                and recovery.boot_id
            ):
                try:
                    promo_recovery = promo_recovery_factory(
                        manager,
                        snapshot,
                        index,
                        name,
                        folder,
                        cancelled,
                        expected_transport=(recovery.adb_target, recovery.boot_id),
                    )
                except Exception as exc:  # noqa: BLE001 - no retry after unknown hook state
                    error = f"Known promo fallback raised: {exc}; no retry is safe"
                    result = ShopSurveyTaskResult(
                        SHOP_SURVEY_TASK,
                        "PROMO_RECOVERY_FAILED",
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        recovery_report=recovery_report,
                        error=error,
                        promo_recovery=promo_recovery,
                    )
                else:
                    promo_status = _status_value(promo_recovery.status)
                    if promo_status == PromoRecoveryStatus.SUCCESS.value:
                        recovery = RecoveryResult(
                            RecoveryStatus.ALREADY_HOME,
                            adb_target=recovery.adb_target,
                            boot_id=recovery.boot_id,
                        )
                    elif promo_status != PromoRecoveryStatus.NOT_PRESENT.value:
                        error = f"Known promo fallback failed: {promo_status}: {promo_recovery.error or ''}".strip()
                        result = ShopSurveyTaskResult(
                            SHOP_SURVEY_TASK,
                            promo_status,
                            task_run_id=task_run_id,
                            started_by_run=started_by_run,
                            recovery_report=recovery_report,
                            error=error,
                            promo_recovery=promo_recovery,
                        )

            if recovery is not None and result.status == "SAFETY_BLOCKED":
                if recovery.status not in {RecoveryStatus.SUCCESS, RecoveryStatus.ALREADY_HOME}:
                    error = f"GAME_HOME precondition failed: {recovery.status.value}"
                    result = ShopSurveyTaskResult(
                        SHOP_SURVEY_TASK,
                        (
                            ShopSurveyStatus.CANCELLED.value
                            if recovery.status == RecoveryStatus.CANCELLED
                            else recovery.status.value
                        ),
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        recovery_report=recovery_report,
                        error=error,
                        promo_recovery=promo_recovery,
                    )
                elif cancelled():
                    result = ShopSurveyTaskResult(
                        SHOP_SURVEY_TASK,
                        ShopSurveyStatus.CANCELLED.value,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        recovery_report=recovery_report,
                        error="Shop survey cancelled after Home recovery.",
                        promo_recovery=promo_recovery,
                    )
                else:
                    if effective_factory is None:
                        effective_factory = shop_survey_factory
                    if effective_factory is shop_survey_factory and promo_recovery_factory is not None:
                        initial_identity = (
                            (recovery.adb_target, recovery.boot_id)
                            if recovery.adb_target and recovery.boot_id
                            else None
                        )
                        if initial_identity is None:
                            error = (
                                "Initial shop survey frame requires the successful Home recovery "
                                "serial and boot identity."
                            )
                            promo_recovery = PromoRecoveryResult(
                                status=PromoRecoveryStatus.IDENTITY_MISMATCH,
                                trigger="initial_home",
                                expected_page="game-home",
                                error=error,
                            )
                            result = ShopSurveyTaskResult(
                                SHOP_SURVEY_TASK,
                                PromoRecoveryStatus.IDENTITY_MISMATCH.value,
                                task_run_id=task_run_id,
                                started_by_run=started_by_run,
                                recovery_report=recovery_report,
                                error=error,
                                promo_recovery=promo_recovery,
                            )
                        else:
                            promo_anchor = load_pending_promo_anchor()
                            survey = effective_factory(
                                manager,
                                snapshot,
                                index,
                                name,
                                folder,
                                cancelled,
                                pending_promo_anchor=promo_anchor,
                                initial_promo_anchor=promo_anchor,
                                initial_promo_identity=initial_identity,
                                promo_budget_available=(
                                    promo_recovery is None or not promo_recovery.attempted
                                ),
                            )
                    else:
                        survey = effective_factory(
                            manager,
                            snapshot,
                            index,
                            name,
                            folder,
                            cancelled,
                        )
                    if survey is not None and survey.promo_recovery is not None:
                        # Preserve an already-attempted startup/timeout Back
                        # when the first survey frame merely proves that no
                        # second popup is present.  A new blocked/uncertain
                        # observation still supersedes that prior result.
                        if (
                            promo_recovery is None
                            or not promo_recovery.attempted
                            or survey.promo_recovery.status != PromoRecoveryStatus.NOT_PRESENT
                        ):
                            promo_recovery = survey.promo_recovery
                    if survey is not None:
                        result = ShopSurveyTaskResult(
                            SHOP_SURVEY_TASK,
                            _status_value(survey.status),
                            task_run_id=task_run_id,
                            started_by_run=started_by_run,
                            recovery_report=recovery_report,
                            survey=survey,
                            error=survey.error,
                            promo_recovery=promo_recovery,
                        )
    except Exception as exc:  # noqa: BLE001 - always persist a bounded task result
        error = _merge_error(error, str(exc))
        result = ShopSurveyTaskResult(
            SHOP_SURVEY_TASK,
            "SAFETY_BLOCKED",
            task_run_id=task_run_id,
            started_by_run=started_by_run,
            recovery_report=recovery_report,
            survey=survey,
            error=error,
            promo_recovery=promo_recovery,
        )
    finally:
        if started_by_run and cleanup_owned and not cleanup_attempted:
            cleanup_attempted = True
            try:
                manager.execute(index, "quit", snapshot=snapshot)
                cleanup_succeeded = True
            except Exception as exc:  # noqa: BLE001 - cleanup is a safety boundary
                error = _merge_error(error or result.error, f"Owned-instance cleanup failed: {exc}")
                result = ShopSurveyTaskResult(
                    SHOP_SURVEY_TASK,
                    "CLEANUP_FAILED",
                    task_run_id=task_run_id,
                    started_by_run=started_by_run,
                    recovery_report=recovery_report,
                    survey=survey,
                    error=error,
                    promo_recovery=promo_recovery,
                    cleanup_attempted=cleanup_attempted,
                    cleanup_succeeded=cleanup_succeeded,
                )

        after: dict | None = None
        isolation: list[int] | None = None
        observed_changed_indices: list[int] | None = None
        unrelated_changed_indices: list[int] | None = None
        inventory_status = "unavailable"

        def block_for_isolation(detail: str):
            nonlocal error, result
            error = _merge_error(error or result.error, detail)
            # Do not replace a stronger prior failure (identity, cancellation,
            # uncertain action, cleanup, and persistence failures) merely
            # because the final inventory read cannot prove isolation.
            if result.status in SURVEY_SUCCESS_STATUSES:
                result = ShopSurveyTaskResult(
                    SHOP_SURVEY_TASK,
                    "SAFETY_BLOCKED",
                    task_run_id=task_run_id,
                    started_by_run=started_by_run,
                    recovery_report=recovery_report,
                    survey=result.survey if result.survey is not None else survey,
                    error=error,
                    cleanup_attempted=cleanup_attempted,
                    cleanup_succeeded=cleanup_succeeded,
                    claims=result.claims,
                    journal_rows=result.journal_rows,
                    promo_recovery=(
                        result.promo_recovery
                        if result.promo_recovery is not None
                        else promo_recovery
                    ),
                )

        try:
            live_instances = manager.list_readonly()
            if live_instances is None:
                block_for_isolation("Instance inventory unavailable; isolation was not verified.")
            else:
                # Keep this read separate from validation.  A valid snapshot
                # remains reportable even when the isolation check rejects an
                # unrelated account change.
                after = _state(live_instances)
                inventory_status = "available"
                changed = {
                    changed_index
                    for changed_index in set(before) | set(after)
                    if before.get(changed_index) != after.get(changed_index)
                }
                observed_changed_indices = sorted(changed)
                unrelated_changed_indices = sorted(changed - {index})
                try:
                    isolation = _only_target_changed(before, after, index)
                except (OSError, RuntimeError, ValueError, SafetyError) as exc:
                    block_for_isolation(str(exc))
        except (OSError, RuntimeError, TypeError, ValueError, SafetyError) as exc:
            block_for_isolation(f"Instance inventory unavailable; isolation was not verified: {exc}")

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_run_id": task_run_id,
            "task": SHOP_SURVEY_TASK,
            "label": SHOP_SURVEY_LABEL,
            "scope": SHOP_SURVEY_SCOPE,
            "instance": {"index": index, "name": name},
            "authorized_target": {"index": PHASE6_TARGET[0], "name": PHASE6_TARGET[1]},
            "started_by_run": started_by_run,
            "cleanup_requested": cleanup_owned,
            "cleanup_attempted": cleanup_attempted,
            "cleanup_succeeded": cleanup_succeeded,
            "recovery_report": str(recovery_report) if recovery_report else None,
            "promo_recovery": promo_recovery.as_dict() if promo_recovery else None,
            "before_instances": before,
            "after_instances": after,
            "inventory_status": inventory_status,
            "observed_changed_indices": observed_changed_indices,
            "unrelated_changed_indices": unrelated_changed_indices,
            "isolation_changed_indices": isolation,
            "survey": survey.as_dict() if survey else None,
            "result": result.status,
            "error": error or result.error,
            "claims": [],
            "journal_rows": 0,
        }
        report_path = folder / "report.json"
        persistence_error: str | None = None
        cleanup_error: str | None = None
        try:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            manager.store.finish_task_run(
                task_run_id,
                result.status,
                error=error or result.error or "",
                report_path=str(report_path),
            )
        except Exception as exc:  # noqa: BLE001 - persistence is a safety boundary
            persistence_error = str(exc)
            if started_by_run and not cleanup_attempted:
                cleanup_attempted = True
                try:
                    manager.execute(index, "quit", snapshot=snapshot)
                    cleanup_succeeded = True
                except Exception as cleanup_exc:  # noqa: BLE001 - do not blindly retry
                    cleanup_error = str(cleanup_exc)
            cleanup_already_failed = started_by_run and cleanup_attempted and not cleanup_succeeded
            failure_status = "CLEANUP_FAILED" if cleanup_error or cleanup_already_failed else "PERSISTENCE_FAILED"
            failure_error = _merge_error(error or result.error, persistence_error)
            if cleanup_error:
                failure_error = _merge_error(failure_error, f"Owned-instance cleanup failed: {cleanup_error}")
            result = ShopSurveyTaskResult(
                SHOP_SURVEY_TASK,
                failure_status,
                task_run_id=task_run_id,
                report_path=report_path,
                started_by_run=started_by_run,
                recovery_report=recovery_report,
                survey=survey,
                error=failure_error,
                cleanup_attempted=cleanup_attempted,
                cleanup_succeeded=cleanup_succeeded,
                promo_recovery=promo_recovery,
            )
            failure_report = {
                **report,
                "cleanup_requested": cleanup_owned or cleanup_attempted,
                "cleanup_attempted": cleanup_attempted,
                "cleanup_succeeded": cleanup_succeeded,
                "result": failure_status,
                "error": failure_error,
                "persistence_error": persistence_error,
                "cleanup_error": cleanup_error,
                "cleanup_already_failed": cleanup_already_failed,
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
            result = ShopSurveyTaskResult(
                SHOP_SURVEY_TASK,
                result.status,
                task_run_id=task_run_id,
                report_path=report_path,
                started_by_run=started_by_run,
                recovery_report=recovery_report,
                survey=survey,
                error=error or result.error,
                cleanup_attempted=cleanup_attempted,
                cleanup_succeeded=cleanup_succeeded,
                promo_recovery=promo_recovery,
            )
    return result

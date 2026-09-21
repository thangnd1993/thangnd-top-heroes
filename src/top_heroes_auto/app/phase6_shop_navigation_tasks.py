"""Persistence-safe, observation-only Phase 6 shop navigation task.

The task deliberately does not construct ``FreeRewardExplorer`` or
``JournalledExplorerPort``.  It can survey the verified daily-offer route, but
it cannot claim, purchase, scroll, or spend anything.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from top_heroes_auto.app.diagnostic import _instance, _only_target_changed, _state
from top_heroes_auto.app.phase6_runtime import (
    shop_navigation_factory,
    shop_navigation_profile,
)
from top_heroes_auto.app.recovery_cli import RecoveryFailure, run_home_recovery
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.phase6_shop_navigation import (
    ShopNavigationProfile,
    ShopNavigationResult,
    ShopNavigationStatus,
)
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus

PHASE6_TARGET = (2, "5-Emmmmm")
SHOP_NAVIGATION_TASK = "shop-navigation-survey"
SHOP_NAVIGATION_LABEL = "khảo sát Tiệm / không nhận quà"
SHOP_NAVIGATION_SCOPE = "navigation-only; no claims, purchases, scrolls, or reward journal"
SUCCESS_STATUSES = frozenset({ShopNavigationStatus.SUCCESS.value})


@dataclass(frozen=True)
class ShopNavigationTaskResult:
    task: str
    status: str
    task_run_id: int | None = None
    report_path: Path | None = None
    started_by_run: bool = False
    recovery_report: Path | None = None
    navigation: ShopNavigationResult | None = None
    error: str | None = None
    cleanup_attempted: bool = False
    cleanup_succeeded: bool = False
    claims: tuple[str, ...] = ()
    journal_rows: int = 0

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "label": SHOP_NAVIGATION_LABEL,
            "scope": SHOP_NAVIGATION_SCOPE,
            "result": self.status,
            "task_run_id": self.task_run_id,
            "report": str(self.report_path) if self.report_path else None,
            "started_by_run": self.started_by_run,
            "recovery_report": str(self.recovery_report) if self.recovery_report else None,
            "navigation": self.navigation.as_dict() if self.navigation else None,
            "error": self.error,
            "cleanup_attempted": self.cleanup_attempted,
            "cleanup_succeeded": self.cleanup_succeeded,
            "claims": list(self.claims),
            "journal_rows": self.journal_rows,
        }


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")


def _safe_folder_name(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return value or "account"


def _report_folder(data: Path, name: str) -> Path:
    folder = (
        data
        / "diagnostics"
        / "tasks"
        / SHOP_NAVIGATION_TASK
        / _safe_folder_name(name)
        / _stamp()
    )
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


def _navigation_report(navigation: ShopNavigationResult | None) -> dict | None:
    return navigation.as_dict() if navigation else None


def run_phase6_shop_navigation(
    manager: Manager,
    data: Path,
    index: int,
    name: str,
    *,
    profile: ShopNavigationProfile | None = None,
    navigation_factory: Callable[..., ShopNavigationResult] | None = None,
    recovery_runner: Callable[..., tuple[RecoveryResult, Path, bool]] = run_home_recovery,
    cancelled: Callable[[], bool] = lambda: False,
    cleanup_owned: bool = True,
) -> ShopNavigationTaskResult:
    """Run the bounded daily-offer survey with exact target and persistence guards."""

    if (index, name) != PHASE6_TARGET:
        raise SafetyError("Phase 6 is authorized only for #2 / 5-Emmmmm.")
    target = _instance(manager, index, name)
    queen = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, queen.index).protected:
        raise SafetyError("Queen must remain Protected before Phase 6 navigation.")
    metadata = manager.store.metadata(manager.namespace, target.index)
    if metadata.protected or not metadata.selected:
        raise SafetyError("Phase 6 target must be selected and not Protected.")

    before = _state(manager.list_readonly())
    snapshot = RunSnapshot(manager.namespace, ((index, name),), True)
    folder = _report_folder(data, name)
    task_run_id = manager.store.create_task_run(
        manager.namespace,
        SHOP_NAVIGATION_TASK,
        index,
        name,
    )
    result = ShopNavigationTaskResult(
        SHOP_NAVIGATION_TASK,
        "SAFETY_BLOCKED",
        task_run_id=task_run_id,
    )
    recovery_report: Path | None = None
    started_by_run = False
    cleanup_attempted = False
    cleanup_succeeded = False
    navigation: ShopNavigationResult | None = None
    error: str | None = None
    effective_profile: ShopNavigationProfile | None = profile
    effective_factory = navigation_factory

    try:
        if effective_profile is None:
            effective_profile = shop_navigation_profile()
        if effective_factory is None:
            effective_factory = shop_navigation_factory
        if cancelled():
            result = ShopNavigationTaskResult(
                SHOP_NAVIGATION_TASK,
                ShopNavigationStatus.CANCELLED.value,
                task_run_id=task_run_id,
            )
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
                cleanup_attempted = exc.cleanup_attempted
                cleanup_succeeded = exc.cleanup_succeeded
                recovery_report = exc.report_path
                error = f"Home recovery raised: {exc}"
                result = ShopNavigationTaskResult(
                    SHOP_NAVIGATION_TASK,
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
                )
            except Exception as exc:  # noqa: BLE001 - ownership is unknown; never infer it
                error = f"Home recovery raised: {exc}; ownership and cleanup outcome are unknown"
                result = ShopNavigationTaskResult(
                    SHOP_NAVIGATION_TASK,
                    "HOME_RECOVERY_FAILED",
                    task_run_id=task_run_id,
                    error=error,
                )
            else:
                if recovery.status not in {
                    RecoveryStatus.SUCCESS,
                    RecoveryStatus.ALREADY_HOME,
                }:
                    error = f"GAME_HOME precondition failed: {recovery.status.value}"
                    result = ShopNavigationTaskResult(
                        SHOP_NAVIGATION_TASK,
                        recovery.status.value,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        recovery_report=recovery_report,
                        error=error,
                    )
                elif cancelled():
                    result = ShopNavigationTaskResult(
                        SHOP_NAVIGATION_TASK,
                        ShopNavigationStatus.CANCELLED.value,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        recovery_report=recovery_report,
                        error="Shop navigation cancelled after Home recovery.",
                    )
                else:
                    navigation = effective_factory(
                        manager,
                        snapshot,
                        index,
                        name,
                        effective_profile,
                        folder,
                        cancelled,
                    )
                    status = _status_value(navigation.status)
                    result = ShopNavigationTaskResult(
                        SHOP_NAVIGATION_TASK,
                        status,
                        task_run_id=task_run_id,
                        started_by_run=started_by_run,
                        recovery_report=recovery_report,
                        navigation=navigation,
                        error=navigation.error,
                    )
    except Exception as exc:  # noqa: BLE001 - always persist a bounded task result
        error = _merge_error(error, str(exc))
        result = ShopNavigationTaskResult(
            SHOP_NAVIGATION_TASK,
            "SAFETY_BLOCKED",
            task_run_id=task_run_id,
            started_by_run=started_by_run,
            recovery_report=recovery_report,
            navigation=navigation,
            error=error,
        )
    finally:
        if started_by_run and cleanup_owned and not cleanup_attempted:
            cleanup_attempted = True
            try:
                manager.execute(index, "quit", snapshot=snapshot)
                cleanup_succeeded = True
            except Exception as exc:  # noqa: BLE001 - cleanup is a safety boundary
                error = _merge_error(error or result.error, f"Owned-instance cleanup failed: {exc}")
                result = ShopNavigationTaskResult(
                    SHOP_NAVIGATION_TASK,
                    "CLEANUP_FAILED",
                    task_run_id=task_run_id,
                    started_by_run=started_by_run,
                    recovery_report=recovery_report,
                    navigation=navigation,
                    error=error,
                )

        try:
            after = _state(manager.list_readonly())
            isolation = _only_target_changed(before, after, index)
        except (OSError, RuntimeError, ValueError, SafetyError) as exc:
            after = {}
            isolation = None
            error = _merge_error(error or result.error, str(exc))
            if result.status in SUCCESS_STATUSES:
                result = ShopNavigationTaskResult(
                    SHOP_NAVIGATION_TASK,
                    "SAFETY_BLOCKED",
                    task_run_id=task_run_id,
                    started_by_run=started_by_run,
                    recovery_report=recovery_report,
                    navigation=navigation,
                    error=error,
                )

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_run_id": task_run_id,
            "task": SHOP_NAVIGATION_TASK,
            "label": SHOP_NAVIGATION_LABEL,
            "scope": SHOP_NAVIGATION_SCOPE,
            "instance": {"index": index, "name": name},
            "authorized_target": {"index": PHASE6_TARGET[0], "name": PHASE6_TARGET[1]},
            "started_by_run": started_by_run,
            "cleanup_requested": cleanup_owned,
            "cleanup_attempted": cleanup_attempted,
            "cleanup_succeeded": cleanup_succeeded,
            "recovery_report": str(recovery_report) if recovery_report else None,
            "before_instances": before,
            "after_instances": after,
            "isolation_changed_indices": isolation,
            "profile_available": effective_profile is not None,
            "navigation": _navigation_report(navigation),
            "result": result.status,
            "error": error or result.error,
            "claims": [],
            "journal_rows": 0,
        }
        report_path = folder / "report.json"
        persistence_error: str | None = None
        cleanup_error: str | None = None
        try:
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
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
                except Exception as cleanup_exc:  # noqa: BLE001 - no blind retry
                    cleanup_error = str(cleanup_exc)
            cleanup_already_failed = started_by_run and cleanup_attempted and not cleanup_succeeded
            failure_status = (
                "CLEANUP_FAILED"
                if cleanup_error or cleanup_already_failed
                else "PERSISTENCE_FAILED"
            )
            failure_error = _merge_error(error or result.error, persistence_error)
            if cleanup_error:
                failure_error = _merge_error(
                    failure_error,
                    f"Owned-instance cleanup failed: {cleanup_error}",
                )
            result = ShopNavigationTaskResult(
                SHOP_NAVIGATION_TASK,
                failure_status,
                task_run_id=task_run_id,
                report_path=report_path,
                started_by_run=started_by_run,
                recovery_report=recovery_report,
                navigation=navigation,
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
                "persistence_error": persistence_error,
                "cleanup_error": cleanup_error,
                "cleanup_already_failed": cleanup_already_failed,
            }
            try:
                report_path.write_text(
                    json.dumps(failure_report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
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
            result = ShopNavigationTaskResult(
                SHOP_NAVIGATION_TASK,
                result.status,
                task_run_id=task_run_id,
                report_path=report_path,
                started_by_run=started_by_run,
                recovery_report=recovery_report,
                navigation=navigation,
                error=error or result.error,
                cleanup_attempted=cleanup_attempted,
                cleanup_succeeded=cleanup_succeeded,
            )
    return result

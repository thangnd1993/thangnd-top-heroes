"""Safe Phase 6 free-reward task orchestration.

The runner owns task-run persistence, exact target checks, Home preconditions,
write-ahead reward journaling, evidence reports, and owned-instance cleanup.
Visual profiles and ports are injectable so the safety flow can be tested
without an emulator. Missing visual/postcondition evidence fails before any
gameplay input is dispatched.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from top_heroes_auto.app.diagnostic import _instance, _only_target_changed, _state
from top_heroes_auto.app.phase6_runtime import entry_navigator_factory, reward_port_factory
from top_heroes_auto.app.recovery_cli import run_home_recovery
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.free_rewards import (
    ExplorerLimits,
    ExplorerPort,
    ExplorerResult,
    FreeRewardExplorer,
    RewardEvidence,
)
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.phase6_navigation import NavigationStatus
from top_heroes_auto.automation.phase6_visual import (
    RewardVisualProfile,
    free_recruit_profile,
    vip_reward_profile,
)
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.automation.reward_journal import JournalledExplorerPort, RewardCycle
from top_heroes_auto.vision.models import NormalizedRect, ScreenState, VisualAnchor

PHASE6_TASKS = ("vip-reward", "free-pack", "free-recruit")
PHASE6_TARGET = (2, "5-Emmmmm")
SUCCESS_STATUSES = frozenset({"SUCCESS", "NOT_AVAILABLE"})


@dataclass(frozen=True)
class Phase6TaskResult:
    task: str
    status: str
    task_run_id: int | None = None
    report_path: Path | None = None
    started_by_run: bool = False
    recovery_report: Path | None = None
    explorer: ExplorerResult | None = None
    error: str | None = None
    cleanup_attempted: bool = False
    cleanup_succeeded: bool = False
    claim_verified: bool = False

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "result": self.status,
            "task_run_id": self.task_run_id,
            "report": str(self.report_path) if self.report_path else None,
            "started_by_run": self.started_by_run,
            "recovery_report": str(self.recovery_report) if self.recovery_report else None,
            "explorer": asdict(self.explorer) if self.explorer else None,
            "error": self.error,
            "cleanup_attempted": self.cleanup_attempted,
            "cleanup_succeeded": self.cleanup_succeeded,
            "claim_verified": self.claim_verified,
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


def phase6_profile_folder(task: str) -> Path:
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
    subfolder = {"vip-reward": "vip", "free-recruit": "recruit"}.get(task, "")
    return root / "assets" / "tasks" / "phase6" / subfolder


def _load_profile_details(task: str) -> tuple[RewardVisualProfile | None, str | None]:
    """Load a packaged profile without constructing an incomplete claim profile.

    The packaged VIP/Recruit assets intentionally contain only precondition
    evidence today.  Check for the independent postcondition before calling
    the strict profile factories, so the task can persist a clear
    ``NOT_IMPLEMENTED`` result instead of turning an expected gap into an
    exception-driven safety failure.
    """

    if task not in {"vip-reward", "free-recruit"}:
        return None, None
    folder = phase6_profile_folder(task)
    if not folder.is_dir():
        return None, None
    anchors: dict[str, VisualAnchor] = {}
    prefix = "vip" if task == "vip-reward" else "recruit"
    for metadata_path in sorted(folder.glob("*.json")):
        item = json.loads(metadata_path.read_text(encoding="utf-8"))
        template = metadata_path.parent / item["template"]
        anchor = VisualAnchor(
            item["id"],
            ScreenState(item["state"]),
            template,
            NormalizedRect(*item["expected_region"]),
            float(item["threshold"]),
            bool(item.get("required", False)),
            float(item.get("weight", 1.0)),
            str(item.get("variant", "default")),
        )
        role_name = item["id"].removeprefix(prefix + "-")
        if role_name in {
            "page", "claim", "free", "available", "home", "entry", "post", "cooldown",
            "receipt", "result",
        }:
            anchors[role_name] = anchor
    required = {"page", "claim", "free", "available", "home"}
    if not required <= anchors.keys():
        return None, None
    if "post" not in anchors:
        return (
            None,
            f"Packaged {task} profile has no independently verified postcondition anchor; "
            "task remains NOT_IMPLEMENTED.",
        )
    if task == "vip-reward":
        return vip_reward_profile(anchors), None
    return free_recruit_profile(anchors), None


def _load_profile(task: str) -> RewardVisualProfile | None:
    """Load only the surveyed VIP/Recruit profiles with complete claim evidence."""

    return _load_profile_details(task)[0]


def _cycle(task: str, screen, reward: RewardEvidence) -> RewardCycle:
    # Never derive a cycle from a screenshot hash, boot ID, or guessed reset.
    return RewardCycle(f"phase6:{task}:conservative-opportunity", reward.available_anchor)


def _report_folder(data: Path, task: str, name: str) -> Path:
    folder = data / "diagnostics" / "tasks" / task / _safe_folder_name(name) / _stamp()
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def run_free_reward_task(
    manager: Manager,
    data: Path,
    index: int,
    name: str,
    task: str,
    *,
    profiles: Mapping[str, RewardVisualProfile] | None = None,
    port_factory: Callable[..., ExplorerPort] | None = None,
    entry_navigator: Callable[..., object] | None = None,
    recovery_runner: Callable[..., tuple[RecoveryResult, Path, bool]] = run_home_recovery,
    limits: ExplorerLimits | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    cleanup_owned: bool = True,
) -> Phase6TaskResult:
    """Run one Phase 6 task with no claim unless all safety evidence exists."""

    if task not in PHASE6_TASKS:
        raise ValueError(f"Unsupported Phase 6 task: {task}")
    if (index, name) != PHASE6_TARGET:
        raise SafetyError("Phase 6 is authorized only for #2 / 5-Emmmmm.")

    target = _instance(manager, index, name)
    queen = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, queen.index).protected:
        raise SafetyError("Queen must remain Protected before Phase 6 automation.")
    metadata = manager.store.metadata(manager.namespace, target.index)
    if metadata.protected or not metadata.selected:
        raise SafetyError("Phase 6 target must be selected and not Protected.")

    before = _state(manager.list_readonly())
    snapshot = RunSnapshot(manager.namespace, ((index, name),), True)
    folder = _report_folder(data, task, name)
    task_run_id = manager.store.create_task_run(manager.namespace, task, index, name)
    profile: RewardVisualProfile | None = None
    result = Phase6TaskResult(task, "SAFETY_BLOCKED", task_run_id=task_run_id)
    recovery_report: Path | None = None
    started_by_run = False
    cleanup_attempted = False
    cleanup_succeeded = False
    error: str | None = None
    explorer_result: ExplorerResult | None = None
    effective_port_factory = port_factory
    effective_entry_navigator = entry_navigator
    profile_error: str | None = None
    if profiles is None:
        effective_port_factory = effective_port_factory or reward_port_factory
        effective_entry_navigator = effective_entry_navigator or entry_navigator_factory

    try:
        if profiles is not None:
            profile = (profiles or {}).get(task)
        else:
            profile, profile_error = _load_profile_details(task)
        if profile is None:
            error = profile_error or "No independently verified Phase 6 visual profile is available."
            result = Phase6TaskResult(
                task,
                "NOT_IMPLEMENTED",
                task_run_id=task_run_id,
                error=error,
            )
        elif effective_port_factory is None or effective_entry_navigator is None:
            error = "Home-to-task entry navigation is not wired; no gameplay action dispatched."
            result = Phase6TaskResult(
                task,
                "NOT_IMPLEMENTED",
                task_run_id=task_run_id,
                error=error,
            )
        elif profile.anchor_map.get("post") is None:
            error = "No independently verified post-claim anchor is available; claim blocked."
            result = Phase6TaskResult(
                task,
                "NOT_IMPLEMENTED",
                task_run_id=task_run_id,
                error=error,
            )
        elif cancelled():
            result = Phase6TaskResult(task, "CANCELLED", task_run_id=task_run_id)
        else:
            recovery, recovery_report, started_by_run = recovery_runner(
                manager,
                data,
                index,
                name,
                cancelled=cancelled,
                cleanup_owned=False,
            )
            if recovery.status not in {RecoveryStatus.SUCCESS, RecoveryStatus.ALREADY_HOME}:
                error = f"GAME_HOME precondition failed: {recovery.status.value}"
                result = Phase6TaskResult(
                    task,
                    recovery.status.value,
                    task_run_id=task_run_id,
                    recovery_report=recovery_report,
                    started_by_run=started_by_run,
                    error=error,
                )
            elif cancelled():
                result = Phase6TaskResult(
                    task,
                    "CANCELLED",
                    task_run_id=task_run_id,
                    recovery_report=recovery_report,
                    started_by_run=started_by_run,
                    error="Phase 6 cancelled after Home recovery.",
                )
            else:
                navigation = effective_entry_navigator(
                    manager, snapshot, index, name, profile, folder, cancelled
                )
                navigation_status = getattr(navigation, "status", None)
                navigation_status = getattr(navigation_status, "value", str(navigation_status))
                if navigation_status != NavigationStatus.SUCCESS.value:
                    error = getattr(navigation, "error", None) or "Entry navigation did not reach the task page."
                    result = Phase6TaskResult(
                        task,
                        navigation_status or "NOT_IMPLEMENTED",
                        task_run_id=task_run_id,
                        recovery_report=recovery_report,
                        started_by_run=started_by_run,
                        error=error,
                    )
                elif cancelled():
                    result = Phase6TaskResult(
                        task,
                        "CANCELLED",
                        task_run_id=task_run_id,
                        recovery_report=recovery_report,
                        started_by_run=started_by_run,
                        error="Phase 6 cancelled before reward observation.",
                    )
                else:
                    port = effective_port_factory(manager, snapshot, index, name, profile, folder)
                    journal = JournalledExplorerPort(
                        port,
                        manager.store,
                        task_run_id,
                        index,
                        name,
                        lambda screen, reward: _cycle(task, screen, reward),
                    )
                    explorer_result = FreeRewardExplorer(limits).run(journal, index, name, cancelled)
                    result = Phase6TaskResult(
                        task,
                        explorer_result.status,
                        task_run_id=task_run_id,
                        recovery_report=recovery_report,
                        started_by_run=started_by_run,
                        explorer=explorer_result,
                        error=explorer_result.error,
                        claim_verified=bool(explorer_result.claimed),
                    )
    except Exception as exc:  # noqa: BLE001 - task failures must be persisted and cleaned up
        error = str(exc)
        result = Phase6TaskResult(
            task,
            "SAFETY_BLOCKED" if explorer_result is None else explorer_result.status,
            task_run_id=task_run_id,
            recovery_report=recovery_report,
            started_by_run=started_by_run,
            explorer=explorer_result,
            error=error,
        )
    finally:
        if started_by_run and cleanup_owned:
            cleanup_attempted = True
            try:
                manager.execute(index, "quit", snapshot=snapshot)
                cleanup_succeeded = True
            except Exception as exc:  # noqa: BLE001 - cleanup is a safety boundary
                error = str(exc)
                if result.status in SUCCESS_STATUSES:
                    result = Phase6TaskResult(
                        task,
                        "CLEANUP_FAILED",
                        task_run_id=task_run_id,
                        recovery_report=recovery_report,
                        started_by_run=started_by_run,
                        explorer=explorer_result,
                        error=error,
                    )
        try:
            after = _state(manager.list_readonly())
            isolation = _only_target_changed(before, after, index)
        except (OSError, RuntimeError, ValueError, SafetyError) as exc:
            after = {}
            isolation = None
            error = str(exc)
            if result.status in SUCCESS_STATUSES:
                result = Phase6TaskResult(
                    task,
                    "SAFETY_BLOCKED",
                    task_run_id=task_run_id,
                    recovery_report=recovery_report,
                    started_by_run=started_by_run,
                    explorer=explorer_result,
                    error=error,
                )
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_run_id": task_run_id,
            "task": task,
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
            "profile_available": profile is not None,
            "entry_available": effective_entry_navigator is not None,
            "postcondition_available": bool(profile and profile.anchor_map.get("post")),
            "result": result.status,
            "error": error or result.error,
            "explorer": asdict(explorer_result) if explorer_result else None,
            "claim_verified": bool(explorer_result and explorer_result.claimed),
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
        except Exception as persistence_exc:  # noqa: BLE001 - persistence failure is a safety boundary
            persistence_error = str(persistence_exc)
            cleanup_error = None
            if started_by_run and not cleanup_attempted:
                cleanup_attempted = True
                try:
                    manager.execute(index, "quit", snapshot=snapshot)
                    cleanup_succeeded = True
                except Exception as cleanup_exc:  # noqa: BLE001 - do not retry uncertain cleanup
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
            elif cleanup_already_failed:
                failure_error = _merge_error(
                    failure_error,
                    "Owned-instance cleanup failed before persistence.",
                )
            result = Phase6TaskResult(
                task,
                failure_status,
                task_run_id=task_run_id,
                report_path=report_path,
                started_by_run=started_by_run,
                recovery_report=recovery_report,
                explorer=explorer_result,
                error=failure_error,
                cleanup_attempted=cleanup_attempted,
                cleanup_succeeded=cleanup_succeeded,
                claim_verified=bool(explorer_result and explorer_result.claimed),
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
            }
            try:
                report_path.write_text(
                    json.dumps(failure_report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:  # noqa: BLE001 - report rewrite is best effort
                pass
            try:
                manager.store.finish_task_run(
                    task_run_id,
                    failure_status,
                    error=failure_error,
                    report_path=str(report_path),
                )
            except Exception:  # noqa: BLE001 - preserve the returned safety result
                pass
        else:
            result = Phase6TaskResult(
                task,
                result.status,
                task_run_id=task_run_id,
                report_path=report_path,
                started_by_run=started_by_run,
                recovery_report=recovery_report,
                explorer=explorer_result,
                error=error or result.error,
                cleanup_attempted=cleanup_attempted,
                cleanup_succeeded=cleanup_succeeded,
                claim_verified=bool(explorer_result and explorer_result.claimed),
            )
    return result


def _home_verified(recovery_runner, manager, data, index, name, cancelled) -> bool:
    recovery, _, _ = recovery_runner(
        manager,
        data,
        index,
        name,
        cancelled=cancelled,
        cleanup_owned=False,
    )
    return recovery.status in {RecoveryStatus.SUCCESS, RecoveryStatus.ALREADY_HOME}


def _sequence_error(existing: str | None, detail: str) -> str:
    if not existing:
        return detail
    if detail in existing:
        return existing
    return f"{existing}; {detail}"


def _persist_sequence_result(
    manager: Manager,
    result: Phase6TaskResult,
    *,
    status: str | None = None,
    error: str | None = None,
    cleanup_succeeded: bool | None = None,
    updates: Mapping[str, object] | None = None,
) -> Phase6TaskResult:
    """Persist sequence-owned status changes to the task row and its report."""

    updated = replace(
        result,
        status=status or result.status,
        error=error if error is not None else result.error,
        cleanup_succeeded=(
            cleanup_succeeded if cleanup_succeeded is not None else result.cleanup_succeeded
        ),
    )
    if result.report_path is not None:
        try:
            payload = json.loads(result.report_path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            payload = {}
        payload.update(updates or {})
        payload["result"] = updated.status
        payload["error"] = updated.error
        payload["cleanup_attempted"] = updated.cleanup_attempted
        payload["cleanup_succeeded"] = updated.cleanup_succeeded
        result.report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if result.task_run_id is not None:
        manager.store.finish_task_run(
            result.task_run_id,
            updated.status,
            error=updated.error or "",
            report_path=str(result.report_path) if result.report_path else "",
        )
    return updated


def run_free_reward_sequence(
    manager: Manager,
    data: Path,
    index: int,
    name: str,
    tasks: tuple[str, ...] = PHASE6_TASKS,
    **kwargs,
) -> list[Phase6TaskResult]:
    """Run a bounded sequence, requiring verified Home between task runs."""

    if not tasks or any(task not in PHASE6_TASKS for task in tasks):
        raise ValueError("Sequence contains an unsupported or empty Phase 6 task list.")
    results: list[Phase6TaskResult] = []
    task_kwargs = dict(kwargs)
    task_kwargs["cleanup_owned"] = False
    recovery_runner = kwargs.get("recovery_runner", run_home_recovery)
    cancelled = kwargs.get("cancelled", lambda: False)
    sequence_before = _state(manager.list_readonly())
    owned_by_sequence = False
    sequence_cleanup_attempted = False
    sequence_cleanup_succeeded = False
    sequence_error: str | None = None
    sequence_after: dict = {}
    sequence_isolation: list[int] | None = None

    try:
        for position, task in enumerate(tasks):
            try:
                result = run_free_reward_task(
                    manager,
                    data,
                    index,
                    name,
                    task,
                    **task_kwargs,
                )
            except Exception as exc:  # noqa: BLE001 - preserve a persisted sequence failure
                # A task should normally persist its own failure. Preserve a
                # bounded sequence result if an injected adapter still escapes.
                result = Phase6TaskResult(task, "SAFETY_BLOCKED", error=str(exc))
            results.append(result)
            owned_by_sequence = owned_by_sequence or result.started_by_run
            sequence_cleanup_attempted = sequence_cleanup_attempted or result.cleanup_attempted
            if result.status not in SUCCESS_STATUSES:
                break
            if position == len(tasks) - 1:
                continue

            try:
                recovery, recovery_report, recovery_started = recovery_runner(
                    manager,
                    data,
                    index,
                    name,
                    cancelled=cancelled,
                    cleanup_owned=False,
                )
                owned_by_sequence = owned_by_sequence or recovery_started
            except Exception as exc:  # noqa: BLE001 - recovery failures must stop the sequence
                recovery = None
                recovery_report = None
                recovery_started = False
                sequence_error = f"Between-task Home recovery raised: {exc}"

            if recovery is None or recovery.status not in {
                RecoveryStatus.SUCCESS,
                RecoveryStatus.ALREADY_HOME,
            }:
                if recovery is not None:
                    sequence_error = (
                        f"Between-task Home recovery failed: {recovery.status.value}"
                    )
                results[-1] = _persist_sequence_result(
                    manager,
                    results[-1],
                    status="HOME_RECOVERY_FAILED",
                    error=_sequence_error(results[-1].error, sequence_error or "Home recovery failed."),
                    updates={
                        "between_task_home_recovery": {
                            "status": recovery.status.value if recovery is not None else None,
                            "report": str(recovery_report) if recovery_report else None,
                            "started_by_run": recovery_started,
                        }
                    },
                )
                break
    finally:
        if owned_by_sequence and not sequence_cleanup_attempted:
            sequence_cleanup_attempted = True
            try:
                manager.execute(
                    index,
                    "quit",
                    snapshot=RunSnapshot(manager.namespace, ((index, name),), True),
                )
                sequence_cleanup_succeeded = True
            except Exception as exc:  # noqa: BLE001 - owned cleanup must always be attempted
                sequence_error = _sequence_error(sequence_error, f"Owned-instance cleanup failed: {exc}")
        elif owned_by_sequence:
            sequence_cleanup_succeeded = all(
                item.cleanup_succeeded
                for item in results
                if item.started_by_run and item.cleanup_attempted
            )

        try:
            sequence_after = _state(manager.list_readonly())
            sequence_isolation = _only_target_changed(sequence_before, sequence_after, index)
        except (OSError, RuntimeError, ValueError, SafetyError) as exc:
            sequence_error = _sequence_error(sequence_error, f"Sequence isolation check failed: {exc}")

        if results:
            final_status = results[-1].status
            if owned_by_sequence and not sequence_cleanup_succeeded:
                final_status = "CLEANUP_FAILED"
            if sequence_isolation is None:
                final_status = "ISOLATION_FAILED"
            results[-1] = _persist_sequence_result(
                manager,
                results[-1],
                status=final_status,
                error=sequence_error or results[-1].error,
                cleanup_succeeded=sequence_cleanup_succeeded or results[-1].cleanup_succeeded,
                updates={
                    "sequence_tasks": list(tasks),
                    "sequence_cleanup_requested": owned_by_sequence,
                    "sequence_cleanup_attempted": sequence_cleanup_attempted,
                    "sequence_cleanup_succeeded": sequence_cleanup_succeeded,
                    "sequence_before_instances": sequence_before,
                    "sequence_after_instances": sequence_after,
                    "sequence_isolation_changed_indices": sequence_isolation,
                },
            )
    return results

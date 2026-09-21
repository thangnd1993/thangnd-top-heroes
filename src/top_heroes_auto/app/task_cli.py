"""Scoped Phase 5 gameplay diagnostics."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.diagnostic import _instance, _manager, _only_target_changed, _state
from top_heroes_auto.app.free_reward_tasks import (
    PHASE6_TASKS,
    SUCCESS_STATUSES,
    run_free_reward_sequence,
    run_free_reward_task,
)
from top_heroes_auto.app.phase6_runtime import promo_recovery_factory
from top_heroes_auto.app.phase6_shop_navigation_tasks import (
    SHOP_NAVIGATION_TASK,
    run_phase6_shop_navigation,
)
from top_heroes_auto.app.recovery_cli import run_home_recovery
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.actions import SafeInputService
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.idle_reward import (
    IdleRewardObservation,
    IdleRewardResult,
    IdleRewardStatus,
    IdleRewardTask,
)
from top_heroes_auto.automation.recovery import RecoveryStatus
from top_heroes_auto.vision.detector import ScreenDetector
from top_heroes_auto.vision.resources import idle_reward_template_folder
from top_heroes_auto.vision.screenshot import ScreenshotService

log = logging.getLogger("top_heroes_auto")
TASK_NAME = "idle-reward"


class DiagnosticIdleRewardPort:
    def __init__(
        self,
        manager: Manager,
        snapshot: RunSnapshot,
        index: int,
        name: str,
        folder: Path,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.folder = folder
        self.detector = ScreenDetector.from_folder(idle_reward_template_folder())
        self.input = SafeInputService(index, name, self._dispatch)
        self.verified_identity: tuple[str, str] | None = None

    def _dispatch(self, action: str, values: tuple[int, ...]):
        self.manager.execute(self.index, action, values=values, snapshot=self.snapshot)

    def observe(self, tag: str) -> IdleRewardObservation:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        identity = target.serial, target.boot_id
        if self.verified_identity is not None and identity != self.verified_identity:
            raise SafetyError("ADB target identity changed during Idle Reward diagnostic.")
        self.verified_identity = identity

        def exact_capture(serial: str) -> bytes:
            if serial != target.serial:
                raise SafetyError("Idle Reward capture target changed unexpectedly.")
            return payload

        screen = ScreenshotService(exact_capture).take(target, self.folder, tag)
        detection = self.detector.detect(screen)
        log.info(
            "[%s / #%s] Idle Reward state: %s confidence=%.3f",
            self.name,
            self.index,
            detection.state.value,
            detection.confidence,
        )
        return IdleRewardObservation(detection, screen.source_image, target.serial)

    def tap(self, detection, anchor_id: str) -> None:
        self.input.tap_detected_target(detection, anchor_id)

    def back(self, detection) -> None:
        self.input.key_back(detection)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")


def run_idle_reward_diagnostic(
    manager: Manager,
    data: Path,
    index: int,
    name: str,
    *,
    cancelled=lambda: False,
    task: IdleRewardTask | None = None,
) -> tuple[IdleRewardResult, Path, bool, int]:
    target = _instance(manager, index, name)
    queen = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, queen.index).protected:
        raise SafetyError("Queen must remain Protected before Idle Reward automation.")
    metadata = manager.store.metadata(manager.namespace, target.index)
    if metadata.protected or not metadata.selected:
        raise SafetyError("Idle Reward target must be selected and not Protected.")

    before = _state(manager.list_readonly())
    snapshot = RunSnapshot(manager.namespace, ((index, name),), True)
    folder = data / "diagnostics" / "tasks" / TASK_NAME / name / _stamp()
    folder.mkdir(parents=True, exist_ok=False)
    task_run_id = manager.store.create_task_run(manager.namespace, TASK_NAME, index, name)
    started_by_run = False
    result = IdleRewardResult(IdleRewardStatus.ACTION_FAILED, error="Precondition did not run.")
    recovery_report: Path | None = None
    cleanup_error = ""
    log.info("[%s / #%s] Idle Reward: bắt đầu", name, index)
    try:
        recovery, recovery_report, started_by_run = run_home_recovery(
            manager,
            data,
            index,
            name,
            cancelled=cancelled,
            cleanup_owned=False,
        )
        if recovery.status not in {
            RecoveryStatus.SUCCESS,
            RecoveryStatus.ALREADY_HOME,
            RecoveryStatus.UNKNOWN_SCREEN,
        }:
            status = (
                IdleRewardStatus.CANCELLED
                if recovery.status == RecoveryStatus.CANCELLED
                else IdleRewardStatus.ACTION_FAILED
            )
            result = IdleRewardResult(
                status,
                adb_target=recovery.adb_target,
                error=f"GAME_HOME precondition failed: {recovery.status.value}: {recovery.error or ''}".strip(),
            )
        else:
            port = DiagnosticIdleRewardPort(manager, snapshot, index, name, folder)
            result = (task or IdleRewardTask()).run(port, cancelled)
    finally:
        if started_by_run:
            try:
                manager.execute(index, "quit", snapshot=snapshot)
            except RuntimeError as exc:
                cleanup_error = str(exc)

    after = _state(manager.list_readonly())
    isolation_changes = _only_target_changed(before, after, index)
    if cleanup_error and result.status in {IdleRewardStatus.SUCCESS, IdleRewardStatus.NOT_AVAILABLE}:
        result.status = IdleRewardStatus.CLEANUP_FAILED
        result.error = cleanup_error
        result.cleanup_succeeded = False
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_run_id": task_run_id,
        "task": TASK_NAME,
        "instance": {"index": index, "name": name},
        "started_by_run": started_by_run,
        "lifecycle_cleanup_error": cleanup_error or None,
        "recovery_report": str(recovery_report) if recovery_report else None,
        "isolation_changed_indices": isolation_changes,
        "before_instances": before,
        "after_instances": after,
        **result.as_dict(),
    }
    report_path = folder / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    manager.store.finish_task_run(
        task_run_id,
        result.status.value,
        error=result.error or "",
        report_path=str(report_path),
    )
    log.info("[%s / #%s] Idle Reward: %s", name, index, result.status.value)
    return result, report_path, started_by_run, task_run_id


def parser():
    root = argparse.ArgumentParser(prog="TopHeroesAutoManager.exe task")
    commands = root.add_subparsers(dest="command", required=True)
    idle = commands.add_parser(TASK_NAME)
    idle.add_argument("--index", type=int, required=True)
    idle.add_argument("--name", required=True)
    for task_name in PHASE6_TASKS:
        phase6 = commands.add_parser(task_name)
        phase6.add_argument("--index", type=int, required=True)
        phase6.add_argument("--name", required=True)
    sequence = commands.add_parser("free-rewards")
    sequence.add_argument("--index", type=int, required=True)
    sequence.add_argument("--name", required=True)
    sequence.add_argument("--tasks", nargs="+", choices=PHASE6_TASKS, default=list(PHASE6_TASKS))
    survey = commands.add_parser(
        SHOP_NAVIGATION_TASK,
        help="khảo sát Tiệm / không nhận quà (navigation-only)",
    )
    survey.add_argument("--index", type=int, required=True)
    survey.add_argument("--name", required=True)
    return root


def main(argv: list[str], data: Path) -> int:
    args = parser().parse_args(argv)
    manager = _manager(data)
    if args.command == TASK_NAME:
        result, report, started, task_run_id = run_idle_reward_diagnostic(
            manager,
            data,
            args.index,
            args.name,
        )
        output = {
            **result.as_dict(),
            "task_run_id": task_run_id,
            "started_by_run": started,
            "report": str(report),
        }
        print(json.dumps(output, ensure_ascii=True, indent=2))
        return 0 if result.status in {IdleRewardStatus.SUCCESS, IdleRewardStatus.NOT_AVAILABLE} else 2
    if args.command in PHASE6_TASKS:
        result = run_free_reward_task(manager, data, args.index, args.name, args.command)
        print(json.dumps(result.as_dict(), ensure_ascii=True, indent=2))
        return 0 if result.status in SUCCESS_STATUSES else 2
    if args.command == SHOP_NAVIGATION_TASK:
        result = run_phase6_shop_navigation(
            manager,
            data,
            args.index,
            args.name,
            promo_recovery_factory=promo_recovery_factory,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=True, indent=2))
        return 0 if result.status == "SUCCESS" else 2
    results = run_free_reward_sequence(
        manager,
        data,
        args.index,
        args.name,
        tuple(args.tasks),
    )
    print(json.dumps({"results": [result.as_dict() for result in results]}, ensure_ascii=True, indent=2))
    return 0 if results and all(result.status in SUCCESS_STATUSES for result in results) else 2

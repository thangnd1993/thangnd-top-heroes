"""Scoped Phase 5 gameplay diagnostics."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.automation_ownership import exclusive_automation
from top_heroes_auto.app.diagnostic import _instance, _manager, _only_target_changed, _state
from top_heroes_auto.app.free_reward_tasks import (
    PHASE6_TASKS,
    SUCCESS_STATUSES,
    run_free_reward_task,
)
from top_heroes_auto.app.phase6_runtime import promo_recovery_factory, shop_survey_factory
from top_heroes_auto.app.phase6_shop_navigation_tasks import (
    SHOP_NAVIGATION_TASK,
    run_phase6_shop_navigation,
)
from top_heroes_auto.app.phase6_shop_survey_tasks import (
    SHOP_SURVEY_TASK,
    SURVEY_SUCCESS_STATUSES,
    run_phase6_shop_survey,
)
from top_heroes_auto.app.phase6_vip_survey_tasks import (
    VIP_SURVEY_LABEL,
    VIP_SURVEY_TASK,
    run_phase6_vip_survey,
)
from top_heroes_auto.app.recovery_cli import RecoveryFailure, run_home_recovery
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.actions import SafeInputService
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError, bound_snapshot
from top_heroes_auto.automation.idle_reward import (
    IdleRewardObservation,
    IdleRewardResult,
    IdleRewardStatus,
    IdleRewardTask,
)
from top_heroes_auto.automation.recovery import RecoveryStatus
from top_heroes_auto.vision.idle_detector import IdleRewardDetector
from top_heroes_auto.vision.models import ScreenState
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
        claim_id: int | None = None,
        task_run_id: int | None = None,
        promo_budget_available: bool = True,
        cancelled=lambda: False,
        require_known_promo: bool = False,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.folder = folder
        self.detector = IdleRewardDetector()
        self.input = SafeInputService(index, name, self._dispatch)
        self.verified_identity: tuple[str, str] | None = None
        self.claim_id = claim_id
        self.task_run_id = task_run_id
        self.promo_budget_available = promo_budget_available
        self.promo_result = None
        self.observed_target = None
        self.claim_pending = False
        self.latest_detection = None
        self.latest_screen = None
        self.accumulation_proof = {}
        self.entry_qualified = False
        self.cancelled = cancelled
        self.require_known_promo = require_known_promo

    def _dispatch(self, action: str, values: tuple[int, ...]):
        self.manager.execute(
            self.index, action, values=values, snapshot=self.snapshot,
            observed_target=self.observed_target,
            before_input=(lambda: self.manager.store.mark_reward_dispatch(self.claim_id, self.task_run_id))
            if self.claim_pending else None,
        )

    def observe(self, tag: str) -> IdleRewardObservation:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        identity = target.serial, target.boot_id
        if self.verified_identity is not None and identity != self.verified_identity:
            raise SafetyError("ADB target identity changed during Idle Reward diagnostic.")
        self.verified_identity = identity
        self.observed_target = target

        def exact_capture(serial: str) -> bytes:
            if serial != target.serial:
                raise SafetyError("Idle Reward capture target changed unexpectedly.")
            return payload

        screen = ScreenshotService(exact_capture).take(target, self.folder, tag)
        detection = self.detector.detect(screen)
        self.latest_detection = detection
        self.latest_screen = screen
        if detection.state == ScreenState.UNKNOWN and self.promo_budget_available and tag.endswith('-game-home'):
            from top_heroes_auto.app.phase6_runtime import pending_promo_anchor
            from top_heroes_auto.vision.exploration import unique_current_anchor

            if unique_current_anchor(screen, pending_promo_anchor()).matched:
                self.promo_budget_available = False
                self.promo_result = promo_recovery_factory(
                    self.manager, self.snapshot, self.index, self.name, self.folder,
                    cancelled=self.cancelled,
                    expected_transport=identity,
                )
                if self.promo_result.status.value != 'SUCCESS':
                    raise SafetyError('Known promo recovery did not verify Home; no retry.')
                self.require_known_promo = False
                return self.observe(tag + '-after-known-promo')
        if self.require_known_promo:
            raise SafetyError('Recovery timeout is not the qualified known promo; no input.')
        log.info(
            "[%s / #%s] Idle Reward state: %s confidence=%.3f",
            self.name,
            self.index,
            detection.state.value,
            detection.confidence,
        )
        return IdleRewardObservation(detection, screen.source_image, target.serial)

    def tap(self, detection, anchor_id: str) -> None:
        if detection is not self.latest_detection or self.observed_target is None:
            raise SafetyError('Idle input requires the current observation, not cached evidence.')
        if anchor_id in {'idle-entry-available', 'idle-entry-available-open'}:
            self.entry_qualified = detection.state == ScreenState.IDLE_ENTRY_AVAILABLE
        if anchor_id == 'idle-claim-button':
            if self.claim_id is None or self.task_run_id is None:
                raise SafetyError('Idle claim requires a durable dispatch reservation.')
            if self.accumulation_proof:
                if not self.entry_qualified or detection.state != ScreenState.IDLE_REWARD_CLAIMABLE:
                    raise SafetyError('New accumulation requires current attention entry and green reward panel.')
                proof = dict(method='original_empty_then_current_attention_and_green_accumulation',
                             **self.accumulation_proof, current_capture=str(self.latest_screen.source_image),
                             current_timestamp=self.latest_screen.timestamp)
                with self.manager.store.connect() as db:
                    changed = db.execute('UPDATE reward_claims SET before_evidence=? WHERE id=? AND task_run_id=? '
                        "AND status='RESERVED' AND dispatch_state='NOT_DISPATCHED'",
                        (json.dumps(proof),self.claim_id,self.task_run_id)).rowcount
                    if changed != 1:
                        raise SafetyError('Idle accumulation reservation changed; no input.')
        self.claim_pending = anchor_id == 'idle-claim-button'
        try:
            self.input.tap_detected_target(detection, anchor_id)
        finally:
            self.claim_pending = False

    def back(self, detection) -> None:
        if detection is not self.latest_detection or self.observed_target is None:
            raise SafetyError('Idle Back requires the current observation.')
        self.input.key_back(detection)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")


@exclusive_automation
def run_idle_reward_diagnostic(
    manager: Manager,
    data: Path,
    index: int,
    name: str,
    *,
    cancelled=lambda: False,
    task: IdleRewardTask | None = None,
    session=None,
) -> tuple[IdleRewardResult, Path, bool, int]:
    if session is not None:
        if session.manager is not manager or session.index != index:
            raise SafetyError('Idle session target mismatch.')
        session.check()
    target = _instance(manager, index, name)
    queen = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, queen.index).protected:
        raise SafetyError("Queen must remain Protected before Idle Reward automation.")
    metadata = manager.store.metadata(manager.namespace, target.index)
    if metadata.protected or not metadata.selected:
        raise SafetyError("Idle Reward target must be selected and not Protected.")

    before = _state(manager.list_readonly())
    snapshot = session.snapshot if session is not None else bound_snapshot(
        manager.store, manager.namespace, ((index, name),), True)
    folder = data / "diagnostics" / "tasks" / TASK_NAME / f"{index}-{dict(snapshot.identities)[index]}" / _stamp()
    folder.mkdir(parents=True, exist_ok=False)
    task_run_id = manager.store.create_task_run(manager.namespace, TASK_NAME, index, name)
    started_by_run = False
    result = IdleRewardResult(
        IdleRewardStatus.ACTION_FAILED,
        error="Precondition did not run.",
        recovery_result="PENDING",
    )
    initial_recovery_result = "NOT_STARTED"
    recovery_report: Path | None = None
    cleanup_error = ""
    claim_id = None
    port = None
    log.info("[%s / #%s] Idle Reward: bắt đầu", name, index)
    try:
        from top_heroes_auto.app.idle_opportunity import opportunity

        stable_id = dict(snapshot.identities)[index]
        cycle, accumulation_proof = opportunity(manager.store, manager.namespace, index, stable_id)
        claim_id = manager.store.reserve_reward_claim(
            task_run_id, 'idle-reward', cycle,
            json.dumps({'task_run_id': task_run_id, 'scope': 'pre-dispatch task lock',
                        'accumulation_proof': accumulation_proof}),
            expected_instance=(index, name), not_dispatched=True,
        )
        if session is not None:
            recovery, recovery_report, _ = session.recover()
        else:
            recovery, recovery_report, started_by_run = run_home_recovery(
                manager, data, index, name, cancelled=cancelled, cleanup_owned=False,
            )
        initial_recovery_result = (
            "SUCCESS"
            if recovery.status in {RecoveryStatus.SUCCESS, RecoveryStatus.ALREADY_HOME}
            else recovery.status.value
        )
        if recovery.status not in {
            RecoveryStatus.SUCCESS,
            RecoveryStatus.ALREADY_HOME,
            RecoveryStatus.UNKNOWN_SCREEN,
            RecoveryStatus.LOADING_TIMEOUT,
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
                recovery_result="FAILED",
            )
        else:
            port = DiagnosticIdleRewardPort(
                manager, snapshot, index, name, folder, claim_id, task_run_id,
                promo_budget_available='back_known_promo' not in recovery.actions,
                cancelled=cancelled,
                require_known_promo=recovery.status == RecoveryStatus.LOADING_TIMEOUT,
            )
            port.accumulation_proof = accumulation_proof
            if recovery.adb_target and recovery.boot_id:
                port.verified_identity = (recovery.adb_target, recovery.boot_id)
            result = (task or IdleRewardTask()).run(port, cancelled)
            # Keep the initial Home-recovery outcome even if the later task
            # exits before it records a recovery field (for example, when the
            # portal detector safely returns UNKNOWN_SCREEN). A later recovery
            # result written by the task remains authoritative.
            if result.recovery_result in {"NOT_STARTED", "PENDING"}:
                result.recovery_result = initial_recovery_result
    except RecoveryFailure as exc:
        initial_recovery_result = "FAILED"
        started_by_run = session is None and exc.started_by_run and not exc.cleanup_attempted
        recovery_report = exc.report_path
        result = IdleRewardResult(
            IdleRewardStatus.ACTION_FAILED,
            error=str(exc),
            recovery_result="FAILED",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        if result.postcondition_result == "VERIFIED":
            result.status = IdleRewardStatus.SUCCESS_WITH_RECOVERY_WARNING
            result.recovery_result = "FAILED"
            result.error = f"Claim verified; post-claim recovery failed: {exc}"
        elif result.claim_dispatched:
            result.status = IdleRewardStatus.ACTION_RESULT_UNCERTAIN
            result.claim_result = "UNCERTAIN"
            result.postcondition_result = "FAILED"
            result.recovery_result = "UNKNOWN"
            result.error = str(exc)
        else:
            result = IdleRewardResult(
                IdleRewardStatus.ACTION_FAILED,
                error=str(exc),
                recovery_result="FAILED",
            )
    finally:
        try:
            if claim_id is not None:
                rows = manager.store.reward_claims(manager.namespace, index)
                row = next(item for item in rows if item['id'] == claim_id)
                if row['dispatch_state'] == 'NOT_DISPATCHED':
                    result.claim_dispatched = False
                    manager.store.release_undispatched_reward(
                        claim_id, task_run_id,
                        json.dumps({'reason': 'claim transport not entered', 'result': result.as_dict()}),
                    )
                    result.journal_result = 'RELEASED'
                elif result.claim_dispatched:
                    claimed = [s for s in result.steps if s.state == ScreenState.IDLE_REWARD_CLAIMED]
                    dispatch = [s.number for s in result.steps if s.action == 'claim_once']
                    if len(dispatch) == 1 and any(s.number > dispatch[0] for s in claimed):
                        manager.store.verify_reward_claim(claim_id, task_run_id, json.dumps(result.as_dict()))
                        result.journal_result = 'VERIFIED'
                    else:
                        result.journal_result = row['status']
                else:
                    result.journal_result = row['status']
        except Exception as exc:  # noqa: BLE001 - journal failure must not bypass owned cleanup
            if result.postcondition_result != 'VERIFIED':
                result.status = IdleRewardStatus.ACTION_FAILED
            result.error = f'Journal finalization failed; reservation retained: {exc}'
            result.journal_result = 'FAILED'
        if started_by_run:
            try:
                manager.execute(index, "quit", snapshot=snapshot)
                result.cleanup_result = 'SUCCESS'
                result.cleanup_succeeded = True
            except (OSError, RuntimeError, ValueError) as exc:
                cleanup_error = str(exc)
                result.cleanup_result = 'FAILED'
                result.cleanup_succeeded = False
        else:
            result.cleanup_result = 'NOT_REQUIRED'

    inventory_error = None
    try:
        after = _state(manager.list_readonly())
        if session is not None:
            # Bound session verifies its own disk/runtime before every action.
            # Other user-owned instances may change independently during a fleet.
            isolation_changes = sorted(i for i in set(before) | set(after) if before.get(i) != after.get(i))
        else:
            isolation_changes = _only_target_changed(before, after, index)
    except (OSError, RuntimeError, ValueError) as exc:
        after = None
        isolation_changes = None
        inventory_error = str(exc)
        if result.postcondition_result == "VERIFIED":
            result.status = IdleRewardStatus.SUCCESS_WITH_RECOVERY_WARNING
            result.recovery_result = "FAILED"
            result.error = f"Claim verified; post-claim inventory could not be restored: {exc}"
    if cleanup_error and result.postcondition_result == 'VERIFIED':
        result.status = IdleRewardStatus.SUCCESS_WITH_RECOVERY_WARNING
        result.error = f'Claim verified; owned lifecycle cleanup failed: {cleanup_error}'
    elif cleanup_error and result.status in {IdleRewardStatus.SUCCESS, IdleRewardStatus.NOT_AVAILABLE}:
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
        "inventory_error": inventory_error,
        "recovery_report": str(recovery_report) if recovery_report else None,
        "initial_home_recovery_result": initial_recovery_result,
        "claim_journal_id": claim_id,
        "known_promo_recovery": port.promo_result.as_dict() if port and port.promo_result else None,
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
    sequence.add_argument("--tasks", nargs="+", choices=('vip-reward', 'ranking-chest', 'free-pack'), default=None)
    survey = commands.add_parser(
        SHOP_NAVIGATION_TASK,
        help="khảo sát Tiệm / không nhận quà (navigation-only)",
    )
    survey.add_argument("--index", type=int, required=True)
    survey.add_argument("--name", required=True)
    broad_survey = commands.add_parser(
        SHOP_SURVEY_TASK,
        help="khảo sát Tiệm (phạm vi một phần) / không nhận quà",
    )
    broad_survey.add_argument("--index", type=int, required=True)
    broad_survey.add_argument("--name", required=True)
    vip_survey = commands.add_parser(
        VIP_SURVEY_TASK,
        help=f"{VIP_SURVEY_LABEL} (observation-only)",
    )
    vip_survey.add_argument("--index", type=int, required=True)
    vip_survey.add_argument("--name", required=True)
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
        return 0 if result.status in {
            IdleRewardStatus.SUCCESS,
            IdleRewardStatus.SUCCESS_WITH_RECOVERY_WARNING,
            IdleRewardStatus.NOT_AVAILABLE,
        } else 2
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
    if args.command == SHOP_SURVEY_TASK:
        result = run_phase6_shop_survey(
            manager,
            data,
            args.index,
            args.name,
            promo_recovery_factory=promo_recovery_factory,
            survey_factory=shop_survey_factory,
        )
        print(json.dumps(result.as_dict(), ensure_ascii=True, indent=2))
        return 0 if result.status in SURVEY_SUCCESS_STATUSES else 2
    if args.command == VIP_SURVEY_TASK:
        result = run_phase6_vip_survey(manager, data, args.index, args.name)
        print(json.dumps(result.as_dict(), ensure_ascii=True, indent=2))
        return 0 if result.status == "SUCCESS" else 2
    from top_heroes_auto.app.registered_tasks import run_registered_selected

    results = run_registered_selected(
        manager,
        data,
        args.index,
        args.name,
        tasks=tuple(args.tasks) if args.tasks else None,
    )
    print(json.dumps({"results": [result.as_dict() for result in results]}, ensure_ascii=True, indent=2))
    return 0 if results and all(result.status in {*SUCCESS_STATUSES, "COMPLETE", "DISABLED", "NOT_APPLICABLE", "ALREADY_COMPLETED"} for result in results) else 2

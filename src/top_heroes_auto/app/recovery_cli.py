"""Exact-target Phase 4 diagnostic for bounded recovery to the game home screen."""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.diagnostic import _instance, _manager
from top_heroes_auto.app.process import CommandError
from top_heroes_auto.app.service import (
    LIFECYCLE_EXTERNAL,
    LIFECYCLE_OWNED,
    LIFECYCLE_UNKNOWN,
    LifecycleAttempt,
    Manager,
)
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.overlays import dismiss_overlay_bottom_left
from top_heroes_auto.automation.recovery import (
    HomeRecoveryEngine,
    RecoveryObservation,
    RecoveryResult,
    RecoveryStatus,
)
from top_heroes_auto.vision.image_normalizer import ScreenshotInvalid
from top_heroes_auto.vision.matcher import match_anchor
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.screenshot import ScreenshotService

log = logging.getLogger("top_heroes_auto")
GAME_PACKAGE = "com.greenmushroom.boomblitz.gp.vn"


class RecoveryFailure(OSError):
    """Recovery failure carrying authoritative ownership and cleanup state."""

    def __init__(
        self,
        message: str,
        *,
        started_by_run: bool,
        cleanup_attempted: bool,
        cleanup_succeeded: bool,
        report_path: Path | None = None,
        result: RecoveryResult | None = None,
        launch_attempt: dict | None = None,
        ownership_uncertain: bool = False,
    ):
        super().__init__(message)
        self.started_by_run = started_by_run
        self.cleanup_attempted = cleanup_attempted
        self.cleanup_succeeded = cleanup_succeeded
        self.report_path = report_path
        self.result = result
        self.launch_attempt = launch_attempt
        self.ownership_uncertain = ownership_uncertain


class DiagnosticRecoveryPort:
    def __init__(
        self,
        manager: Manager,
        snapshot: RunSnapshot,
        index: int,
        name: str,
        folder: Path,
        package: str = GAME_PACKAGE,
        clock=time.monotonic,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.folder = folder
        self.package = package
        self.detector = RecoveryScreenDetector()
        self.verified_identity: tuple[str, str] | None = None
        self.clock = clock
        self.started = clock()
        self.sample_thresholds = [0, 10, 20, 40]
        self.diagnostic_samples = []
        self.final_sample = False
        self._overlay_frame = None

    def observe(self, step: int) -> RecoveryObservation:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        identity = target.serial, target.boot_id
        if self.verified_identity is not None and identity != self.verified_identity:
            raise SafetyError("ADB target identity changed during recovery.")
        self.verified_identity = identity

        def exact_capture(serial: str) -> bytes:
            if serial != target.serial:
                raise SafetyError("Recovery capture target changed unexpectedly.")
            return payload

        elapsed = self.clock() - self.started
        due = [value for value in self.sample_thresholds if elapsed >= value]
        persist = True  # Every potential dismiss and its fresh result retain evidence.
        self.sample_thresholds = [value for value in self.sample_thresholds if value not in due]
        label = 'final' if self.final_sample else f'sample-{max(due)}s' if due else f'observation-{step:03d}'
        # Keep the raw final frame even when decoding rejects a blank transition.
        raw = None
        if persist:
            self.folder.mkdir(parents=True, exist_ok=True)
            raw = self.folder / f'{label}-raw.png'
            raw.write_bytes(payload)
            self.diagnostic_samples.append({
                'label': label, 'elapsed_seconds': elapsed, 'screenshot': str(raw),
                'index': target.index, 'name': target.name,
                'adb_target': target.serial, 'boot_id': target.boot_id,
                'capture_error': 'Frame captured; decoding/detection not completed.',
            })
        try:
            screen = ScreenshotService(exact_capture).take(
                target,
                None,
                f"{step:03d}-recovery",
            )
        except ScreenshotInvalid as exc:
            sample_path = raw
            if sample_path is None:
                sample_path = self.folder / f"invalid-{step:03d}-raw.png"
                sample_path.write_bytes(payload)
                self.diagnostic_samples.append({
                    'label': f'invalid-{step:03d}',
                    'elapsed_seconds': elapsed,
                    'screenshot': str(sample_path),
                    'index': target.index,
                    'name': target.name,
                    'adb_target': target.serial,
                    'boot_id': target.boot_id,
                })
            for sample in reversed(self.diagnostic_samples):
                if sample.get('screenshot') == str(sample_path):
                    sample['capture_error'] = str(exc)
                    break
            raise
        detection = self.detector.detect(screen)
        self._overlay_frame = (target, screen, detection)
        if persist:
            self.diagnostic_samples[-1].pop('capture_error')
            self.diagnostic_samples[-1].update({
                'detection': detection.as_dict(),
                'anchors': [match_anchor(screen, anchor).as_dict() for anchor in self.detector.anchors],
            })
        log.info(
            "[%s / #%s] Recovery state: %s confidence=%.3f",
            self.name,
            self.index,
            detection.state.value,
            detection.confidence,
        )
        return RecoveryObservation(detection, raw, target.serial, target.boot_id)

    def dismiss_overlay(self, observation):
        if self._overlay_frame is None or self._overlay_frame[2] is not observation.detection:
            raise SafetyError("Stale overlay observation.")
        target, screen, detection = self._overlay_frame
        point = dismiss_overlay_bottom_left(screen, detection)
        self._overlay_frame = None  # No uncertain input retry using this frame.
        self.manager.execute(self.index, "tap", values=point, snapshot=self.snapshot,
                             observed_target=target)
        log.info("[%s / #%s] Qualified overlay bottom-left tap %s", self.name, self.index, point)
        return point

    def persist_final(self):
        self.final_sample = True
        try:
            self.observe(0)
        except (OSError, RuntimeError, ValueError) as exc:
            error = {
                'label': 'final', 'capture_error': str(exc),
                'screenshot': str(self.folder / 'final-raw.png')
                if (self.folder / 'final-raw.png').exists() else None,
            }
            if self.diagnostic_samples and self.diagnostic_samples[-1]['label'] == 'final':
                self.diagnostic_samples[-1].update(error)
            else:
                self.diagnostic_samples.append(error)
        finally:
            self.final_sample = False

    def launch_game(self) -> None:
        log.info("[%s / #%s] Recovery action: launch verified package", self.name, self.index)
        self.manager.execute(
            self.index,
            "open_game",
            self.package,
            snapshot=self.snapshot,
        )


def run_home_recovery(
    manager: Manager,
    data: Path,
    index: int,
    name: str,
    *,
    cancelled=lambda: False,
    cleanup_owned: bool = True,
    engine: HomeRecoveryEngine | None = None,
) -> tuple[RecoveryResult, Path, bool]:
    target = _instance(manager, index, name)
    queen = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, queen.index).protected:
        raise SafetyError("Queen must remain Protected before recovery.")
    metadata = manager.store.metadata(manager.namespace, target.index)
    if metadata.protected or not metadata.selected:
        raise SafetyError("Recovery target must be selected and not Protected.")
    snapshot = RunSnapshot(manager.namespace, ((index, name),), True)
    started_by_run = False
    cleanup_attempted = False
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
    folder = data / "diagnostics" / "recovery" / name / stamp
    folder.mkdir(parents=True, exist_ok=False)
    result: RecoveryResult | None = None
    launch_attempt: dict | None = None
    ownership_uncertain = False
    port = None
    try:
        if not target.running:
            if cancelled():
                launch_attempt = LifecycleAttempt(
                    index=index,
                    action="launch",
                    target_name=name,
                    pre_running=False,
                    failure_stage="cancelled",
                ).as_dict()
                result = RecoveryResult(status=RecoveryStatus.CANCELLED)
            else:
                try:
                    manager.execute(index, "launch", snapshot=snapshot)
                finally:
                    attempt = manager.last_lifecycle_attempt
                    launch_attempt = attempt.as_dict() if attempt is not None else None
                    if attempt is not None:
                        started_by_run = attempt.ownership == LIFECYCLE_OWNED
                        ownership_uncertain = attempt.ownership == LIFECYCLE_UNKNOWN
                if launch_attempt is None:
                    raise SafetyError("Indexed launch outcome was unavailable; recovery is blocked.")
                if ownership_uncertain:
                    log.warning("[%s / #%s] Indexed launch ownership is uncertain; cleanup is blocked", name, index)
                if not started_by_run and not ownership_uncertain:
                    raise SafetyError("Indexed launch did not confirm ownership; recovery is blocked.")
        else:
            launch_attempt = LifecycleAttempt(
                index=index,
                action="launch",
                target_name=name,
                pre_running=True,
                ownership=LIFECYCLE_EXTERNAL,
            ).as_dict()
        if result is None:
            port = DiagnosticRecoveryPort(manager, snapshot, index, name, folder)
            result = (engine or HomeRecoveryEngine()).ensure_game_home(port, cancelled)
    except (CommandError, OSError, SafetyError, ValueError) as exc:
        result = RecoveryResult(RecoveryStatus.ADB_ERROR, error=str(exc))

    if result is None:
        result = RecoveryResult(RecoveryStatus.ADB_ERROR, error="Recovery did not produce a result.")
    result.launch_attempt = launch_attempt
    result.ownership_uncertain = ownership_uncertain
    if port is not None and result.status in {
        RecoveryStatus.LOADING_TIMEOUT, RecoveryStatus.LIMIT_REACHED, RecoveryStatus.UNKNOWN_SCREEN,
        RecoveryStatus.PROMO_BLOCKING,
    }:
        port.persist_final()

    report_path = folder / "report.json"
    cleanup_performed = False
    if started_by_run and cleanup_owned:
        cleanup_attempted = True
        try:
            manager.execute(index, "quit", snapshot=snapshot)
            cleanup_performed = True
        except Exception as exc:  # noqa: BLE001 - callers must not infer ownership
            raise RecoveryFailure(
                f"Owned recovery cleanup failed: {exc}",
                started_by_run=started_by_run,
                cleanup_attempted=cleanup_attempted,
                cleanup_succeeded=False,
                report_path=report_path,
                result=result,
                launch_attempt=launch_attempt,
                ownership_uncertain=ownership_uncertain,
            ) from exc
    try:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instance": {"index": index, "name": name},
            "package": GAME_PACKAGE,
            "started_by_run": started_by_run,
            "cleanup_requested": cleanup_owned,
            "cleanup_performed": cleanup_performed,
            "launch_attempt": launch_attempt,
            "ownership_uncertain": ownership_uncertain,
            "diagnostic_samples": port.diagnostic_samples if port is not None else [],
            **result.as_dict(),
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - persistence failure must not leak an owned instance
        cleanup_error: str | None = None
        if started_by_run and not cleanup_attempted:
            cleanup_attempted = True
            try:
                manager.execute(index, "quit", snapshot=snapshot)
                cleanup_performed = True
            except Exception as cleanup_exc:  # noqa: BLE001 - preserve the original persistence failure
                cleanup_error = f"owned cleanup failed: {cleanup_exc}"
                log.exception("[%s / #%s] Owned recovery cleanup failed after report failure", name, index)
        message = str(exc)
        if cleanup_error:
            message = f"{message}; {cleanup_error}"
        raise RecoveryFailure(
            message,
            started_by_run=started_by_run,
            cleanup_attempted=cleanup_attempted,
            cleanup_succeeded=cleanup_performed,
            report_path=report_path,
            result=result,
            launch_attempt=launch_attempt,
            ownership_uncertain=ownership_uncertain,
        ) from exc
    return result, report_path, started_by_run


def parser():
    root = argparse.ArgumentParser(prog="TopHeroesAutoManager.exe recovery")
    commands = root.add_subparsers(dest="command", required=True)
    home = commands.add_parser("home")
    home.add_argument("--index", type=int, required=True)
    home.add_argument("--name", required=True)
    return root


def main(argv: list[str], data: Path) -> int:
    args = parser().parse_args(argv)
    manager = _manager(data)
    result, report, started = run_home_recovery(manager, data, args.index, args.name)
    output = {**result.as_dict(), "started_by_run": started, "report": str(report)}
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0 if result.status.value in {"SUCCESS", "ALREADY_HOME"} else 2

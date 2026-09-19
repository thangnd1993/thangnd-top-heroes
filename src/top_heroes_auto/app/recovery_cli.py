"""Exact-target Phase 4 diagnostic for bounded recovery to the game home screen."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.diagnostic import _instance, _manager
from top_heroes_auto.app.process import CommandError
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.recovery import (
    HomeRecoveryEngine,
    RecoveryObservation,
    RecoveryResult,
    RecoveryStatus,
)
from top_heroes_auto.vision.detector import ScreenDetector
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.screenshot import ScreenshotService

log = logging.getLogger("top_heroes_auto")
GAME_PACKAGE = "com.greenmushroom.boomblitz.gp.vn"


class DiagnosticRecoveryPort:
    def __init__(
        self,
        manager: Manager,
        snapshot: RunSnapshot,
        index: int,
        name: str,
        folder: Path,
        package: str = GAME_PACKAGE,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.folder = folder
        self.package = package
        self.detector = ScreenDetector.from_folder(template_folder())
        self.verified_identity: tuple[str, str] | None = None

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

        screen = ScreenshotService(exact_capture).take(
            target,
            self.folder,
            f"{step:03d}-recovery",
        )
        detection = self.detector.detect(screen)
        log.info(
            "[%s / #%s] Recovery state: %s confidence=%.3f",
            self.name,
            self.index,
            detection.state.value,
            detection.confidence,
        )
        return RecoveryObservation(detection, screen.source_image, target.serial)

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
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
    folder = data / "diagnostics" / "recovery" / name / stamp
    folder.mkdir(parents=True, exist_ok=False)
    result: RecoveryResult | None = None
    try:
        if not target.running:
            if cancelled():
                result = RecoveryResult(status=RecoveryStatus.CANCELLED)
            else:
                manager.execute(index, "launch", snapshot=snapshot)
                started_by_run = True
        if result is None:
            port = DiagnosticRecoveryPort(manager, snapshot, index, name, folder)
            result = (engine or HomeRecoveryEngine()).ensure_game_home(port, cancelled)
    except (CommandError, OSError, SafetyError, ValueError) as exc:
        result = RecoveryResult(RecoveryStatus.ADB_ERROR, error=str(exc))

    cleanup_performed = False
    if started_by_run and cleanup_owned:
        manager.execute(index, "quit", snapshot=snapshot)
        cleanup_performed = True
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "instance": {"index": index, "name": name},
        "package": GAME_PACKAGE,
        "started_by_run": started_by_run,
        "cleanup_requested": cleanup_owned,
        "cleanup_performed": cleanup_performed,
        **result.as_dict(),
    }
    report_path = folder / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
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

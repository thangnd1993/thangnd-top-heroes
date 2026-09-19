"""Encoding-safe, exact-target Phase 3 screenshot and recognition diagnostics."""

import argparse
import json
import logging
from pathlib import Path

from top_heroes_auto.app.diagnostic import _instance, _manager
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.debug import write_overlay
from top_heroes_auto.vision.detector import ScreenDetector
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.screenshot import ScreenshotService

log = logging.getLogger("top_heroes_auto")


def parser():
    root = argparse.ArgumentParser(prog="TopHeroesAutoManager.exe vision")
    commands = root.add_subparsers(dest="command", required=True)
    for command in ("capture", "detect"):
        child = commands.add_parser(command)
        child.add_argument("--index", type=int, required=True)
        child.add_argument("--name", required=True)
        child.add_argument("--tag", default=command)
        if command == "detect":
            child.add_argument("--debug", action="store_true")
    return root


def _capture(manager, data: Path, index: int, name: str, tag: str):
    target_instance = _instance(manager, index, name)
    queen = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, queen.index).protected:
        raise SafetyError("Queen must remain Protected before vision diagnostics.")
    metadata = manager.store.metadata(manager.namespace, target_instance.index)
    if metadata.protected or not metadata.selected:
        raise SafetyError("Vision target must be selected and not Protected.")
    target, payload = manager.capture_verified(index)

    def exact_capture(serial: str) -> bytes:
        if serial != target.serial:
            raise SafetyError("Vision capture target changed unexpectedly.")
        return payload

    folder = data / "diagnostics" / "vision" / name
    return ScreenshotService(exact_capture).take(target, folder, tag)


def _write_detection_report(screen, result: dict) -> Path:
    if screen.source_image is None:
        raise ValueError("A persisted screenshot is required for a diagnostic report.")
    report = screen.source_image.with_name(f"{screen.source_image.stem}-detection.json")
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: list[str], data: Path) -> int:
    args = parser().parse_args(argv)
    manager = _manager(data)
    try:
        screen = _capture(manager, data, args.index, args.name, args.tag)
        result = {
            "instance": {"index": screen.index, "name": screen.name},
            "adb_target": screen.serial,
            "resolution": list(screen.original_size),
            "normalized_resolution": list(screen.normalized_size),
            "scale_to_original": list(screen.scale_to_original),
            "source_image": str(screen.source_image),
        }
        if args.command == "detect":
            detection = ScreenDetector.from_folder(template_folder()).detect(screen)
            result.update(detection.as_dict())
            if args.debug:
                overlay = data / "diagnostics" / "vision" / "debug" / f"{screen.source_image.stem}-debug.png"
                result["debug_overlay"] = str(write_overlay(screen, detection, overlay))
            log.info(
                "[%s] Screen state %s confidence=%.3f",
                screen.name,
                detection.state.value,
                detection.confidence,
            )
            result["detection_report"] = str(_write_detection_report(screen, result))
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=True))
        raise

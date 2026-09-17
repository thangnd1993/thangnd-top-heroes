"""Explicit, guarded headless diagnostics for real Windows acceptance testing."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.process import Process
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.ldplayer.client import LDPlayer, discover
from top_heroes_auto.storage.store import Store


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _instance(manager: Manager, index: int, name: str):
    instance = manager.query(index)
    if instance.name != name:
        raise SafetyError(f"Identity mismatch: expected #{index} / {name!r}, got {instance.name!r}.")
    return instance


def _state(instances):
    return {item.index: (item.name, item.running, item.android_started) for item in instances}


def _only_target_changed(before, after, target: int):
    changed = {index for index in set(before) | set(after) if before.get(index) != after.get(index)}
    unexpected = changed - {target}
    if unexpected:
        raise SafetyError(f"Isolation failure: unrelated instances changed: {sorted(unexpected)}")
    return sorted(changed)


def _packages(output: str) -> list[str]:
    return [line.removeprefix("package:").strip() for line in output.splitlines() if line.startswith("package:")]


def _top_heroes_candidates(packages: list[str]) -> list[str]:
    return [package for package in packages if "top" in package.casefold() and "hero" in package.casefold()]


def _report_path(data: Path) -> Path:
    folder = data / "diagnostics" / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "phase1-windows-acceptance.json"


def _write_report(data: Path, report: dict):
    path = _report_path(data)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _manager(data: Path) -> Manager:
    store = Store(data / "config.sqlite3")
    installation = discover(store.get("ldplayer_folder"))
    if installation is None:
        raise SafetyError("Không phát hiện LDPlayer an toàn.")
    return Manager(LDPlayer(installation, Process()), store, data)


def _view(manager: Manager, instances):
    return [
        {
            "index": item.index,
            "name": item.name,
            "status": "running" if item.running else "stopped",
            "android_started": item.android_started,
            "resolution": [item.width, item.height] if item.width else None,
            "dpi": item.dpi,
            "protected": manager.store.metadata(manager.namespace, item.index).protected,
            "selected": manager.store.metadata(manager.namespace, item.index).selected,
            "adb_target": item.adb_serial,
        }
        for item in instances
    ]


def list_command(manager: Manager, data: Path):
    rows = _view(manager, manager.refresh())
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return {"instances": rows, "timestamps": {"finished": _stamp()}}


def protect_command(manager: Manager, data: Path, index: int, name: str):
    _instance(manager, index, name)
    manager.protect(index, True)
    meta = manager.store.metadata(manager.namespace, index)
    if not meta.protected or meta.selected:
        raise SafetyError("Không thể lưu Protected state an toàn.")
    result = {"index": index, "name": name, "protected": meta.protected, "selected": meta.selected}
    print(json.dumps(result, ensure_ascii=False))
    return {"protection": result, "timestamps": {"finished": _stamp()}}


def test_command(manager: Manager, data: Path, index: int, name: str):
    report = {"timestamps": {"started": _stamp()}, "test_clone": {"index": index, "name": name}, "errors": []}
    target = _instance(manager, index, name)
    main = _instance(manager, 0, "Queen")
    main_meta = manager.store.metadata(manager.namespace, main.index)
    if not main_meta.protected:
        raise SafetyError("Queen must be Protected before diagnostic testing.")
    target_meta = manager.store.metadata(manager.namespace, target.index)
    if target_meta.protected:
        raise SafetyError("Diagnostic target is Protected.")
    manager.select(index, True)
    report["protected_main"] = {"index": main.index, "name": main.name, "protected": True}

    def lifecycle(action: str):
        before = _state(manager.refresh())
        result = manager.execute(index, action)
        after = _state(manager.refresh())
        return result, _only_target_changed(before, after, index)

    report["start_result"], report["start_changed"] = lifecycle("launch")
    report["adb"] = manager.execute(index, "verify")
    report["harmless_shell"] = manager.execute(index, "harmless")
    first = Path(manager.execute(index, "screenshot"))
    shots = data / "diagnostics" / name
    shots.mkdir(parents=True, exist_ok=True)
    first_path = shots / first.name
    first.replace(first_path)
    report["screenshot_before_game"] = str(first_path)
    packages = _packages(manager.execute(index, "packages"))
    candidates = _top_heroes_candidates(packages)
    report["top_heroes_candidates"] = candidates
    if len(candidates) != 1:
        raise SafetyError("Top Heroes package is ambiguous or cannot be identified safely.")
    package = candidates[0]
    report["top_heroes_package"] = package
    report["game_launch"] = manager.execute(index, "open_game", package)
    second = Path(manager.execute(index, "screenshot"))
    second_path = shots / second.name
    second.replace(second_path)
    report["screenshot_after_game"] = str(second_path)
    report["game_stop"] = manager.execute(index, "close_game", package)
    report["restart_result"], report["restart_changed"] = lifecycle("reboot")
    report["adb_after_restart"] = manager.execute(index, "verify")
    report["stop_result"], report["stop_changed"] = lifecycle("quit")
    report["isolation"] = "passed"
    report["timestamps"]["finished"] = _stamp()
    return report


def parser():
    root = argparse.ArgumentParser(prog="TopHeroesAutoManager.exe diagnostic")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for command in ("protect", "show", "test"):
        child = commands.add_parser(command)
        child.add_argument("--index", type=int, required=True)
        child.add_argument("--name", required=True)
    return root


def main(argv: list[str], data: Path) -> int:
    args = parser().parse_args(argv)
    manager = _manager(data)
    report = {"ldplayer_path": str(manager.ld.installation.console.parent), "timestamps": {"started": _stamp()}}
    try:
        if args.command == "list":
            report.update(list_command(manager, data))
        elif args.command == "protect":
            report.update(protect_command(manager, data, args.index, args.name))
        elif args.command == "show":
            report["instance"] = _view(manager, (_instance(manager, args.index, args.name),))[0]
            print(json.dumps(report["instance"], ensure_ascii=False, indent=2))
        else:
            report.update(test_command(manager, data, args.index, args.name))
        report["status"] = "passed"
        return 0
    except Exception as exc:
        report["status"] = "failed"
        report["errors"] = [str(exc)]
        raise
    finally:
        report["timestamps"]["finished"] = _stamp()
        path = _write_report(data, report)
        print(f"Diagnostic report: {path}")

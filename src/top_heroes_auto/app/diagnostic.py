"""Explicit, guarded headless diagnostics for real Windows acceptance testing."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.process import Process
from top_heroes_auto.app.run_queue import RunController
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.ldplayer.client import LDPlayer, discover
from top_heroes_auto.storage.store import Store


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _instance(manager: Manager, index: int, name: str):
    instance = manager.query(index)
    stable_id = manager.store.require_identity(manager.namespace, index)
    if instance.stable_id != stable_id:
        raise SafetyError('IDENTITY_UNVERIFIED: current backing disk proof missing or changed.')
    # name is a caller's display label, never an authorization check.
    return instance


def _state(instances):
    return {item.index: (item.stable_id, item.running, item.android_started) for item in instances}


def _only_target_changed(before, after, target: int, *, peer_identities=None):
    changed = {index for index in set(before) | set(after) if before.get(index) != after.get(index)}
    # Concurrent workers may change only runtime state of their frozen disks.
    # Missing/replaced peers are not hidden by an index-only allowlist.
    peers = {index for index, identity in (peer_identities or {}).items()
             if identity and before.get(index, (None,))[0] == identity
             and after.get(index, (None,))[0] == identity}
    unexpected = changed - {target} - peers
    if unexpected:
        raise SafetyError(f"Isolation failure: unrelated instances changed: {sorted(unexpected)}")
    return sorted(changed)


def _packages(output: str) -> list[str]:
    return [line.removeprefix("package:").strip() for line in output.splitlines() if line.startswith("package:")]


def _aapt_labels(output: str) -> set[str]:
    """Return localized and default labels from ``aapt dump badging``."""
    labels = set()
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("application-label") and ":'" in stripped and stripped.endswith("'"):
            labels.add(stripped.partition(":'")[2][:-1])
    return labels


def _report_path(data: Path) -> Path:
    folder = data / "diagnostics" / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "phase1-windows-acceptance.json"


def _write_report(data: Path, report: dict):
    path = _report_path(data)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _manager(data: Path) -> Manager:
    store = Store(data / "config.sqlite3", recover_running=False)
    installation = discover(store.get("ldplayer_folder"))
    if installation is None:
        raise SafetyError("Không phát hiện LDPlayer an toàn.")
    return Manager(LDPlayer(installation, Process()), store, data)


def _view(manager: Manager, instances):
    return [
        {
            "index": item.index,
            "name": item.name,
            "stable_id": item.stable_id,
            "identity_state": manager.store.metadata(manager.namespace, item.index).identity_state,
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
    rows = _view(manager, manager.list_readonly())
    print(json.dumps(rows, ensure_ascii=True, indent=2))
    return {"instances": rows, "timestamps": {"finished": _stamp()}}


def protect_command(manager: Manager, data: Path, index: int, name: str):
    live = _instance(manager, index, name)
    name = live.name
    manager.protect(index, True)
    meta = manager.store.metadata(manager.namespace, index)
    if not meta.protected or meta.selected:
        raise SafetyError("Không thể lưu Protected state an toàn.")
    result = {"index": index, "name": name, "protected": meta.protected, "selected": meta.selected}
    print(json.dumps(result, ensure_ascii=True))
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

    started = False
    game_started = False
    package = ""
    try:
        report["start_result"], report["start_changed"] = lifecycle("launch")
        started = True
        report["adb"] = manager.execute(index, "verify")
        report["harmless_shell"] = manager.execute(index, "harmless")
        first = Path(manager.execute(index, "screenshot"))
        shots = data / "diagnostics" / f"{index}-{target.stable_id}"
        shots.mkdir(parents=True, exist_ok=True)
        first_path = shots / first.name
        first.replace(first_path)
        report["screenshot_before_game"] = str(first_path)
        packages = _packages(manager.execute(index, "packages"))
        third_party = _packages(manager.execute(index, "third_party_packages"))
        candidates = [
            package
            for package in third_party
            if "Thời Đại Anh Hùng" in _aapt_labels(manager.execute(index, "package_badging", package))
        ]
        candidates = sorted(set(packages) & set(candidates))
        report["top_heroes_candidates"] = candidates
        if len(candidates) != 1:
            raise SafetyError("Top Heroes package label is ambiguous or cannot be identified safely.")
        package = candidates[0]
        launcher = manager.execute(index, "launcher_activity", package).strip()
        if not launcher or "/" not in launcher:
            raise SafetyError("Top Heroes launcher activity cannot be identified safely.")
        report["top_heroes_package"] = package
        report["top_heroes_launcher_activity"] = launcher
        report["game_launch"] = manager.execute(index, "open_game", package)
        game_started = True
        second = Path(manager.execute(index, "screenshot"))
        second_path = shots / second.name
        second.replace(second_path)
        report["screenshot_after_game"] = str(second_path)
        report["game_stop"] = manager.execute(index, "close_game", package)
        game_started = False
        report["restart_result"], report["restart_changed"] = lifecycle("reboot")
        report["adb_after_restart"] = manager.execute(index, "verify")
        report["stop_result"], report["stop_changed"] = lifecycle("quit")
        started = False
        report["isolation"] = "passed"
        report["timestamps"]["finished"] = _stamp()
        return report
    finally:
        if game_started:
            manager.execute(index, "close_game", package)
        # launch may have started the exact instance before its ADB verification
        # raises. Observe the live target rather than trusting a successful return.
        target_is_running = any(item.index == index and item.running for item in manager.refresh())
        if started or target_is_running:
            report["cleanup_stop_result"], report["cleanup_stop_changed"] = lifecycle("quit")


def verify_target_command(manager: Manager, data: Path, index: int):
    """Read-only hybrid-workflow check of ONE target: Multi index -> Protection -> stable
    identity -> indexed ADB serial + boot identity -> one fresh screenshot -> classification.

    Never sends input, launch/quit, selection or Protection changes, or name writes. A
    Protected, stopped, not-ready or ambiguous target fails closed with an explicit reason
    before any ADB command is sent to it."""
    import time

    from top_heroes_auto.automation import timing
    from top_heroes_auto.automation.guard import bound_snapshot

    timing.reset()
    started = time.perf_counter()
    result = dict(index=index, stages={}, input_dispatched=False, lifecycle_dispatched=False)

    def stage(name, began):
        result['stages'][name] = round(time.perf_counter() - began, 3)

    began = time.perf_counter()
    matches = [i for i in manager.list_readonly() if i.index == index]
    stage('inventory_seconds', began)
    if len(matches) != 1:
        raise SafetyError(f'TARGET_NOT_FOUND: Multi index {index} missing or ambiguous.')
    live = matches[0]
    meta = manager.store.metadata(manager.namespace, index)
    result.update(display_name_informational_only=live.name, running=live.running,
                  android_started=live.android_started, protected=meta.protected)
    if meta.protected:
        raise SafetyError('PROTECTED_TARGET: automation never sends commands to this instance.')
    try:
        stable_id = manager.store.require_identity(manager.namespace, index)
    except ValueError as exc:
        raise SafetyError(f'TARGET_IDENTITY_AMBIGUOUS: {exc}') from exc
    if live.stable_id != stable_id:
        raise SafetyError('TARGET_IDENTITY_AMBIGUOUS: live backing disk differs from the stored identity.')
    if not (live.running and live.android_started):
        raise SafetyError('ADB_UNAVAILABLE: target is not running/Android-ready; this check never launches it.')
    result['stable_id'] = stable_id
    began = time.perf_counter()
    target, payload = manager.capture_verified(
        index, bound_snapshot(manager.store, manager.namespace, ((index, live.name),), True))
    stage('identity_and_capture_seconds', began)
    result.update(adb_serial=target.serial, boot_id=target.boot_id)
    folder = data / 'diagnostics' / 'verify-target'
    folder.mkdir(parents=True, exist_ok=True)
    shot = folder / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{index}.png"
    shot.write_bytes(payload)
    result['screenshot'] = str(shot)
    began = time.perf_counter()
    try:
        from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
        from top_heroes_auto.vision.screenshot import ScreenshotService

        screen = ScreenshotService(lambda serial: payload if serial == target.serial else b'').take(target)
        detection = RecoveryScreenDetector().detect(screen)
        result['screen'] = dict(state=detection.state.value, confidence=round(float(detection.confidence), 3))
    except (ValueError, OSError) as exc:
        result['screen'] = dict(state='UNKNOWN', error=str(exc)[:300])  # UNKNOWN never authorizes input
    stage('classification_seconds', began)
    result['stages']['total_seconds'] = round(time.perf_counter() - started, 3)
    result['transport_commands'] = getattr(manager.ld.process, 'metrics', {})
    result['operation_metrics'] = timing.snapshot()
    print(json.dumps({k: v for k, v in result.items() if k != 'operation_metrics'}, ensure_ascii=True, indent=2))
    return {'verify_target': result}


def parser():
    root = argparse.ArgumentParser(prog="TopHeroesAutoManager.exe diagnostic")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for command in ("protect", "show", "test", "run-selected"):
        child = commands.add_parser(command)
        child.add_argument("--index", type=int, required=True)
        child.add_argument("--name", required=True)
        if command == "run-selected":
            child.add_argument("--concurrency", type=int, choices=(1, 2, 3, 4), default=1)
    verify = commands.add_parser("verify-target", help="Read-only: identity, indexed ADB, one screenshot. No input.")
    verify.add_argument("--index", type=int, required=True)
    members = commands.add_parser("run-members")
    members.add_argument(
        "--member",
        action="append",
        required=True,
        help="Exact member in INDEX:NAME form; repeat once per explicitly authorized clone.",
    )
    members.add_argument("--concurrency", type=int, choices=(1, 2, 3, 4), required=True)
    return root


def _members(values: list[str]) -> tuple[tuple[int, str], ...]:
    """Parse exact, non-ambiguous diagnostic members without any fallback."""
    parsed = []
    for value in values:
        index, separator, name = value.partition(":")
        if not separator or not name:
            raise SafetyError("Mỗi --member phải có dạng INDEX:NAME chính xác.")
        try:
            parsed.append((int(index), name))
        except ValueError as exc:
            raise SafetyError("Member index không hợp lệ; không fallback về index 0.") from exc
    members = tuple(parsed)
    if len(set(members)) != len(members):
        raise SafetyError("Diagnostic members bị trùng lặp.")
    return members


def _run_members(manager: Manager, data: Path, members: tuple[tuple[int, str], ...], concurrency: int):
    main = _instance(manager, 0, "Queen")
    if not manager.store.metadata(manager.namespace, main.index).protected:
        raise SafetyError("Queen must be Protected before diagnostic testing.")
    # Query every requested target before a run exists or a worker can mutate it.
    for index, name in members:
        _instance(manager, index, name)
    controller = RunController(
        manager.store,
        lambda: Manager(LDPlayer(manager.ld.installation, Process()), manager.store, data),
    )
    run = controller.create_members(manager, members, concurrency)
    rows = controller.execute(run)
    return {
        "id": run.id,
        "snapshot": list(run.snapshot.members),
        "max_concurrency": run.max_concurrency,
        "accounts": [list(row) for row in rows],
    }


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
            print(json.dumps(report["instance"], ensure_ascii=True, indent=2))
        elif args.command == "verify-target":
            report.update(verify_target_command(manager, data, args.index))
        elif args.command == "test":
            report.update(test_command(manager, data, args.index, args.name))
        elif args.command == "run-selected":
            target = _instance(manager, args.index, args.name)
            report["phase2_run"] = _run_members(manager, data, ((target.index, target.name),), args.concurrency)
        else:
            report["phase2_run"] = _run_members(manager, data, _members(args.member), args.concurrency)
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

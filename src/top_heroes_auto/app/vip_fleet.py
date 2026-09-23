"""Explicitly invoked, sequential VIP daily-only acceptance across live safe targets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.diagnostic import _instance, _manager, _view
from top_heroes_auto.app.free_reward_tasks import _load_profile_details
from top_heroes_auto.app.main import data_directory
from top_heroes_auto.app.phase6_runtime import entry_navigator_factory, reward_port_factory
from top_heroes_auto.app.recovery_cli import RecoveryFailure, run_home_recovery
from top_heroes_auto.automation.free_rewards import ClaimOutcome, FreeRewardGuard
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.recovery import RecoveryStatus
from top_heroes_auto.automation.reward_journal import evidence_json

PROTECTED = {0: "Queen", 1: "anh Ry", 6: "Chicken", 7: "Happy"}


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _protected(manager):
    for index, name in PROTECTED.items():
        _instance(manager, index, name)
        meta = manager.store.metadata(manager.namespace, index)
        if not meta.protected or meta.selected:
            raise SafetyError(f"Protected account #{index} must remain Protected and unselected.")


def run_vip_account(manager, data, index, name, folder, *, include_upper_gift=False):
    """Use production guards and visual ports; one claim call, no explorer routes."""
    row = dict(index=index, name=name, adb_target=None, recovery_result="NOT_STARTED",
               game_home_confidence=None, vip_entry=None, vip_screen_verified=False,
               free_reward_state="UNKNOWN", geometry=None, claim_dispatched=False,
               post_condition="NOT_STARTED", journal_state="NONE", final_result="SAFETY_BLOCKED",
               cleanup="NOT_REQUIRED", selection_restored=False, error=None)
    original_selected = None
    selection_changed = False
    started = False
    cleanup_attempted = False
    task_id = None
    claim_id = None
    snapshot = RunSnapshot(manager.namespace, ((index, name),), True)
    try:
        _protected(manager)
        _instance(manager, index, name)
        meta = manager.store.metadata(manager.namespace, index)
        original_selected = meta.selected
        if meta.protected or index in PROTECTED:
            row["final_result"] = "SKIPPED_PROTECTED"
            return row
        prior = [r for r in manager.store.reward_claims(manager.namespace, index)
                 if r["reward_id"] == "vip-daily" and r["status"] in {"RESERVED", "VERIFIED"}]
        if prior and not include_upper_gift:
            row["journal_state"] = prior[-1]["status"]
            row["final_result"] = "ALREADY_VERIFIED" if prior[-1]["status"] == "VERIFIED" else "ALREADY_ATTEMPTED"
            row["free_reward_state"] = "JOURNAL_LOCKED"
            row["error"] = "Conservative journal lock retained; no visually proven period reset."
            return row
        profile, error = _load_profile_details("vip-reward")
        if profile is None:
            raise SafetyError(error or "VIP profile unavailable.")
        task_id = manager.store.create_task_run(manager.namespace, "vip-reward", index, name)
        row["task_run_id"] = task_id
        if not original_selected:
            selection_changed = True
            manager.select(index, True)
        recovery, report, started = run_home_recovery(manager, data, index, name, cleanup_owned=False)
        row.update(recovery_report=str(report), recovery_result=recovery.status.value, adb_target=recovery.adb_target)
        if recovery.status not in {RecoveryStatus.SUCCESS, RecoveryStatus.ALREADY_HOME}:
            row["final_result"] = "BLOCKED_ADB_CONFIG" if recovery.status == RecoveryStatus.ADB_ERROR else recovery.status.value
            row["error"] = recovery.error
            return row
        row["recovery_result"] = "SUCCESS"
        row["game_home_confidence"] = recovery.steps[-1].confidence if recovery.steps else None
        navigation = entry_navigator_factory(manager, snapshot, index, name, profile, folder)
        row["navigation"] = navigation.as_dict()
        if navigation.status.value != "SUCCESS":
            row["final_result"] = navigation.status.value
            row["error"] = navigation.error
            return row
        entry = navigation.target_evidence[-1] if navigation.target_evidence else None
        row["vip_entry"] = entry
        if include_upper_gift:
            from top_heroes_auto.app.vip_gift import run_upper_gift

            gift_folder = folder / "upper-gift"
            gift_folder.mkdir(exist_ok=True)
            row["upper_gift"] = {}
            run_upper_gift(manager, snapshot, index, name, profile, gift_folder, entry, task_id, row["upper_gift"])
            row["vip_screen_verified"] = row["upper_gift"].get("before", {}).get("detection", {}).get("state") == "FREE_REWARD_PAGE"
            if row["upper_gift"]["result"] not in {"SUCCESS", "NOT_AVAILABLE", "ALREADY_VERIFIED", "ALREADY_ATTEMPTED"}:
                row["final_result"] = row["upper_gift"]["result"]
                return row
        port = reward_port_factory(manager, snapshot, index, name, profile, folder)
        port.set_entry_geometry(entry)
        before = port.observe()
        guard = FreeRewardGuard(index, name)
        guard.observe(before)
        row.update(adb_target=before.adb_target, before_evidence=json.loads(evidence_json(before)))
        row["vip_screen_verified"] = before.detection.state.value == "FREE_REWARD_PAGE" and before.detection.confidence >= .9
        if not row["vip_screen_verified"]:
            raise SafetyError("Current VIP screen is not qualified.")
        if prior:
            row.update(journal_state=prior[-1]["status"], free_reward_state="JOURNAL_LOCKED",
                       final_result="ALREADY_VERIFIED" if prior[-1]["status"] == "VERIFIED" else "ALREADY_ATTEMPTED")
            row["return_home"] = "SUCCESS" if port.return_home(before) else "FAILED"
            return row
        if not before.rewards:
            # The VIP adapter emits no candidate only for a positive claimed-state anchor.
            row.update(free_reward_state="UNAVAILABLE", final_result="NOT_AVAILABLE")
            row["return_home"] = "SUCCESS" if port.return_home(before) else "FAILED"
            return row
        if len(before.rewards) != 1 or before.rewards[0].reward_id != "vip-daily":
            raise SafetyError("Only one VIP daily candidate is authorized.")
        reward = before.rewards[0]
        point = guard.claim(before, reward)
        port.validate_claim(before, reward, point)
        row.update(free_reward_state="FREE_CLAIMABLE", geometry=port.geometry_report)
        claim_id = manager.store.reserve_reward_claim(
            task_id, "vip-daily", "phase6:vip-reward:conservative-opportunity", evidence_json(before),
            expected_instance=(index, name), not_dispatched=True,
        )
        row.update(claim_id=claim_id, journal_state="RESERVED")
        _write(folder / "account-report.json", row)

        def before_input():
            manager.store.mark_reward_dispatch(claim_id, task_id)
            row["claim_dispatched"] = "POSSIBLE"

        port.claim(before, reward, point, before_input=before_input)
        row["claim_dispatched"] = True
        after = port.observe()
        guard.observe(after)
        row["immediate_after_evidence"] = json.loads(evidence_json(after))
        after = port.dismiss_receipts(after)
        if after.capture_id != row["immediate_after_evidence"]["capture_id"]:
            guard.observe(after)
        row["overlay_events"] = port.overlay_events
        row["after_evidence"] = json.loads(evidence_json(after))
        outcome = port.classify_claim(before, after, reward)
        row["post_condition"] = outcome.value
        if outcome != ClaimOutcome.CLAIMED:
            row["final_result"] = "ACTION_DISPATCHED_UNVERIFIED"
            return row
        manager.store.verify_reward_claim(claim_id, task_id, evidence_json(after))
        row.update(journal_state="VERIFIED", post_condition="VERIFIED", final_result="SUCCESS")
        row["return_home"] = "SUCCESS" if port.return_home(after) else "FAILED"
        if row["return_home"] == "FAILED":
            row["final_result"] = "SUCCESS_WITH_RECOVERY_WARNING"
        return row
    except Exception as exc:  # noqa: BLE001 - one account cannot suppress the remaining fleet
        if isinstance(exc, RecoveryFailure):
            started, cleanup_attempted = exc.started_by_run, exc.cleanup_attempted
            row["cleanup"] = "SUCCESS" if exc.cleanup_succeeded else "FAILED" if cleanup_attempted else "NOT_REQUIRED"
            row["recovery_report"] = str(exc.report_path)
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["final_result"] = (
            "SUCCESS_WITH_RECOVERY_WARNING" if row["journal_state"] == "VERIFIED" else
            "ACTION_DISPATCHED_UNVERIFIED" if row["claim_dispatched"] or
            row.get("upper_gift", {}).get("claim_dispatched") else "SAFETY_BLOCKED"
        )
        return row
    finally:
        if started and not cleanup_attempted:
            try:
                manager.execute(index, "quit", snapshot=snapshot)
                row["cleanup"] = "SUCCESS"
            except Exception as exc:  # noqa: BLE001 - never retry uncertain cleanup
                row["cleanup"] = f"FAILED: {exc}"
                if row["journal_state"] == "VERIFIED":
                    row["final_result"] = "SUCCESS_WITH_RECOVERY_WARNING"
        try:
            if selection_changed:
                _instance(manager, index, name)
                meta = manager.store.metadata(manager.namespace, index)
                if not meta.protected:
                    manager.select(index, original_selected)
            row["selection_restored"] = manager.store.metadata(manager.namespace, index).selected == original_selected
        except Exception as exc:  # noqa: BLE001 - report restoration failure without targeting another account
            row["selection_error"] = str(exc)
        if claim_id is not None:
            receipt = next(r for r in manager.store.reward_claims(manager.namespace, index) if r["id"] == claim_id)
            row["journal_state"] = receipt["status"]
            row["dispatch_state"] = receipt["dispatch_state"]
        if row.get("upper_gift", {}).get("result") == "ALREADY_ATTEMPTED":
            row["daily_result"] = row["final_result"]
            row["final_result"] = "PARTIAL_UPPER_GIFT_UNVERIFIED"
        _write(folder / "account-report.json", row)
        if task_id is not None:
            manager.store.finish_task_run(task_id, row["final_result"], error=row["error"] or "",
                                          report_path=str(folder / "account-report.json"))


def run_vip_fleet(manager, data: Path, *, account_runner=run_vip_account):
    _protected(manager)
    inventory = manager.list_readonly()
    before = _view(manager, inventory)
    candidates = [(r["index"], r["name"]) for r in before if not r["protected"] and r["index"] not in PROTECTED]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%fZ")
    folder = data / "diagnostics" / "tasks" / "vip-daily-fleet" / stamp
    folder.mkdir(parents=True, exist_ok=False)
    report = dict(max_concurrency=1, before_instances=before, candidates=candidates, accounts=[])
    _write(folder / "fleet-report.json", report)
    for index, name in candidates:
        account_folder = folder / str(index)
        account_folder.mkdir()
        print(f"VIP START #{index} / {name}", flush=True)
        try:
            row = account_runner(manager, data, index, name, account_folder)
        except Exception as exc:  # noqa: BLE001 - preserve a row even after account report failure
            row = dict(index=index, name=name, final_result="FAILED", error=str(exc))
        report["accounts"].append(row)
        _write(folder / "fleet-report.json", report)
        print(f"VIP END #{index}: {row['final_result']}; claim={row.get('claim_dispatched', False)}; "
              f"cleanup={row.get('cleanup')}; selection_restored={row.get('selection_restored')}", flush=True)
    report["after_instances"] = _view(manager, manager.list_readonly())
    report["all_selection_states_restored"] = {
        r["index"]: r["selected"] for r in before
    } == {r["index"]: r["selected"] for r in report["after_instances"]}
    report["protected_state_unchanged"] = all(
        r in report["after_instances"] for r in before if r["protected"]
    )
    _write(folder / "fleet-report.json", report)
    print(f"FLEET REPORT: {folder / 'fleet-report.json'}", flush=True)
    return report


if __name__ == "__main__":
    run_vip_fleet(_manager(data_directory()), data_directory())

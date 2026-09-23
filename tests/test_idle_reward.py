from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.idle_reward import (
    IdleRewardObservation,
    IdleRewardResult,
    IdleRewardStatus,
    IdleRewardStep,
    IdleRewardTask,
)
from top_heroes_auto.automation.recovery import RecoveryResult, RecoveryStatus
from top_heroes_auto.storage.store import Store
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenDetection, ScreenState

ANCHORS = {
    ScreenState.GAME_HOME: "idle-adventure-portal",
    ScreenState.IDLE_ENTRY_AVAILABLE: "idle-entry-available",
    ScreenState.IDLE_ENTRY_NOT_AVAILABLE: "idle-entry-not-available",
    ScreenState.IDLE_REWARD_CLAIMABLE: "idle-claim-button",
    ScreenState.IDLE_REWARD_CLAIMED: "idle-claimed-continue",
}


def detection(state: ScreenState, anchor_override: str | None = None) -> ScreenDetection:
    anchor = anchor_override or ANCHORS.get(state)
    evidence = ()
    if anchor:
        evidence = (
            AnchorEvidence(
                anchor,
                state,
                1.0,
                0.9,
                True,
                BoundingBox(10, 20, 30, 40),
                BoundingBox(100, 200, 30, 40),
            ),
        )
    return ScreenDetection(
        state,
        1.0 if state != ScreenState.UNKNOWN else 0.0,
        evidence,
        datetime.now(timezone.utc).isoformat(),
        None,
        1.0,
    )


class Port:
    def __init__(self, *states: ScreenState, entry_anchor: str | None = None):
        self.states = list(states)
        self.actions = []
        self.observations = 0
        self.entry_anchor = entry_anchor

    def observe(self, tag):
        self.observations += 1
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        override = self.entry_anchor if state == ScreenState.IDLE_ENTRY_AVAILABLE else None
        return IdleRewardObservation(
            detection(state, override), Path(f"{tag}.png"), "emulator-5562"
        )

    def tap(self, current, anchor_id):
        matches = [item for item in current.evidence if item.anchor_id == anchor_id and item.matched]
        if len(matches) != 1:
            raise SafetyError("DO NOT TAP")
        self.actions.append(("tap", anchor_id))

    def back(self, current):
        if current.state == ScreenState.UNKNOWN:
            raise SafetyError("DO NOT PRESS BACK")
        self.actions.append(("back", current.state.value))


def task():
    return IdleRewardTask(settle_seconds=0, sleep=lambda _: None)


def test_claimable_flow_claims_once_and_returns_home():
    port = Port(
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.IDLE_REWARD_CLAIMABLE,
        ScreenState.IDLE_REWARD_CLAIMED,
        ScreenState.GAME_HOME,
    )
    result = task().run(port)
    assert result.status == IdleRewardStatus.SUCCESS
    assert result.claim_dispatched
    assert result.claim_result == "SUCCESS"
    assert result.postcondition_result == "VERIFIED"
    assert result.recovery_result == "VERIFIED"
    assert port.actions == [
        ("tap", "idle-adventure-portal"),
        ("tap", "idle-entry-available"),
        ("tap", "idle-claim-button"),
        ("tap", "idle-claimed-continue"),
    ]


def test_claimable_open_animation_uses_its_verified_action_anchor():
    port = Port(
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.IDLE_REWARD_CLAIMABLE,
        ScreenState.IDLE_REWARD_CLAIMED,
        ScreenState.GAME_HOME,
        entry_anchor="idle-entry-available-open",
    )
    result = task().run(port)
    assert result.status == IdleRewardStatus.SUCCESS
    assert ("tap", "idle-entry-available-open") in port.actions


def test_known_task_panel_is_closed_and_reentered_from_verified_home():
    port = Port(
        ScreenState.IDLE_REWARD_CLAIMABLE,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.IDLE_REWARD_CLAIMABLE,
        ScreenState.IDLE_REWARD_CLAIMED,
        ScreenState.GAME_HOME,
    )
    result = task().run(port)
    assert result.status == IdleRewardStatus.SUCCESS
    assert result.claim_dispatched
    assert port.actions == [
        ("back", ScreenState.IDLE_REWARD_CLAIMABLE.value),
        ("back", ScreenState.IDLE_ENTRY_AVAILABLE.value),
        ("tap", "idle-adventure-portal"),
        ("tap", "idle-entry-available"),
        ("tap", "idle-claim-button"),
        ("tap", "idle-claimed-continue"),
    ]


def test_verified_post_claim_panel_is_closed_without_retrying_claim():
    port = Port(
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.IDLE_REWARD_CLAIMABLE,
        ScreenState.IDLE_REWARD_CLAIMED,
        ScreenState.IDLE_REWARD_NOT_CLAIMABLE,
        ScreenState.IDLE_ENTRY_NOT_AVAILABLE,
        ScreenState.GAME_HOME,
    )
    result = task().run(port)
    assert result.status == IdleRewardStatus.SUCCESS
    assert result.claim_dispatched and result.recovery_result == "VERIFIED"
    assert port.actions.count(("tap", "idle-claim-button")) == 1
    assert port.actions[-2:] == [
        ("back", ScreenState.IDLE_REWARD_NOT_CLAIMABLE.value),
        ("back", ScreenState.IDLE_ENTRY_NOT_AVAILABLE.value),
    ]


def test_unavailable_entry_never_opens_or_claims_reward():
    port = Port(
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_NOT_AVAILABLE,
        ScreenState.GAME_HOME,
    )
    result = task().run(port)
    assert result.status == IdleRewardStatus.NOT_AVAILABLE
    assert not result.claim_dispatched
    assert port.actions == [
        ("tap", "idle-adventure-portal"),
        ("back", ScreenState.IDLE_ENTRY_NOT_AVAILABLE.value),
    ]


def test_unknown_precondition_fails_closed_without_input():
    port = Port(ScreenState.UNKNOWN)
    result = task().run(port)
    assert result.status == IdleRewardStatus.UNKNOWN_SCREEN
    assert port.actions == []


def test_ambiguous_post_claim_never_taps_claim_twice():
    port = Port(
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.IDLE_REWARD_CLAIMABLE,
        ScreenState.UNKNOWN,
    )
    result = task().run(port)
    assert result.status == IdleRewardStatus.ACTION_RESULT_UNCERTAIN
    assert result.claim_dispatched
    assert port.actions.count(("tap", "idle-claim-button")) == 1


def test_cancellation_after_claim_is_uncertain_and_never_retries():
    cancelled = False

    class CancelAfterClaimPort(Port):
        def tap(self, current, anchor_id):
            nonlocal cancelled
            super().tap(current, anchor_id)
            if anchor_id == "idle-claim-button":
                cancelled = True

    port = CancelAfterClaimPort(
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.IDLE_REWARD_CLAIMABLE,
    )
    result = task().run(port, cancelled=lambda: cancelled)
    assert result.status == IdleRewardStatus.ACTION_RESULT_UNCERTAIN
    assert result.claim_dispatched
    assert port.actions.count(("tap", "idle-claim-button")) == 1


def test_cancellation_before_capture_prevents_all_input():
    port = Port(ScreenState.GAME_HOME)
    result = task().run(port, cancelled=lambda: True)
    assert result.status == IdleRewardStatus.CANCELLED
    assert port.observations == 0
    assert port.actions == []


def test_return_home_failure_is_distinct_from_claim_result():
    port = Port(
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.IDLE_REWARD_CLAIMABLE,
        ScreenState.IDLE_REWARD_CLAIMED,
        ScreenState.UNKNOWN,
    )
    result = task().run(port)
    assert result.status == IdleRewardStatus.SUCCESS_WITH_RECOVERY_WARNING
    assert result.claim_dispatched
    assert result.claim_result == "SUCCESS"
    assert result.postcondition_result == "VERIFIED"
    assert result.recovery_result == "FAILED"


def test_verified_claim_never_becomes_action_uncertain_and_is_never_redispatched():
    port = Port(
        ScreenState.GAME_HOME,
        ScreenState.IDLE_ENTRY_AVAILABLE,
        ScreenState.IDLE_REWARD_CLAIMABLE,
        ScreenState.IDLE_REWARD_CLAIMED,
        ScreenState.UNKNOWN,
    )
    result = task().run(port)
    assert result.status != IdleRewardStatus.ACTION_RESULT_UNCERTAIN
    assert result.claim_result == "SUCCESS"
    assert result.postcondition_result == "VERIFIED"
    assert port.actions.count(("tap", "idle-claim-button")) == 1


def test_persistent_empty_inventory_fails_closed_after_bounded_rediscovery(rig, monkeypatch):
    from top_heroes_auto.ldplayer.client import LDPlayer

    _, process, _ = rig
    process.listing = "\n"
    monkeypatch.setattr(LDPlayer, "EMPTY_INVENTORY_DELAY", 0)
    calls_before = len(process.calls)
    with pytest.raises(ValueError, match="bounded rediscovery"):
        from top_heroes_auto.ldplayer.client import Installation
        LDPlayer(Installation(Path("ldconsole.exe"), Path("adb.exe")), process).list_instances()
    listing_calls = [call for call in process.calls[calls_before:] if call[1:] == ["list2"]]
    assert len(listing_calls) == LDPlayer.EMPTY_INVENTORY_ATTEMPTS


def test_temporary_empty_inventory_is_rediscovered_before_exact_target_use(rig, monkeypatch):
    from top_heroes_auto.ldplayer.client import LDPlayer

    manager, process, _ = rig
    monkeypatch.setattr(LDPlayer, "EMPTY_INVENTORY_DELAY", 0)
    original_run = process.run
    empty_once = {"pending": True}

    def transient_empty(args, timeout=20):
        if args[1:] == ["list2"] and empty_once["pending"]:
            empty_once["pending"] = False
            process.calls.append(args)
            return b""
        return original_run(args, timeout)

    process.run = transient_empty
    assert manager.query(7).name == "Farm-007"
    assert empty_once["pending"] is False


def test_ambiguous_rediscovered_target_identity_fails_closed(rig):
    from top_heroes_auto.app.diagnostic import _instance

    manager, process, _ = rig
    process.listing = "0,Main-Thang,1,2,1,101,102\n7,Other-Account,3,4,1,201,202\n"
    with pytest.raises(SafetyError, match="Identity mismatch"):
        _instance(manager, 7, "Farm-007")


def test_verified_journal_and_claim_survive_owned_cleanup_failure(rig, tmp_path, monkeypatch):
    from top_heroes_auto.app import task_cli

    manager, process, _ = rig
    process.listing = process.listing.replace("Main-Thang", "Queen")
    manager.refresh()
    monkeypatch.setattr(
        task_cli,
        "run_home_recovery",
        lambda *args, **kwargs: (RecoveryResult(RecoveryStatus.ALREADY_HOME), None, True),
    )
    original_execute = manager.execute

    def fail_owned_quit(index, action, **kwargs):
        if action == "quit":
            raise RuntimeError("owned cleanup failed")
        return original_execute(index, action, **kwargs)

    monkeypatch.setattr(manager, "execute", fail_owned_quit)

    class VerifiedClaim:
        def run(self, port, cancelled):
            claim = manager.store.reward_claims(manager.namespace, 7)[-1]
            manager.store.mark_reward_dispatch(claim["id"], claim["task_run_id"])
            return IdleRewardResult(
                IdleRewardStatus.SUCCESS_WITH_RECOVERY_WARNING,
                steps=[
                    IdleRewardStep(1, ScreenState.IDLE_REWARD_CLAIMABLE, 1.0, None, "claim_once"),
                    IdleRewardStep(2, ScreenState.IDLE_REWARD_CLAIMED, 0.994715, None),
                ],
                claim_dispatched=True,
                claim_result="SUCCESS",
                postcondition_result="VERIFIED",
                recovery_result="FAILED",
            )

    result, report_path, _, _ = task_cli.run_idle_reward_diagnostic(
        manager, tmp_path, 7, "Farm-007", task=VerifiedClaim()
    )
    assert result.claim_result == "SUCCESS"
    assert result.journal_result == "VERIFIED"
    assert result.cleanup_result == "FAILED"
    assert result.status == IdleRewardStatus.SUCCESS_WITH_RECOVERY_WARNING
    row = manager.store.reward_claims(manager.namespace, 7)[0]
    assert row["status"] == "VERIFIED"
    report = __import__("json").loads(report_path.read_text(encoding="utf-8"))
    assert report["cleanup_result"] == "FAILED"
    assert report["journal_result"] == "VERIFIED"


def test_task_persistence_keeps_not_available_distinct(tmp_path):
    store = Store(tmp_path / "config.sqlite3")
    run_id = store.create_task_run("install", "idle-reward", 4, "3-Chíp")
    store.finish_task_run(run_id, IdleRewardStatus.NOT_AVAILABLE, report_path="report.json")
    latest = store.latest_task_run("install", "idle-reward", 4)
    assert latest[0] == run_id
    assert latest[1:3] == ("3-Chíp", "NOT_AVAILABLE")
    assert latest[-1] == "report.json"


def test_protected_target_is_rejected_before_mutation(rig, tmp_path):
    from top_heroes_auto.app.task_cli import run_idle_reward_diagnostic

    manager, process, _ = rig
    process.listing = process.listing.replace("Main-Thang", "Queen")
    manager.refresh()
    manager.protect(7, True)
    process.calls.clear()
    with pytest.raises(SafetyError, match="selected and not Protected"):
        run_idle_reward_diagnostic(manager, tmp_path, 7, "Farm-007")
    assert not any(call[1] in {"launch", "quit", "-s"} for call in process.calls if len(call) > 1)


def test_task_specific_recovery_gets_safe_chance_after_generic_unknown(
    rig, tmp_path, monkeypatch
):
    from top_heroes_auto.app.task_cli import run_idle_reward_diagnostic

    manager, process, _ = rig
    process.listing = process.listing.replace("Main-Thang", "Queen")
    manager.refresh()
    recovery_report = tmp_path / "generic-recovery.json"
    recovery_report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "top_heroes_auto.app.task_cli.run_home_recovery",
        lambda *args, **kwargs: (
            RecoveryResult(RecoveryStatus.UNKNOWN_SCREEN),
            recovery_report,
            False,
        ),
    )

    class SafeTaskFallback:
        def run(self, port, cancelled):
            return IdleRewardResult(IdleRewardStatus.NOT_AVAILABLE)

    result, report, started, _ = run_idle_reward_diagnostic(
        manager,
        tmp_path,
        7,
        "Farm-007",
        task=SafeTaskFallback(),
    )
    assert result.status == IdleRewardStatus.NOT_AVAILABLE
    assert report.is_file()
    assert not started
    assert not any(call[1] in {"launch", "quit", "-s"} for call in process.calls if len(call) > 1)

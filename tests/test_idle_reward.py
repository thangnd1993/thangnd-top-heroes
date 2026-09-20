from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.idle_reward import (
    IdleRewardObservation,
    IdleRewardResult,
    IdleRewardStatus,
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
    assert result.claim_dispatched and result.cleanup_succeeded
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
    assert result.claim_dispatched and result.cleanup_succeeded
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
    assert result.status == IdleRewardStatus.CLEANUP_FAILED
    assert result.claim_dispatched
    assert not result.cleanup_succeeded


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

"""Durable dispatch boundary shared by Phase 6 explorer/task adapters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from top_heroes_auto.automation.free_rewards import (
    ClaimOutcome,
    ExplorerPort,
    RewardEvidence,
    RewardScreen,
    verified_anchor,
)
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.storage.store import Store


@dataclass(frozen=True)
class RewardCycle:
    """Adapter-proven semantic cycle; never derive from capture/boot/local time.

    The anchor must independently identify the opportunity in the current frame.
    If a reset cannot be proven, keep a fixed conservative key rather than permit
    another claim merely because the application or device was restarted.
    """

    key: str
    anchor: str


def evidence_json(screen: RewardScreen) -> str:
    return json.dumps({
        "index": screen.index, "name": screen.name,
        "adb_target": screen.adb_target, "boot_id": screen.boot_id,
        "capture_id": screen.capture_id, "page": screen.page,
        "fingerprint": screen.fingerprint, "detection": screen.detection.as_dict(),
    }, ensure_ascii=False, allow_nan=False)


class JournalledExplorerPort:
    """No device call occurs unless the write-ahead intent commits successfully.

    Compose this with a real adapter, never replace the explorer's FreeRewardGuard.
    A failed dispatch, postcondition or receipt write retains RESERVED permanently.
    """

    def __init__(
        self, port: ExplorerPort, store: Store, task_run_id: int,
        index: int, name: str,
        cycle: Callable[[RewardScreen, RewardEvidence], RewardCycle],
    ):
        self.port, self.store, self.task_run_id = port, store, task_run_id
        self.identity, self.cycle = (index, name), cycle
        self.pending: dict[str, tuple[int, str]] = {}

    def observe(self):
        return self.port.observe()

    def dismiss_receipts(self, screen):
        dismiss = getattr(self.port, "dismiss_receipts", None)
        return dismiss(screen) if callable(dismiss) else screen

    def validate_claim(self, screen, reward, point):
        validate = getattr(self.port, "validate_claim", None)
        if callable(validate):
            validate(screen, reward, point)

    def claim(self, screen, reward, point):
        if (screen.index, screen.name) != self.identity or reward.reward_id in self.pending:
            raise SafetyError("Claim journal identity changed or reward already attempted.")
        cycle = self.cycle(screen, reward)
        verified_anchor(screen.detection, cycle.anchor)
        claim_id = self.store.reserve_reward_claim(
            self.task_run_id, reward.reward_id, cycle.key, evidence_json(screen),
            expected_instance=self.identity,
        )
        self.pending[reward.reward_id] = claim_id, screen.capture_id
        self.port.claim(screen, reward, point)

    def verify_claim(self, before, after, reward):
        return self.classify_claim(before, after, reward) in {
            ClaimOutcome.CLAIMED,
        }

    def classify_claim(self, before, after, reward):
        pending = self.pending.get(reward.reward_id)
        if (not pending or pending[1] != before.capture_id
                or after.capture_id == before.capture_id
                or (after.index, after.name) != self.identity
                or (before.adb_target, before.boot_id) != (after.adb_target, after.boot_id)):
            return ClaimOutcome.IDENTITY_MISMATCH
        classifier = getattr(self.port, "classify_claim", None)
        if callable(classifier):
            outcome = classifier(before, after, reward)
        else:
            outcome = ClaimOutcome.CLAIMED if self.port.verify_claim(before, after, reward) else ClaimOutcome.UNKNOWN
        if not isinstance(outcome, ClaimOutcome):
            try:
                outcome = ClaimOutcome(str(outcome))
            except ValueError:
                outcome = ClaimOutcome.UNKNOWN
        if outcome != ClaimOutcome.CLAIMED:
            return outcome
        self.store.verify_reward_claim(pending[0], self.task_run_id, evidence_json(after))
        return outcome

    def navigate(self, screen, route, point):
        return self.port.navigate(screen, route, point)

    def scroll(self, screen, axis):
        return self.port.scroll(screen, axis)

    def return_home(self, screen):
        return self.port.return_home(screen)

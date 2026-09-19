from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from top_heroes_auto.app.process import CommandError
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.image_normalizer import ScreenshotInvalid
from top_heroes_auto.vision.models import ScreenDetection, ScreenState

IDLE_ENTRY_ACTION_ANCHORS = frozenset(
    {"idle-entry-available", "idle-entry-available-open"}
)


class IdleRewardStatus(StrEnum):
    SUCCESS = "SUCCESS"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    UNKNOWN_SCREEN = "UNKNOWN_SCREEN"
    ACTION_FAILED = "ACTION_FAILED"
    ACTION_RESULT_UNCERTAIN = "ACTION_RESULT_UNCERTAIN"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class IdleRewardObservation:
    detection: ScreenDetection
    screenshot: Path | None
    adb_target: str


class IdleRewardPort(Protocol):
    def observe(self, tag: str) -> IdleRewardObservation: ...

    def tap(self, detection: ScreenDetection, anchor_id: str) -> None: ...

    def back(self, detection: ScreenDetection) -> None: ...


@dataclass(frozen=True)
class IdleRewardStep:
    number: int
    state: ScreenState
    confidence: float
    screenshot: Path | None
    action: str | None = None

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "state": self.state.value,
            "confidence": round(self.confidence, 6),
            "screenshot": str(self.screenshot) if self.screenshot else None,
            "action": self.action,
        }


@dataclass
class IdleRewardResult:
    status: IdleRewardStatus
    steps: list[IdleRewardStep] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    adb_target: str | None = None
    claim_dispatched: bool = False
    cleanup_succeeded: bool = False
    duration: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "result": self.status.value,
            "initial_state": self.steps[0].state.value if self.steps else None,
            "final_state": self.steps[-1].state.value if self.steps else None,
            "claim_dispatched": self.claim_dispatched,
            "cleanup_succeeded": self.cleanup_succeeded,
            "actions": list(self.actions),
            "screenshots": [str(step.screenshot) for step in self.steps if step.screenshot],
            "steps": [step.as_dict() for step in self.steps],
            "adb_target": self.adb_target,
            "duration_seconds": round(self.duration, 3),
            "error": self.error,
        }


class IdleRewardTask:
    """Evidence-gated idle reward flow with no claim retry after dispatch."""

    def __init__(
        self,
        *,
        max_duration: float = 60.0,
        observe_retries: int = 4,
        settle_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.max_duration = max_duration
        self.observe_retries = observe_retries
        self.settle_seconds = settle_seconds
        self.clock = clock
        self.sleep = sleep

    def run(
        self,
        port: IdleRewardPort,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> IdleRewardResult:
        started = self.clock()
        result = IdleRewardResult(IdleRewardStatus.ACTION_FAILED)
        counter = 0

        def finish(status: IdleRewardStatus, error: str | None = None):
            result.status = status
            result.error = error
            result.duration = self.clock() - started
            return result

        def check_cancelled():
            if cancelled():
                raise _Cancelled
            if self.clock() - started >= self.max_duration:
                raise _TimedOut

        def observe(tag: str) -> IdleRewardObservation:
            nonlocal counter
            check_cancelled()
            counter += 1
            observation = port.observe(f"{counter:03d}-{tag}")
            if result.adb_target is not None and observation.adb_target != result.adb_target:
                raise SafetyError("ADB target changed during Idle Reward task.")
            result.adb_target = observation.adb_target
            result.steps.append(
                IdleRewardStep(
                    counter,
                    observation.detection.state,
                    observation.detection.confidence,
                    observation.screenshot,
                )
            )
            return observation

        def observe_until(tag: str, accepted: set[ScreenState]) -> IdleRewardObservation | None:
            for attempt in range(self.observe_retries):
                observation = observe(f"{tag}-{attempt + 1}")
                if observation.detection.state in accepted:
                    return observation
                if observation.detection.state != ScreenState.UNKNOWN:
                    return observation
                check_cancelled()
                self.sleep(self.settle_seconds)
            return None

        def action(
            name: str,
            callback: Callable[[], None],
            after_dispatch: Callable[[], None] = lambda: None,
        ):
            check_cancelled()
            callback()
            after_dispatch()
            result.actions.append(name)
            previous = result.steps[-1]
            result.steps[-1] = IdleRewardStep(
                previous.number,
                previous.state,
                previous.confidence,
                previous.screenshot,
                name,
            )
            check_cancelled()
            self.sleep(self.settle_seconds)

        def return_from_adventure(observation: IdleRewardObservation) -> bool:
            action("back_to_game_home", lambda: port.back(observation.detection))
            home = observe_until("return-home", {ScreenState.GAME_HOME})
            return bool(home and home.detection.state == ScreenState.GAME_HOME)

        try:
            home = observe("game-home")
            if home.detection.state != ScreenState.GAME_HOME:
                return finish(IdleRewardStatus.UNKNOWN_SCREEN, "GAME_HOME portal anchor was not verified.")
            action(
                "open_adventure",
                lambda: port.tap(home.detection, "idle-adventure-portal"),
            )
            entry = observe_until(
                "adventure-entry",
                {ScreenState.IDLE_ENTRY_AVAILABLE, ScreenState.IDLE_ENTRY_NOT_AVAILABLE},
            )
            if entry is None or entry.detection.state not in {
                ScreenState.IDLE_ENTRY_AVAILABLE,
                ScreenState.IDLE_ENTRY_NOT_AVAILABLE,
            }:
                return finish(IdleRewardStatus.UNKNOWN_SCREEN, "Idle Reward entry state was not verified.")
            if entry.detection.state == ScreenState.IDLE_ENTRY_NOT_AVAILABLE:
                if not return_from_adventure(entry):
                    return finish(IdleRewardStatus.CLEANUP_FAILED, "Reward unavailable; return Home failed.")
                result.cleanup_succeeded = True
                return finish(IdleRewardStatus.NOT_AVAILABLE)

            entry_anchor = next(
                (
                    item.anchor_id
                    for item in entry.detection.evidence
                    if item.matched and item.anchor_id in IDLE_ENTRY_ACTION_ANCHORS
                ),
                None,
            )
            if entry_anchor is None:
                return finish(
                    IdleRewardStatus.UNKNOWN_SCREEN,
                    "Claimable Idle Reward entry action anchor was not verified.",
                )

            action(
                "open_idle_reward",
                lambda: port.tap(entry.detection, entry_anchor),
            )
            reward = observe_until(
                "idle-reward",
                {ScreenState.IDLE_REWARD_CLAIMABLE, ScreenState.IDLE_REWARD_NOT_CLAIMABLE},
            )
            if reward is None:
                return finish(IdleRewardStatus.UNKNOWN_SCREEN, "Idle Reward screen was not verified.")
            if reward.detection.state == ScreenState.IDLE_REWARD_NOT_CLAIMABLE:
                action("close_idle_reward", lambda: port.back(reward.detection))
                entry = observe_until(
                    "entry-after-close",
                    {ScreenState.IDLE_ENTRY_AVAILABLE, ScreenState.IDLE_ENTRY_NOT_AVAILABLE},
                )
                if entry is None or not return_from_adventure(entry):
                    return finish(IdleRewardStatus.CLEANUP_FAILED, "Reward unavailable; return Home failed.")
                result.cleanup_succeeded = True
                return finish(IdleRewardStatus.NOT_AVAILABLE)
            if reward.detection.state != ScreenState.IDLE_REWARD_CLAIMABLE:
                return finish(IdleRewardStatus.UNKNOWN_SCREEN, "Claimable state was not verified.")

            # A claim is intentionally never retried. Any uncertain postcondition
            # ends the task without another tap.
            action(
                "claim_once",
                lambda: port.tap(reward.detection, "idle-claim-button"),
                lambda: setattr(result, "claim_dispatched", True),
            )
            claimed = observe_until("post-claim", {ScreenState.IDLE_REWARD_CLAIMED})
            if claimed is None or claimed.detection.state != ScreenState.IDLE_REWARD_CLAIMED:
                return finish(
                    IdleRewardStatus.ACTION_RESULT_UNCERTAIN,
                    "Claim was dispatched once but its result could not be verified; no retry sent.",
                )
            action(
                "dismiss_verified_reward",
                lambda: port.tap(claimed.detection, "idle-claimed-continue"),
            )
            final = observe_until("final-home", {ScreenState.GAME_HOME})
            if final is None or final.detection.state != ScreenState.GAME_HOME:
                return finish(IdleRewardStatus.CLEANUP_FAILED, "Claim succeeded but GAME_HOME was not restored.")
            result.cleanup_succeeded = True
            return finish(IdleRewardStatus.SUCCESS)
        except _Cancelled:
            if result.claim_dispatched:
                return finish(
                    IdleRewardStatus.ACTION_RESULT_UNCERTAIN,
                    "Cancelled after the single claim dispatch; no retry sent.",
                )
            return finish(IdleRewardStatus.CANCELLED)
        except _TimedOut:
            if result.claim_dispatched:
                return finish(
                    IdleRewardStatus.ACTION_RESULT_UNCERTAIN,
                    "Timed out after the single claim dispatch; no retry sent.",
                )
            return finish(IdleRewardStatus.TIMEOUT)
        except (CommandError, OSError, ScreenshotInvalid, SafetyError, ValueError) as exc:
            return finish(IdleRewardStatus.ACTION_FAILED, str(exc))


class _Cancelled(Exception):
    pass


class _TimedOut(Exception):
    pass

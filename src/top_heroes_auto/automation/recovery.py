from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from top_heroes_auto.app.process import CommandError
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import ScreenDetection, ScreenState


class RecoveryStatus(StrEnum):
    SUCCESS = "SUCCESS"
    ALREADY_HOME = "ALREADY_HOME"
    UNKNOWN_SCREEN = "UNKNOWN_SCREEN"
    LOADING_TIMEOUT = "LOADING_TIMEOUT"
    ACTION_FAILED = "ACTION_FAILED"
    ADB_ERROR = "ADB_ERROR"
    CANCELLED = "CANCELLED"
    LIMIT_REACHED = "LIMIT_REACHED"


@dataclass(frozen=True)
class RecoveryObservation:
    detection: ScreenDetection
    screenshot: Path | None
    adb_target: str


class RecoveryPort(Protocol):
    def observe(self, step: int) -> RecoveryObservation: ...

    def launch_game(self) -> None: ...


@dataclass(frozen=True)
class RecoveryStep:
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
class RecoveryResult:
    status: RecoveryStatus
    steps: list[RecoveryStep] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    adb_target: str | None = None
    duration: float = 0.0
    error: str | None = None

    @property
    def states_seen(self) -> list[str]:
        return [step.state.value for step in self.steps]

    @property
    def screenshots(self) -> list[str]:
        return [str(step.screenshot) for step in self.steps if step.screenshot]

    def as_dict(self) -> dict:
        return {
            "result": self.status.value,
            "initial_state": self.steps[0].state.value if self.steps else None,
            "states_seen": self.states_seen,
            "actions": list(self.actions),
            "final_state": self.steps[-1].state.value if self.steps else None,
            "screenshots": self.screenshots,
            "steps": [step.as_dict() for step in self.steps],
            "duration_seconds": round(self.duration, 3),
            "adb_target": self.adb_target,
            "error": self.error,
        }


class HomeRecoveryEngine:
    def __init__(
        self,
        *,
        max_steps: int = 30,
        max_duration: float = 120.0,
        loading_timeout: float = 90.0,
        loading_interval: float = 5.0,
        action_settle: float = 2.0,
        unknown_confirmations: int = 2,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.max_steps = max_steps
        self.max_duration = max_duration
        self.loading_timeout = loading_timeout
        self.loading_interval = loading_interval
        self.action_settle = action_settle
        self.unknown_confirmations = unknown_confirmations
        self.clock = clock
        self.sleep = sleep

    def ensure_game_home(
        self,
        port: RecoveryPort,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> RecoveryResult:
        started = self.clock()
        result = RecoveryResult(RecoveryStatus.LIMIT_REACHED)
        loading_started: float | None = None
        unknown_count = 0
        launched = False

        def finish(status: RecoveryStatus, error: str | None = None):
            result.status = status
            result.error = error
            result.duration = self.clock() - started
            return result

        for number in range(1, self.max_steps + 1):
            if cancelled():
                return finish(RecoveryStatus.CANCELLED)
            if self.clock() - started >= self.max_duration:
                return finish(RecoveryStatus.LIMIT_REACHED, "Recovery exceeded max duration.")
            try:
                observation = port.observe(number)
            except (CommandError, OSError, SafetyError, ValueError) as exc:
                return finish(RecoveryStatus.ADB_ERROR, str(exc))
            detection = observation.detection
            result.adb_target = observation.adb_target
            step = RecoveryStep(
                number,
                detection.state,
                detection.confidence,
                observation.screenshot,
            )
            result.steps.append(step)
            if detection.state == ScreenState.GAME_HOME:
                return finish(RecoveryStatus.SUCCESS if result.actions else RecoveryStatus.ALREADY_HOME)
            if detection.state == ScreenState.UNKNOWN:
                if loading_started is not None:
                    if self.clock() - loading_started >= self.loading_timeout:
                        return finish(
                            RecoveryStatus.LOADING_TIMEOUT,
                            "Loading transition remained UNKNOWN past timeout; no input sent.",
                        )
                    if cancelled():
                        return finish(RecoveryStatus.CANCELLED)
                    result.actions.append("wait")
                    result.steps[-1] = RecoveryStep(
                        step.number,
                        step.state,
                        step.confidence,
                        step.screenshot,
                        "wait",
                    )
                    self.sleep(self.loading_interval)
                    continue
                unknown_count += 1
                if unknown_count >= self.unknown_confirmations:
                    return finish(RecoveryStatus.UNKNOWN_SCREEN, "Screen remained UNKNOWN; no input sent.")
                if cancelled():
                    return finish(RecoveryStatus.CANCELLED)
                self.sleep(self.action_settle)
                continue
            unknown_count = 0
            if detection.state == ScreenState.ANDROID_HOME:
                if launched:
                    return finish(RecoveryStatus.ACTION_FAILED, "Game launch did not change Android home.")
                if cancelled():
                    return finish(RecoveryStatus.CANCELLED)
                try:
                    port.launch_game()
                except (CommandError, OSError, SafetyError, ValueError) as exc:
                    return finish(RecoveryStatus.ACTION_FAILED, str(exc))
                launched = True
                result.actions.append("launch_game")
                result.steps[-1] = RecoveryStep(
                    step.number,
                    step.state,
                    step.confidence,
                    step.screenshot,
                    "launch_game",
                )
                self.sleep(self.action_settle)
                continue
            if detection.state == ScreenState.GAME_LOADING:
                if loading_started is None:
                    loading_started = self.clock()
                if self.clock() - loading_started >= self.loading_timeout:
                    return finish(RecoveryStatus.LOADING_TIMEOUT, "GAME_LOADING exceeded timeout.")
                if cancelled():
                    return finish(RecoveryStatus.CANCELLED)
                result.actions.append("wait")
                result.steps[-1] = RecoveryStep(
                    step.number,
                    step.state,
                    step.confidence,
                    step.screenshot,
                    "wait",
                )
                self.sleep(self.loading_interval)
                continue
            return finish(
                RecoveryStatus.ACTION_FAILED,
                f"No verified safe handler for {detection.state.value}.",
            )
        return finish(RecoveryStatus.LIMIT_REACHED, "Recovery exceeded max steps.")

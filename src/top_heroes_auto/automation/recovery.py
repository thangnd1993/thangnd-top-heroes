from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from top_heroes_auto.app.process import CommandError
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import DISMISSIBLE, OverlayBudget, overlay_signature
from top_heroes_auto.vision.image_normalizer import ScreenshotInvalid
from top_heroes_auto.vision.loading_progress import progressing_stage
from top_heroes_auto.vision.models import ScreenDetection, ScreenState


class RecoveryStatus(StrEnum):
    SUCCESS = "SUCCESS"
    ALREADY_HOME = "ALREADY_HOME"
    UNKNOWN_SCREEN = "UNKNOWN_SCREEN"
    LOADING_TIMEOUT = "LOADING_TIMEOUT"
    PROMO_BLOCKING = "PROMO_BLOCKING"
    ACTION_FAILED = "ACTION_FAILED"
    ADB_ERROR = "ADB_ERROR"
    SCREEN_NOT_READY = "SCREEN_NOT_READY"
    CANCELLED = "CANCELLED"
    LIMIT_REACHED = "LIMIT_REACHED"


@dataclass(frozen=True)
class RecoveryObservation:
    detection: ScreenDetection
    screenshot: Path | None
    adb_target: str
    boot_id: str | None = None


class RecoveryPort(Protocol):
    def observe(self, step: int) -> RecoveryObservation: ...

    def launch_game(self) -> None: ...

    def back_from_hanging(self, observation: RecoveryObservation) -> tuple[int, int]: ...

    def back_from_war(self, observation: RecoveryObservation) -> tuple[int, int]: ...

    def dismiss_overlay(self, observation: RecoveryObservation) -> tuple[int, int]: ...


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
    boot_id: str | None = None
    launch_attempt: dict | None = None
    ownership_uncertain: bool = False

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
            "boot_id": self.boot_id,
            "launch_attempt": self.launch_attempt,
            "ownership_uncertain": self.ownership_uncertain,
            "error": self.error,
        }


def confirm_final_home(
    result: RecoveryResult,
    observation: RecoveryObservation | None,
    *,
    duration: float,
    max_duration: float,
    max_steps: int,
) -> bool:
    """Use the already-required final capture only within the original budget.

    A new positive Home frame can settle a loading timeout before owned cleanup.
    This function performs no launch, wait, input, or additional capture.
    """
    if (
        result.status != RecoveryStatus.LOADING_TIMEOUT
        or observation is None
        or observation.detection.state != ScreenState.GAME_HOME
        or not observation.screenshot
        or not result.adb_target
        or not result.boot_id
        or (observation.adb_target, observation.boot_id) != (result.adb_target, result.boot_id)
        or not result.duration <= duration < max_duration
        or not result.steps
        or result.steps[-1].number >= max_steps
    ):
        return False
    result.steps.append(
        RecoveryStep(
            result.steps[-1].number + 1,
            ScreenState.GAME_HOME,
            observation.detection.confidence,
            observation.screenshot,
            "verify_final_home",
        )
    )
    result.actions.append("verify_final_home")
    result.status, result.error, result.duration = RecoveryStatus.SUCCESS, None, duration
    return True


class HomeRecoveryEngine:
    def __init__(
        self,
        *,
        max_steps: int = 30,
        max_duration: float = 120.0,
        loading_timeout: float = 90.0,
        loading_interval: float = 5.0,
        initial_blank_retries: int = 2,
        initial_blank_interval: float = 2.0,
        action_settle: float = 2.0,
        unknown_confirmations: int = 2,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.max_steps = max_steps
        self.max_duration = max_duration
        self.loading_timeout = loading_timeout
        self.loading_interval = loading_interval
        self.initial_blank_retries = initial_blank_retries
        self.initial_blank_interval = initial_blank_interval
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
        initial_blank_count = 0
        unknown_count = 0
        launched = False
        overlays = OverlayBudget()
        stable_overlay = None
        hanging_backs = 0
        hanging_departed = False
        navigation_state = None
        capture_after_back = False
        progress_seen = False
        duration_limit = self.max_duration

        def finish(status: RecoveryStatus, error: str | None = None):
            result.status = status
            result.error = error
            result.duration = self.clock() - started
            return result

        for number in range(1, self.max_steps + 1):
            if cancelled():
                return finish(RecoveryStatus.CANCELLED)
            if self.clock() - started >= duration_limit and not capture_after_back:
                return finish(RecoveryStatus.LIMIT_REACHED, "Recovery exceeded max duration.")
            following_back = capture_after_back
            capture_after_back = False
            try:
                observation = port.observe(number)
            except ScreenshotInvalid as exc:
                if loading_started is None:
                    if exc.blank_frame and initial_blank_count < self.initial_blank_retries:
                        initial_blank_count += 1
                        result.steps.append(
                            RecoveryStep(number, ScreenState.UNKNOWN, 0.0, None, "wait")
                        )
                        result.actions.append("wait")
                        if cancelled():
                            return finish(RecoveryStatus.CANCELLED)
                        self.sleep(self.initial_blank_interval)
                        continue
                    result.steps.append(
                        RecoveryStep(number, ScreenState.UNKNOWN, 0.0, None)
                    )
                    return finish(
                        RecoveryStatus.SCREEN_NOT_READY,
                        f"Initial screenshot remained invalid after {initial_blank_count + 1} capture(s); no input sent: {exc}",
                    )
                if self.clock() - loading_started >= self.loading_timeout:
                    return finish(
                        RecoveryStatus.LOADING_TIMEOUT,
                        "Loading transition remained blank past timeout; no input sent.",
                    )
                result.steps.append(
                    RecoveryStep(number, ScreenState.UNKNOWN, 0.0, None, "wait")
                )
                result.actions.append("wait")
                if cancelled():
                    return finish(RecoveryStatus.CANCELLED)
                self.sleep(self.loading_interval)
                continue
            except (CommandError, OSError, SafetyError, ValueError) as exc:
                return finish(RecoveryStatus.ADB_ERROR, str(exc))
            detection = observation.detection
            result.adb_target = observation.adb_target
            result.boot_id = observation.boot_id
            # A newly qualified functional loading stage is independent evidence
            # of progress. Grant one bounded wait window, never for UNKNOWN/art.
            if progressing_stage(detection) and not progress_seen:
                progress_seen = True
                if loading_started is not None:
                    loading_started = self.clock()
                    duration_limit = self.max_duration + min(60.0, self.loading_timeout)
                    result.actions.append('qualified_loading_progress')
                else:
                    result.actions.append('qualified_loading_stage')
            step = RecoveryStep(
                number,
                detection.state,
                detection.confidence,
                observation.screenshot,
            )
            result.steps.append(step)
            if following_back and self.clock() - started >= self.max_duration:
                return finish(RecoveryStatus.LIMIT_REACHED, "Post-Back capture completed after deadline; no further input.")
            if hanging_backs and detection.state != navigation_state:
                hanging_departed = True
            if detection.state in {ScreenState.TREO_THUONG, ScreenState.WAR_EMPTY}:
                if (hanging_departed or hanging_backs >= 2 or number == self.max_steps
                        or self.clock() - started >= self.max_duration):
                    return finish(RecoveryStatus.LIMIT_REACHED, "Qualified page Back bound reached; no further input.")
                if cancelled():
                    return finish(RecoveryStatus.CANCELLED)
                try:
                    navigation_state = detection.state
                    method = "back_from_war" if navigation_state == ScreenState.WAR_EMPTY else "back_from_hanging"
                    point = getattr(port, method)(observation)
                except (CommandError, OSError, SafetyError, ValueError) as exc:
                    return finish(RecoveryStatus.ACTION_FAILED, str(exc))
                hanging_backs += 1
                capture_after_back = True
                action = f"{method}:{point[0]},{point[1]}"
                result.actions.append(action)
                result.steps[-1] = RecoveryStep(number, detection.state, detection.confidence,
                                               observation.screenshot, action)
                loading_started = None
                self.sleep(self.action_settle)
                continue  # Fresh qualified observation required before any next input.
            if detection.state == ScreenState.GAME_HOME:
                return finish(RecoveryStatus.SUCCESS if result.actions else RecoveryStatus.ALREADY_HOME)
            if detection.state in DISMISSIBLE:
                signature = overlay_signature(detection)
                # Wait for a second current classified frame before any overlay input.
                if stable_overlay != signature:
                    stable_overlay = signature
                    result.actions.append("wait_overlay_stable")
                    self.sleep(self.action_settle)
                    continue
                if cancelled():
                    return finish(RecoveryStatus.CANCELLED)
                if number == self.max_steps:
                    return finish(RecoveryStatus.LIMIT_REACHED, 'No capture budget remains after a dismissal.')
                try:
                    overlays.reserve(detection)
                    home_back = getattr(port, 'dismiss_home_overlay_back', None)
                    if (detection.state == ScreenState.HOME_OVERLAY
                            and overlays.counts[signature] == 2 and callable(home_back)):
                        home_back(observation)
                        action = 'dismiss_home_overlay_back'
                    else:
                        point = port.dismiss_overlay(observation)
                        action = f"dismiss_overlay_bottom_left:{point[0]},{point[1]}"
                except (CommandError, OSError, SafetyError, ValueError) as exc:
                    return finish(RecoveryStatus.PROMO_BLOCKING, str(exc))
                result.actions.append(action)
                result.steps[-1] = RecoveryStep(number, detection.state, detection.confidence,
                                               observation.screenshot, action)
                loading_started = None
                self.sleep(self.action_settle)
                continue  # Next iteration always captures and classifies a fresh frame.
            stable_overlay = None
            if overlays.total and detection.state == ScreenState.UNKNOWN:
                unknown_count += 1
                if unknown_count >= self.unknown_confirmations:
                    return finish(RecoveryStatus.UNKNOWN_SCREEN, "Unknown destination after overlay dismissal; no further input.")
                self.sleep(self.action_settle)
                continue
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
                loading_started = self.clock()
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
            if detection.state in {ScreenState.GAME_LOADING, ScreenState.PROMO_LOADING}:
                if loading_started is None:
                    loading_started = self.clock()
                if self.clock() - loading_started >= self.loading_timeout:
                    if detection.state == ScreenState.PROMO_LOADING:
                        return finish(
                            RecoveryStatus.LOADING_TIMEOUT,
                            "Game loading with promotional artwork exceeded timeout; Home not reached, no input sent.",
                        )
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


def wait_for_final_loading_progress(result, observation, port, engine, cancelled=lambda: False):
    """One capture-only grace when final evidence proves a NEW loading phase.

    Absolute original-start and original-step budgets remain bounded. No launch,
    Back, dismiss, claim or other input is available on this path.
    """
    if (result.status != RecoveryStatus.LOADING_TIMEOUT or observation is None
            or not progressing_stage(observation.detection)
            or any(a in result.actions for a in ('qualified_loading_progress','qualified_loading_stage'))
            or not any(step.state == ScreenState.GAME_LOADING for step in result.steps)
            or not result.boot_id or not result.adb_target
            or (observation.adb_target,observation.boot_id)!=(result.adb_target,result.boot_id)):
        return False
    absolute=port.started+engine.max_duration+min(60.0,engine.loading_timeout)
    deadline=min(absolute,port.clock()+30.0)
    result.actions.append('qualified_loading_progress')
    number=result.steps[-1].number if result.steps else 0
    while number < engine.max_steps and not cancelled() and port.clock() < deadline:
        engine.sleep(min(engine.loading_interval,deadline-port.clock()))
        if cancelled() or port.clock() >= deadline:
            break
        number+=1
        try:
            fresh=port.observe(number)
        except (CommandError,OSError,SafetyError,ValueError,ScreenshotInvalid) as exc:
            result.error=f'Loading progress capture failed closed: {exc}'
            break
        if port.clock() >= deadline:
            result.error='Loading grace capture crossed deadline; no input.'
            break
        if (fresh.adb_target,fresh.boot_id)!=(result.adb_target,result.boot_id):
            result.error='Loading progress identity changed; no input.'
            break
        state=fresh.detection.state
        result.steps.append(RecoveryStep(number,state,fresh.detection.confidence,fresh.screenshot,'wait'))
        result.actions.append('wait')
        if state==ScreenState.GAME_HOME:
            result.status,result.error=RecoveryStatus.SUCCESS,None
            result.duration=port.clock()-port.started
            return True
        if not progressing_stage(fresh.detection):
            result.error='Loading progress left qualified state; no input.'
            break
    result.duration=port.clock()-port.started
    return False

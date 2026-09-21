"""Guarded Home → Phase 6 entry navigation.

Navigation is deliberately separate from reward claiming.  Each action uses a
fresh screenshot, a unique current-frame anchor, and the Manager's exact
observed-target guard.  A fresh destination capture is required before the
next action; an uncertain or missing destination stops the route.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import CapturedScreen, ScreenDetection, ScreenState, VisualAnchor
from top_heroes_auto.vision.screenshot import ScreenshotService


class NavigationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    DESTINATION_UNVERIFIED = "DESTINATION_UNVERIFIED"
    ACTION_RESULT_UNCERTAIN = "ACTION_RESULT_UNCERTAIN"


class _ActionUncertain(RuntimeError):
    pass


class _Cancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class EntryFrame:
    target: Target
    screen: CapturedScreen

    @property
    def capture_id(self) -> str:
        if self.screen.source_image:
            return str(self.screen.source_image)
        digest = hashlib.sha256(self.screen.normalized.tobytes()).hexdigest()
        return f"frame:{self.screen.timestamp}:{digest}"


class EntryPort(Protocol):
    def observe(self, tag: str) -> EntryFrame: ...

    def tap(self, frame: EntryFrame, point: tuple[int, int]) -> None: ...


@dataclass(frozen=True)
class EntryProfile:
    task: str
    first_anchor: VisualAnchor
    first_destination: VisualAnchor
    second_anchor: VisualAnchor | None = None
    second_destination: VisualAnchor | None = None

    def __post_init__(self):
        if (self.second_anchor is None) != (self.second_destination is None):
            raise ValueError("Second navigation action and destination must be paired.")


@dataclass
class NavigationResult:
    status: NavigationStatus
    actions: list[str] = field(default_factory=list)
    captures: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "result": self.status.value,
            "actions": list(self.actions),
            "captures": list(self.captures),
            "error": self.error,
        }


class ManagerEntryPort(EntryPort):
    """Capture and dispatch only through Manager's explicit target boundary."""

    def __init__(
        self,
        manager: Manager,
        snapshot: RunSnapshot,
        index: int,
        name: str,
        folder: Path | None = None,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.folder = folder
        self._target: Target | None = None

    def observe(self, tag: str) -> EntryFrame:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        if (target.index, target.name) != (self.index, self.name):
            raise SafetyError("Entry capture identity changed.")
        if self._target and (target.serial, target.boot_id) != (self._target.serial, self._target.boot_id):
            raise SafetyError("Entry capture transport identity changed.")
        self._target = target
        captured = ScreenshotService(lambda serial: payload if serial == target.serial else b"").take(
            target, self.folder, tag
        )
        return EntryFrame(target, captured)

    def tap(self, frame: EntryFrame, point: tuple[int, int]) -> None:
        if self._target != frame.target:
            raise SafetyError("Entry action target is stale or changed.")
        self.manager.execute(
            self.index,
            "tap",
            values=point,
            snapshot=self.snapshot,
            observed_target=frame.target,
        )
        self._target = None


class GuardedEntryNavigator:
    """Navigate one- or two-step entry routes without coordinate reuse."""

    def __init__(
        self,
        port: EntryPort,
        profile: EntryProfile,
        home_detector: Callable[[CapturedScreen], ScreenDetection],
        *,
        destination_observations: int = 1,
        destination_wait_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if destination_observations < 1:
            raise ValueError("At least one destination observation is required.")
        if destination_wait_seconds < 0:
            raise ValueError("Destination wait cannot be negative.")
        self.port = port
        self.profile = profile
        self.home_detector = home_detector
        self.destination_observations = destination_observations
        self.destination_wait_seconds = destination_wait_seconds
        self.sleep = sleep
        self._identity: tuple[int, str, str, str] | None = None

    @staticmethod
    def _match(screen: CapturedScreen, anchor: VisualAnchor):
        evidence = unique_current_anchor(screen, anchor)
        if not evidence.matched or evidence.device_box is None:
            raise SafetyError(f"Entry anchor {anchor.id!r} is missing or ambiguous.")
        if evidence.score < max(0.9, evidence.threshold):
            raise SafetyError(f"Entry anchor {anchor.id!r} confidence is insufficient.")
        return evidence

    @staticmethod
    def _destination(screen: CapturedScreen, anchor: VisualAnchor):
        evidence = GuardedEntryNavigator._match(screen, anchor)
        # The destination anchor's declared state is the minimum semantic
        # identity. It is not enough to match a similarly shaped Home control.
        if anchor.state == ScreenState.UNKNOWN:
            raise SafetyError("Destination anchor has no known state.")
        return evidence

    def _home(self, result: NavigationResult, tag: str) -> EntryFrame:
        frame = self.port.observe(tag)
        identity = (frame.target.index, frame.target.name, frame.target.serial, frame.target.boot_id)
        if self._identity is None:
            self._identity = identity
        elif identity != self._identity:
            raise SafetyError("Entry frame target identity changed.")
        result.captures.append(frame.capture_id)
        detection = self.home_detector(frame.screen)
        if detection.state != ScreenState.GAME_HOME or detection.confidence < 0.9:
            raise SafetyError("Current frame is not a verified GAME_HOME screen.")
        return frame

    def _step(
        self,
        result: NavigationResult,
        frame: EntryFrame,
        action_anchor: VisualAnchor,
        destination_anchor: VisualAnchor,
        action_name: str,
        destination_name: str,
        cancelled: Callable[[], bool],
    ) -> EntryFrame:
        evidence = self._match(frame.screen, action_anchor)
        if cancelled():
            raise _Cancelled("Entry navigation cancelled before dispatch.")
        try:
            self.port.tap(frame, evidence.device_box.center)
        except SafetyError:
            raise
        except (OSError, RuntimeError) as exc:
            raise _ActionUncertain(str(exc)) from exc
        result.actions.append(action_name)
        return self._observe_destination(
            result,
            destination_anchor,
            destination_name,
            cancelled,
        )

    def _observe_destination(
        self,
        result: NavigationResult,
        destination_anchor: VisualAnchor,
        destination_name: str,
        cancelled: Callable[[], bool],
    ) -> EntryFrame:
        """Wait for a delayed destination using fresh frames only.

        A destination transition can take more than one capture.  Polling is
        deliberately bounded and never dispatches another input.  Transport
        identity is checked on every frame so a boot/serial change fails
        immediately instead of waiting on an unrelated target.
        """
        last_error: SafetyError | None = None
        for attempt in range(self.destination_observations):
            if cancelled():
                raise _Cancelled("Entry navigation cancelled while observing destination.")
            if attempt:
                if self.destination_wait_seconds:
                    self.sleep(self.destination_wait_seconds)
                if cancelled():
                    raise _Cancelled("Entry navigation cancelled while waiting for destination.")
            try:
                after = self.port.observe(destination_name)
            except StopIteration:
                break
            identity = (after.target.index, after.target.name, after.target.serial, after.target.boot_id)
            if identity != self._identity:
                raise SafetyError("Entry destination target identity changed.")
            result.captures.append(after.capture_id)
            try:
                self._destination(after.screen, destination_anchor)
            except SafetyError as exc:
                last_error = exc
                continue
            return after
        detail = str(last_error) if last_error else "no fresh destination frame was available"
        raise SafetyError(
            f"Entry destination remained unverified after "
            f"{self.destination_observations} bounded observations: {detail}"
        )

    def run(self, cancelled: Callable[[], bool] = lambda: False) -> NavigationResult:
        result = NavigationResult(NavigationStatus.BLOCKED)
        try:
            if cancelled():
                raise _Cancelled("Entry navigation cancelled before capture.")
            frame = self._home(result, f"{self.profile.task}-home-before")
            frame = self._step(
                result,
                frame,
                self.profile.first_anchor,
                self.profile.first_destination,
                f"tap:{self.profile.first_anchor.id}",
                f"{self.profile.task}-after-step-1",
                cancelled,
            )
            if self.profile.second_anchor is not None and self.profile.second_destination is not None:
                frame = self._step(
                    result,
                    frame,
                    self.profile.second_anchor,
                    self.profile.second_destination,
                    f"tap:{self.profile.second_anchor.id}",
                    f"{self.profile.task}-after-step-2",
                    cancelled,
                )
            result.status = NavigationStatus.SUCCESS
            return result
        except _Cancelled as exc:
            result.status = NavigationStatus.CANCELLED
            result.error = str(exc)
            return result
        except _ActionUncertain as exc:
            result.status = NavigationStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
            return result
        except OSError as exc:
            result.status = NavigationStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
            return result
        except (SafetyError, RuntimeError, ValueError) as exc:
            result.status = NavigationStatus.DESTINATION_UNVERIFIED if result.actions else NavigationStatus.BLOCKED
            result.error = str(exc)
            return result


def vip_entry_profile(home_vip_entry: VisualAnchor, vip_page: VisualAnchor) -> EntryProfile:
    return EntryProfile("vip-reward", home_vip_entry, vip_page)


def recruit_entry_profile(
    home_tavern: VisualAnchor,
    tavern_selected_name: VisualAnchor,
    tavern_recruit_entry: VisualAnchor,
    recruit_page: VisualAnchor,
) -> EntryProfile:
    # The selected-name anchor is the first destination; it is independently
    # matched before the Recruit action can be considered.
    return EntryProfile(
        "free-recruit",
        home_tavern,
        tavern_selected_name,
        tavern_recruit_entry,
        recruit_page,
    )

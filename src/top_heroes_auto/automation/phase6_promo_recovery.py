"""Bounded, navigation-only recovery for the known Stranger Things popup.

The popup is a Phase 6 shop-survey concern only.  This module deliberately
does not belong to the normal Home recovery engine: it can send at most one
observed-target Back keyevent, never retries an uncertain dispatch, and never
claims, purchases, scrolls, or writes a reward journal row.
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


class PromoRecoveryStatus(StrEnum):
    """Outcome of the optional known-popup recovery attempt."""

    NOT_PRESENT = "NOT_PRESENT"
    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    ACTION_RESULT_UNCERTAIN = "ACTION_RESULT_UNCERTAIN"
    DESTINATION_UNVERIFIED = "DESTINATION_UNVERIFIED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class PromoRecoveryFrame:
    target: Target
    screen: CapturedScreen

    @property
    def capture_id(self) -> str:
        if self.screen.source_image:
            return str(self.screen.source_image)
        digest = hashlib.sha256(self.screen.normalized.tobytes()).hexdigest()
        return f"frame:{self.screen.timestamp}:{digest}"


class PromoRecoveryPort(Protocol):
    def observe(self, tag: str) -> PromoRecoveryFrame: ...

    def back(self, frame: PromoRecoveryFrame) -> None: ...


@dataclass
class PromoRecoveryResult:
    status: PromoRecoveryStatus = PromoRecoveryStatus.BLOCKED
    attempted: bool = False
    actions: list[str] = field(default_factory=list)
    captures: list[str] = field(default_factory=list)
    before: dict | None = None
    after: dict | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "result": self.status.value,
            "attempted": self.attempted,
            "actions": list(self.actions),
            "captures": list(self.captures),
            "before": self.before,
            "after": self.after,
            "error": self.error,
            "claims": [],
            "journal_rows": 0,
        }


class _Cancelled(RuntimeError):
    pass


class _IdentityMismatch(SafetyError):
    pass


class _ActionUncertain(RuntimeError):
    pass


class _DestinationTimeout(RuntimeError):
    pass


class GuardedPromoRecovery:
    """Recover one verified account from the known popup without retries."""

    MAX_DESTINATION_OBSERVATIONS = 3
    DEFAULT_WAIT_SECONDS = 0.25
    BACK_KEYCODE = 4

    def __init__(
        self,
        port: PromoRecoveryPort,
        promo_anchor: VisualAnchor,
        home_detector: Callable[[CapturedScreen], ScreenDetection],
        *,
        destination_observations: int = MAX_DESTINATION_OBSERVATIONS,
        destination_wait_seconds: float = DEFAULT_WAIT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if promo_anchor.state != ScreenState.POPUP_GENERIC:
            raise ValueError("Known promo recovery requires a POPUP_GENERIC anchor.")
        if not 1 <= destination_observations <= self.MAX_DESTINATION_OBSERVATIONS:
            raise ValueError("Promo recovery allows one to three destination observations.")
        if destination_wait_seconds < 0:
            raise ValueError("Destination wait cannot be negative.")
        self.port = port
        self.promo_anchor = promo_anchor
        self.home_detector = home_detector
        self.destination_observations = destination_observations
        self.destination_wait_seconds = destination_wait_seconds
        self.sleep = sleep
        self._expected_identity: tuple[int, str, str, str] | None = None
        self._expected_transport: tuple[str, str] | None = None
        self._seen_captures: set[str] = set()

    @staticmethod
    def _identity(frame: PromoRecoveryFrame) -> tuple[int, str, str, str]:
        target = frame.target
        screen = frame.screen
        captured = (target.index, target.name, target.serial, target.boot_id)
        rendered = (screen.index, screen.name, screen.serial, screen.boot_id)
        if captured != rendered or not all(captured):
            raise _IdentityMismatch("Promo recovery frame identity is missing or inconsistent.")
        return captured

    def _observe(
        self,
        result: PromoRecoveryResult,
        tag: str,
        expected: tuple[int, str],
    ) -> PromoRecoveryFrame:
        frame = self.port.observe(tag)
        identity = self._identity(frame)
        if identity[:2] != expected:
            raise _IdentityMismatch("Promo recovery account identity changed.")
        if self._expected_identity is None:
            if self._expected_transport and identity[2:] != self._expected_transport:
                raise _IdentityMismatch("Promo recovery transport differs from the last verified frame.")
            self._expected_identity = identity
        elif identity != self._expected_identity:
            raise _IdentityMismatch("Promo recovery serial or boot identity changed.")
        if frame.capture_id in self._seen_captures:
            raise SafetyError("Promo recovery requires a fresh screenshot for every observation.")
        self._seen_captures.add(frame.capture_id)
        result.captures.append(frame.capture_id)
        return frame

    @staticmethod
    def _frame_dict(frame: PromoRecoveryFrame) -> dict:
        target = frame.target
        return {
            "capture": frame.capture_id,
            "instance": {"index": target.index, "name": target.name},
            "adb_target": target.serial,
            "boot_id": target.boot_id,
            "timestamp": frame.screen.timestamp,
        }

    def _match_popup(self, frame: PromoRecoveryFrame):
        evidence = unique_current_anchor(frame.screen, self.promo_anchor)
        return evidence

    def _dispatch_back(
        self,
        result: PromoRecoveryResult,
        frame: PromoRecoveryFrame,
        cancelled: Callable[[], bool],
    ) -> None:
        if cancelled():
            raise _Cancelled("Promo recovery cancelled before Back dispatch.")
        # Set this before entering the transport boundary.  Any exception is
        # therefore terminal for this run; callers must never retry the Back.
        result.attempted = True
        try:
            self.port.back(frame)
        except (SafetyError, _IdentityMismatch):
            raise
        except (OSError, RuntimeError) as exc:
            raise _ActionUncertain(str(exc)) from exc
        result.actions.append("keyevent:4")

    def _home_after_back(
        self,
        result: PromoRecoveryResult,
        expected: tuple[int, str],
        cancelled: Callable[[], bool],
    ) -> PromoRecoveryFrame:
        last_error: str | None = None
        for attempt in range(self.destination_observations):
            if cancelled():
                raise _Cancelled("Promo recovery cancelled while observing Home.")
            if attempt:
                if self.destination_wait_seconds:
                    self.sleep(self.destination_wait_seconds)
                if cancelled():
                    raise _Cancelled("Promo recovery cancelled while waiting for Home.")
            try:
                frame = self._observe(result, "phase6-promo-home-after", expected)
            except StopIteration as exc:
                if last_error:
                    raise SafetyError(last_error) from exc
                raise _DestinationTimeout("No fresh Home frame was available after Back.") from exc
            detection = self.home_detector(frame.screen)
            result.after = {
                **self._frame_dict(frame),
                "detection": detection.as_dict(),
            }
            if detection.state == ScreenState.GAME_HOME and detection.confidence >= 0.9:
                return frame
            # A popup/unknown frame is not a loading transition that may be
            # safely guessed through.  Stop immediately, without another input.
            if detection.state in {ScreenState.UNKNOWN, ScreenState.POPUP_GENERIC}:
                raise SafetyError(
                    f"Back destination remained {detection.state.value}; no retry is safe."
                )
            last_error = (
                f"GAME_HOME not verified: {detection.state.value} "
                f"confidence={detection.confidence:.3f}"
            )
        raise SafetyError(last_error or "GAME_HOME did not become verified after Back.")

    def run(
        self,
        index: int,
        name: str,
        cancelled: Callable[[], bool] = lambda: False,
        *,
        expected_transport: tuple[str, str] | None = None,
    ) -> PromoRecoveryResult:
        result = PromoRecoveryResult()
        expected = index, name
        self._expected_transport = expected_transport
        try:
            if cancelled():
                raise _Cancelled("Promo recovery cancelled before capture.")
            frame = self._observe(result, "phase6-promo-before", expected)
            evidence = self._match_popup(frame)
            result.before = {
                **self._frame_dict(frame),
                "anchor": evidence.as_dict(),
            }
            if not evidence.matched or evidence.device_box is None:
                if evidence.score >= max(0.9, self.promo_anchor.threshold):
                    raise SafetyError("Known promo anchor is ambiguous in the current frame.")
                result.status = PromoRecoveryStatus.NOT_PRESENT
                return result
            self._dispatch_back(result, frame, cancelled)
            self._home_after_back(result, expected, cancelled)
            result.status = PromoRecoveryStatus.SUCCESS
            return result
        except _Cancelled as exc:
            result.status = PromoRecoveryStatus.CANCELLED
            result.error = str(exc)
        except _ActionUncertain as exc:
            result.status = PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
        except _DestinationTimeout as exc:
            result.status = PromoRecoveryStatus.TIMEOUT
            result.error = str(exc)
        except _IdentityMismatch as exc:
            result.status = PromoRecoveryStatus.IDENTITY_MISMATCH
            result.error = str(exc)
        except OSError as exc:
            result.status = PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
        except (SafetyError, RuntimeError, ValueError) as exc:
            result.status = (
                PromoRecoveryStatus.DESTINATION_UNVERIFIED
                if result.attempted
                else PromoRecoveryStatus.BLOCKED
            )
            result.error = str(exc)
        return result


class ManagerPromoRecoveryPort(PromoRecoveryPort):
    """Manager bridge for the one evidence-bound Back keyevent."""

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

    def observe(self, tag: str) -> PromoRecoveryFrame:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        if (target.index, target.name) != (self.index, self.name):
            raise SafetyError("Promo recovery capture identity changed.")
        if self._target and (target.serial, target.boot_id) != (
            self._target.serial,
            self._target.boot_id,
        ):
            raise SafetyError("Promo recovery transport identity changed.")
        self._target = target
        captured = ScreenshotService(
            lambda serial: payload if serial == target.serial else b""
        ).take(target, self.folder, tag)
        return PromoRecoveryFrame(target, captured)

    def back(self, frame: PromoRecoveryFrame) -> None:
        if self._target != frame.target:
            raise SafetyError("Promo recovery action target is stale or changed.")
        self.manager.execute(
            self.index,
            "keyevent",
            values=(GuardedPromoRecovery.BACK_KEYCODE,),
            snapshot=self.snapshot,
            observed_target=frame.target,
        )
        self._target = None

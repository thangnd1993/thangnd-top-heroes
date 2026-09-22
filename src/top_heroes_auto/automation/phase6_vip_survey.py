"""Bounded, observation-only VIP page survey primitives.

This module intentionally has no reward profile, claim, explorer, or journal
dependency.  It records current-frame VIP evidence and permits only the
already-qualified Home-to-VIP entry and VIP-to-Home exit actions.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable, Mapping, Protocol

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import (
    AnchorEvidence,
    CapturedScreen,
    ScreenDetection,
    ScreenState,
    VisualAnchor,
)
from top_heroes_auto.vision.screenshot import ScreenshotService


class VipSurveyStatus(StrEnum):
    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    DESTINATION_UNVERIFIED = "DESTINATION_UNVERIFIED"
    ACTION_RESULT_UNCERTAIN = "ACTION_RESULT_UNCERTAIN"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    TIMEOUT = "TIMEOUT"


class _SurveyCancelled(RuntimeError):
    pass


class _SurveyTimeout(RuntimeError):
    pass


class _ActionUncertain(RuntimeError):
    pass


class _IdentityChanged(RuntimeError):
    pass


@dataclass(frozen=True)
class VipSurveyFrame:
    target: Target
    screen: CapturedScreen

    @property
    def capture_id(self) -> str:
        if self.screen.source_image:
            return str(self.screen.source_image)
        digest = hashlib.sha256(self.screen.normalized.tobytes()).hexdigest()
        return f"frame:{self.screen.timestamp}:{digest}"


class VipSurveyPort(Protocol):
    def observe(self, tag: str) -> VipSurveyFrame: ...

    def tap(self, frame: VipSurveyFrame, point: tuple[int, int]) -> None: ...


class ManagerVipSurveyPort:
    """Capture and dispatch only through the exact observed Manager target."""

    def __init__(
        self,
        manager: Manager,
        snapshot: RunSnapshot,
        index: int,
        name: str,
        expected_identity: tuple[str, str],
        folder: Path | None = None,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.expected_identity = expected_identity
        self.folder = folder
        self._target: Target | None = None

    def observe(self, tag: str) -> VipSurveyFrame:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        if (target.index, target.name) != (self.index, self.name):
            raise SafetyError("VIP survey capture identity changed.")
        if (target.serial, target.boot_id) != self.expected_identity:
            raise _IdentityChanged("VIP survey serial/boot identity changed.")
        if self._target is not None and (target.serial, target.boot_id) != (
            self._target.serial,
            self._target.boot_id,
        ):
            raise _IdentityChanged("VIP survey transport identity changed.")
        self._target = target
        captured = ScreenshotService(
            lambda serial: payload if serial == target.serial else b""
        ).take(target, self.folder, tag)
        return VipSurveyFrame(target, captured)

    def tap(self, frame: VipSurveyFrame, point: tuple[int, int]) -> None:
        if self._target != frame.target:
            raise SafetyError("VIP survey action target is stale or changed.")
        self.manager.execute(
            self.index,
            "tap",
            values=point,
            snapshot=self.snapshot,
            observed_target=frame.target,
        )
        self._target = None


@dataclass
class VipSurveyResult:
    status: VipSurveyStatus = VipSurveyStatus.BLOCKED
    captures: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    diagnostics: dict[str, dict] = field(default_factory=dict)
    serial: str | None = None
    boot_id: str | None = None
    error: str | None = None
    receipt_available: bool = False
    claim_readiness: str = "NOT_IMPLEMENTED"
    claims: list[str] = field(default_factory=list)
    journal_rows: int = 0

    def as_dict(self) -> dict:
        return {
            "result": self.status.value,
            "captures": list(self.captures),
            "actions": list(self.actions),
            "diagnostics": dict(self.diagnostics),
            "serial": self.serial,
            "boot_id": self.boot_id,
            "error": self.error,
            "receipt_available": self.receipt_available,
            "claim_readiness": self.claim_readiness,
            "claims": list(self.claims),
            "journal_rows": self.journal_rows,
        }


class GuardedVipSurvey:
    """Run one Home → VIP observation → Home route with no reward input."""

    REQUIRED_ANCHORS = ("home_entry", "page", "exit", "home")

    def __init__(
        self,
        port: VipSurveyPort,
        anchors: Mapping[str, VisualAnchor],
        home_detector: Callable[[CapturedScreen], ScreenDetection],
        expected_identity: tuple[str, str],
        *,
        max_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        missing = [role for role in self.REQUIRED_ANCHORS if role not in anchors]
        if missing:
            raise ValueError(f"VIP survey anchors missing: {', '.join(missing)}")
        if max_seconds <= 0:
            raise ValueError("VIP survey deadline must be positive.")
        self.port = port
        self.anchors = dict(anchors)
        self.home_detector = home_detector
        self.expected_identity = expected_identity
        self.max_seconds = max_seconds
        self.clock = clock
        self._started = 0.0
        self._stage = "home"

    @staticmethod
    def _target_dict(frame: VipSurveyFrame) -> dict:
        return {
            "index": frame.target.index,
            "name": frame.target.name,
            "serial": frame.target.serial,
            "boot_id": frame.target.boot_id,
        }

    def _check_limits(self, cancelled: Callable[[], bool]) -> None:
        if cancelled():
            raise _SurveyCancelled("VIP survey cancelled before the next observation or action.")
        if self.clock() - self._started >= self.max_seconds:
            raise _SurveyTimeout("VIP survey exceeded its bounded deadline.")

    def _observe(
        self,
        result: VipSurveyResult,
        tag: str,
        cancelled: Callable[[], bool],
    ) -> VipSurveyFrame:
        self._check_limits(cancelled)
        frame = self.port.observe(tag)
        if (frame.target.index, frame.target.name) != (2, "5-Emmmmm"):
            raise _IdentityChanged("VIP survey target identity changed.")
        if (frame.target.serial, frame.target.boot_id) != self.expected_identity:
            raise _IdentityChanged("VIP survey serial/boot identity changed.")
        result.serial = frame.target.serial
        result.boot_id = frame.target.boot_id
        result.captures.append(frame.capture_id)
        result.diagnostics[frame.capture_id] = {
            "tag": tag,
            "capture": frame.capture_id,
            "target": self._target_dict(frame),
        }
        return frame

    def _match(self, result: VipSurveyResult, frame: VipSurveyFrame, role: str) -> AnchorEvidence:
        evidence = unique_current_anchor(frame.screen, self.anchors[role])
        result.diagnostics.setdefault(frame.capture_id, {}).setdefault("anchors", {})[
            role
        ] = evidence.as_dict()
        if not evidence.matched or evidence.device_box is None:
            raise SafetyError(f"VIP survey anchor {self.anchors[role].id!r} is missing or ambiguous.")
        if evidence.score < max(0.9, evidence.threshold):
            raise SafetyError(f"VIP survey anchor {self.anchors[role].id!r} confidence is insufficient.")
        return evidence

    def _diagnose(self, result: VipSurveyResult, frame: VipSurveyFrame, role: str) -> AnchorEvidence:
        """Record optional page evidence without turning it into an action gate."""
        anchor = self.anchors.get(role)
        if anchor is None:
            result.diagnostics.setdefault(frame.capture_id, {}).setdefault("anchors", {})[
                role
            ] = {
                "anchor": None,
                "required": False,
                "available": False,
                "proven": False,
            }
            return AnchorEvidence(role, ScreenState.FREE_REWARD_PAGE, 0.0, 1.0, False)
        evidence = unique_current_anchor(frame.screen, anchor)
        result.diagnostics.setdefault(frame.capture_id, {}).setdefault("anchors", {})[
            role
        ] = {
            **evidence.as_dict(),
            "required": False,
            "proven": bool(
                evidence.matched
                and evidence.device_box is not None
                and evidence.score >= max(0.9, evidence.threshold)
            ),
        }
        return evidence

    def _home(self, result: VipSurveyResult, frame: VipSurveyFrame) -> None:
        detection = self.home_detector(frame.screen)
        result.diagnostics[frame.capture_id]["screen"] = detection.as_dict()
        if detection.state != ScreenState.GAME_HOME or detection.confidence < 0.9:
            raise SafetyError("VIP survey frame is not a verified GAME_HOME screen.")

    def _tap(
        self,
        result: VipSurveyResult,
        frame: VipSurveyFrame,
        evidence: AnchorEvidence,
        label: str,
        cancelled: Callable[[], bool],
    ) -> None:
        self._check_limits(cancelled)
        result.actions.append(label)
        try:
            self.port.tap(frame, evidence.device_box.center)
        except SafetyError:
            raise
        except (OSError, RuntimeError) as exc:
            raise _ActionUncertain(str(exc)) from exc

    def run(self, cancelled: Callable[[], bool] = lambda: False) -> VipSurveyResult:
        result = VipSurveyResult()
        self._started = self.clock()
        try:
            home_before = self._observe(result, "home-before", cancelled)
            self._home(result, home_before)
            entry = self._match(result, home_before, "home_entry")
            self._tap(result, home_before, entry, "tap:home-vip-entry", cancelled)

            self._stage = "vip"
            vip_frame = self._observe(result, "vip-after-entry", cancelled)
            self._match(result, vip_frame, "page")
            for role in ("free", "available", "claim"):
                self._diagnose(result, vip_frame, role)
            paid = self.anchors.get("paid")
            if paid is not None:
                self._diagnose(result, vip_frame, "paid")

            self._stage = "vip-exit"
            exit_evidence = self._match(result, vip_frame, "exit")
            self._tap(result, vip_frame, exit_evidence, "tap:vip-exit", cancelled)

            self._stage = "home-after"
            home_after = self._observe(result, "home-after-exit", cancelled)
            self._home(result, home_after)
            self._match(result, home_after, "home")
            result.status = VipSurveyStatus.SUCCESS
            return result
        except _SurveyCancelled as exc:
            result.status = VipSurveyStatus.CANCELLED
            result.error = str(exc)
        except _SurveyTimeout as exc:
            result.status = VipSurveyStatus.TIMEOUT
            result.error = str(exc)
        except _ActionUncertain as exc:
            result.status = VipSurveyStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
        except _IdentityChanged as exc:
            result.status = VipSurveyStatus.IDENTITY_MISMATCH
            result.error = str(exc)
        except OSError as exc:
            result.status = VipSurveyStatus.BLOCKED
            result.error = str(exc)
        except (SafetyError, RuntimeError, ValueError) as exc:
            result.status = (
                VipSurveyStatus.DESTINATION_UNVERIFIED
                if result.actions and self._stage != "home"
                else VipSurveyStatus.BLOCKED
            )
            result.error = str(exc)
        return result

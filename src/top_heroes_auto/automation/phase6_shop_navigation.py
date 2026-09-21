"""Guarded, observation-only navigation for the Phase 6 daily-offer page.

This route is deliberately separate from :mod:`free_rewards` and the shop
claim adapter.  It can open the surveyed daily-offer page, inspect the generic
help popup, close it, and return Home; it has no claim, purchase, scroll, or
journal API.  Every input point comes from a unique match in the fresh frame
immediately preceding that input.
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


class ShopNavigationStatus(StrEnum):
    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    DESTINATION_UNVERIFIED = "DESTINATION_UNVERIFIED"
    ACTION_RESULT_UNCERTAIN = "ACTION_RESULT_UNCERTAIN"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class ShopNavigationFrame:
    target: Target
    screen: CapturedScreen

    @property
    def capture_id(self) -> str:
        if self.screen.source_image:
            return str(self.screen.source_image)
        digest = hashlib.sha256(self.screen.normalized.tobytes()).hexdigest()
        return f"frame:{self.screen.timestamp}:{digest}"


class ShopNavigationPort(Protocol):
    def observe(self, tag: str) -> ShopNavigationFrame: ...

    def tap(self, frame: ShopNavigationFrame, point: tuple[int, int]) -> None: ...


@dataclass(frozen=True)
class ShopNavigationProfile:
    """The exact four-action, navigation-only daily-offer route."""

    home_shop_entry: VisualAnchor
    daily_page: VisualAnchor
    info_button: VisualAnchor
    info_popup: VisualAnchor
    info_close: VisualAnchor
    daily_exit: VisualAnchor

    def __post_init__(self):
        anchors = (
            self.home_shop_entry,
            self.daily_page,
            self.info_button,
            self.info_popup,
            self.info_close,
            self.daily_exit,
        )
        ids = [anchor.id for anchor in anchors]
        if len(ids) != len(set(ids)):
            raise ValueError("Shop navigation anchors must have unique IDs.")
        if self.home_shop_entry.state != ScreenState.GAME_HOME:
            raise ValueError("Home shop entry must be a GAME_HOME anchor.")
        if self.daily_page.state != ScreenState.FREE_REWARD_PAGE:
            raise ValueError("Daily page must be a FREE_REWARD_PAGE anchor.")
        if self.info_button.state != ScreenState.FREE_REWARD_PAGE:
            raise ValueError("Daily information button must be a FREE_REWARD_PAGE anchor.")
        if self.info_popup.state != ScreenState.POPUP_GENERIC:
            raise ValueError("Information popup must be a POPUP_GENERIC anchor.")
        if self.info_close.state != ScreenState.POPUP_GENERIC:
            raise ValueError("Information close control must be a POPUP_GENERIC anchor.")
        if self.daily_exit.state != ScreenState.FREE_REWARD_PAGE:
            raise ValueError("Daily exit must be a FREE_REWARD_PAGE anchor.")


@dataclass
class ShopNavigationResult:
    status: ShopNavigationStatus = ShopNavigationStatus.BLOCKED
    actions: list[str] = field(default_factory=list)
    captures: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "result": self.status.value,
            "actions": list(self.actions),
            "captures": list(self.captures),
            "error": self.error,
            "claims": [],
            "journal_rows": 0,
        }


class _Cancelled(RuntimeError):
    pass


class _ActionUncertain(RuntimeError):
    pass


class _IdentityMismatch(SafetyError):
    pass


class _DestinationTimeout(RuntimeError):
    pass


class GuardedShopNavigation:
    """Execute one bounded route using only fresh, identity-bound frames."""

    MAX_ACTIONS = 4
    MAX_DESTINATION_OBSERVATIONS = 3
    DEFAULT_WAIT_SECONDS = 0.25

    def __init__(
        self,
        port: ShopNavigationPort,
        profile: ShopNavigationProfile,
        home_detector: Callable[[CapturedScreen], ScreenDetection],
        *,
        destination_observations: int = MAX_DESTINATION_OBSERVATIONS,
        destination_wait_seconds: float = DEFAULT_WAIT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not 1 <= destination_observations <= self.MAX_DESTINATION_OBSERVATIONS:
            raise ValueError("Shop navigation allows one to three destination observations.")
        if destination_wait_seconds < 0:
            raise ValueError("Destination wait cannot be negative.")
        self.port = port
        self.profile = profile
        self.home_detector = home_detector
        self.destination_observations = destination_observations
        self.destination_wait_seconds = destination_wait_seconds
        self.sleep = sleep
        self._expected_identity: tuple[int, str, str, str] | None = None
        self._seen_captures: set[str] = set()

    @staticmethod
    def _match(screen: CapturedScreen, anchor: VisualAnchor):
        evidence = unique_current_anchor(screen, anchor)
        if not evidence.matched or evidence.device_box is None:
            raise SafetyError(f"Shop navigation anchor {anchor.id!r} is missing or ambiguous.")
        if evidence.score < max(0.9, evidence.threshold):
            raise SafetyError(f"Shop navigation anchor {anchor.id!r} confidence is insufficient.")
        return evidence

    @staticmethod
    def _identity(frame: ShopNavigationFrame) -> tuple[int, str, str, str]:
        target = frame.target
        screen = frame.screen
        captured = (target.index, target.name, target.serial, target.boot_id)
        rendered = (screen.index, screen.name, screen.serial, screen.boot_id)
        if captured != rendered or not all(captured):
            raise _IdentityMismatch("Shop navigation frame identity is missing or inconsistent.")
        return captured

    def _observe(
        self,
        result: ShopNavigationResult,
        tag: str,
        expected: tuple[int, str],
    ) -> ShopNavigationFrame:
        frame = self.port.observe(tag)
        identity = self._identity(frame)
        if identity[:2] != expected:
            raise _IdentityMismatch("Shop navigation account identity changed.")
        if self._expected_identity is None:
            self._expected_identity = identity
        elif identity != self._expected_identity:
            raise _IdentityMismatch("Shop navigation serial or boot identity changed.")
        if frame.capture_id in self._seen_captures:
            raise SafetyError("Shop navigation requires a fresh screenshot for every observation.")
        self._seen_captures.add(frame.capture_id)
        result.captures.append(frame.capture_id)
        return frame

    def _verify_home(self, frame: ShopNavigationFrame) -> None:
        detection = self.home_detector(frame.screen)
        if detection.state != ScreenState.GAME_HOME or detection.confidence < 0.9:
            raise SafetyError("Current frame is not a verified GAME_HOME screen.")

    @staticmethod
    def _verify_source(frame: ShopNavigationFrame, anchor: VisualAnchor) -> None:
        GuardedShopNavigation._match(frame.screen, anchor)

    def _dispatch(
        self,
        result: ShopNavigationResult,
        frame: ShopNavigationFrame,
        anchor: VisualAnchor,
        action_name: str,
        cancelled: Callable[[], bool],
    ) -> None:
        evidence = self._match(frame.screen, anchor)
        if cancelled():
            raise _Cancelled("Shop navigation cancelled before dispatch.")
        try:
            self.port.tap(frame, evidence.device_box.center)
        except (SafetyError, _IdentityMismatch):
            raise
        except (OSError, RuntimeError) as exc:
            raise _ActionUncertain(str(exc)) from exc
        result.actions.append(action_name)

    def _destination_anchor(
        self,
        result: ShopNavigationResult,
        expected: tuple[int, str],
        anchor: VisualAnchor,
        tag: str,
        cancelled: Callable[[], bool],
    ) -> ShopNavigationFrame:
        last_error: SafetyError | None = None
        for attempt in range(self.destination_observations):
            if cancelled():
                raise _Cancelled("Shop navigation cancelled while observing destination.")
            if attempt:
                if self.destination_wait_seconds:
                    self.sleep(self.destination_wait_seconds)
                if cancelled():
                    raise _Cancelled("Shop navigation cancelled while waiting for destination.")
            try:
                frame = self._observe(result, tag, expected)
            except StopIteration as exc:
                if last_error is not None:
                    raise SafetyError(str(last_error)) from exc
                raise _DestinationTimeout("No fresh destination frame was available.") from exc
            try:
                self._match(frame.screen, anchor)
            except SafetyError as exc:
                last_error = exc
                continue
            return frame
        detail = str(last_error) if last_error else "destination anchor did not match"
        raise SafetyError(
            f"Destination {anchor.id!r} remained unverified after "
            f"{self.destination_observations} bounded observations: {detail}"
        )

    def _home_destination(
        self,
        result: ShopNavigationResult,
        expected: tuple[int, str],
        tag: str,
        cancelled: Callable[[], bool],
    ) -> ShopNavigationFrame:
        last_error: SafetyError | None = None
        for attempt in range(self.destination_observations):
            if cancelled():
                raise _Cancelled("Shop navigation cancelled while observing Home.")
            if attempt:
                if self.destination_wait_seconds:
                    self.sleep(self.destination_wait_seconds)
                if cancelled():
                    raise _Cancelled("Shop navigation cancelled while waiting for Home.")
            try:
                frame = self._observe(result, tag, expected)
            except StopIteration as exc:
                if last_error is not None:
                    raise SafetyError(str(last_error)) from exc
                raise _DestinationTimeout("No fresh Home frame was available.") from exc
            try:
                self._verify_home(frame)
            except SafetyError as exc:
                last_error = exc
                continue
            return frame
        detail = str(last_error) if last_error else "GAME_HOME detector did not match"
        raise SafetyError(
            f"Home remained unverified after {self.destination_observations} "
            f"bounded observations: {detail}"
        )

    def run(
        self,
        index: int,
        name: str,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> ShopNavigationResult:
        result = ShopNavigationResult()
        expected = index, name
        try:
            if cancelled():
                raise _Cancelled("Shop navigation cancelled before capture.")
            try:
                frame = self._observe(result, "phase6-shop-home-before", expected)
            except StopIteration as exc:
                raise _DestinationTimeout("No fresh Home frame was available.") from exc
            self._verify_home(frame)
            self._dispatch(
                result,
                frame,
                self.profile.home_shop_entry,
                "tap:home-shop-entry",
                cancelled,
            )
            frame = self._destination_anchor(
                result,
                expected,
                self.profile.daily_page,
                "phase6-shop-daily-after-entry",
                cancelled,
            )

            self._verify_source(frame, self.profile.daily_page)
            self._dispatch(
                result,
                frame,
                self.profile.info_button,
                "tap:phase6-daily-info-button",
                cancelled,
            )
            frame = self._destination_anchor(
                result,
                expected,
                self.profile.info_popup,
                "phase6-shop-info-popup",
                cancelled,
            )

            self._verify_source(frame, self.profile.info_popup)
            self._dispatch(
                result,
                frame,
                self.profile.info_close,
                "tap:phase6-daily-info-close",
                cancelled,
            )
            frame = self._destination_anchor(
                result,
                expected,
                self.profile.daily_page,
                "phase6-shop-daily-after-close",
                cancelled,
            )

            self._verify_source(frame, self.profile.daily_page)
            self._dispatch(
                result,
                frame,
                self.profile.daily_exit,
                "tap:phase6-daily-exit",
                cancelled,
            )
            self._home_destination(result, expected, "phase6-shop-home-after", cancelled)
            result.status = ShopNavigationStatus.SUCCESS
            return result
        except _Cancelled as exc:
            result.status = ShopNavigationStatus.CANCELLED
            result.error = str(exc)
        except _ActionUncertain as exc:
            result.status = ShopNavigationStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
        except _DestinationTimeout as exc:
            result.status = ShopNavigationStatus.TIMEOUT
            result.error = str(exc)
        except _IdentityMismatch as exc:
            result.status = ShopNavigationStatus.IDENTITY_MISMATCH
            result.error = str(exc)
        except OSError as exc:
            result.status = ShopNavigationStatus.ACTION_RESULT_UNCERTAIN
            result.error = str(exc)
        except (SafetyError, RuntimeError, ValueError) as exc:
            result.status = (
                ShopNavigationStatus.DESTINATION_UNVERIFIED
                if result.actions
                else ShopNavigationStatus.BLOCKED
            )
            result.error = str(exc)
        return result


class ManagerShopNavigationPort(ShopNavigationPort):
    """Manager bridge with no claim, reward, or journal operation."""

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

    def observe(self, tag: str) -> ShopNavigationFrame:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        if (target.index, target.name) != (self.index, self.name):
            raise SafetyError("Shop navigation capture identity changed.")
        if self._target and (target.serial, target.boot_id) != (
            self._target.serial,
            self._target.boot_id,
        ):
            raise SafetyError("Shop navigation transport identity changed.")
        self._target = target
        captured = ScreenshotService(
            lambda serial: payload if serial == target.serial else b""
        ).take(target, self.folder, tag)
        return ShopNavigationFrame(target, captured)

    def tap(self, frame: ShopNavigationFrame, point: tuple[int, int]) -> None:
        if self._target != frame.target:
            raise SafetyError("Shop navigation action target is stale or changed.")
        self.manager.execute(
            self.index,
            "tap",
            values=point,
            snapshot=self.snapshot,
            observed_target=frame.target,
        )
        self._target = None

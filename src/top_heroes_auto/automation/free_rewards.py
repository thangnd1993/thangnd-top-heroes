"""Free-only policy and bounded traversal shared by gameplay task adapters.

An adapter must recognize a known screen and its controls from each fresh capture.
Discovery (including red dots) never grants permission to claim. Unknown screens
stop traversal; absence of a recognized reward is not proof of unavailability.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Protocol

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import ScreenDetection, ScreenState


class Cost(StrEnum):
    FREE = "FREE"
    MONEY = "MONEY"
    DIAMONDS = "DIAMONDS"
    PREMIUM = "PREMIUM"
    TICKETS = "TICKETS"
    ITEMS = "ITEMS"
    SPEEDUPS = "SPEEDUPS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RewardEvidence:
    reward_id: str
    action_anchor: str
    free_anchor: str
    available_anchor: str
    cost: Cost = Cost.UNKNOWN
    ambiguous: bool = True
    diamond_reward: bool = False


@dataclass(frozen=True)
class Route:
    """Stable semantic edge; coordinates must come from this observation only."""

    id: str
    anchor: str
    destination: str
    kind: str = "tab"


@dataclass(frozen=True)
class RewardScreen:
    detection: ScreenDetection
    index: int
    name: str
    adb_target: str
    boot_id: str
    capture_id: str
    page: str
    fingerprint: str
    depth: int = 0
    rewards: tuple[RewardEvidence, ...] = ()
    routes: tuple[Route, ...] = ()
    scroll_axes: tuple[str, ...] = ()
    red_dot_candidates: tuple[str, ...] = ()
    # True only if adapter accounts for all content/tabs, including unsupported UI.
    coverage_known: bool = False


def verified_anchor(detection: ScreenDetection, anchor_id: str):
    if (detection.state == ScreenState.UNKNOWN or not math.isfinite(detection.confidence)
            or detection.confidence < 0.9):
        raise SafetyError("DO NOT TAP: unknown or low-confidence screen.")
    matches = [item for item in detection.evidence if item.anchor_id == anchor_id and item.matched]
    if len(matches) != 1:
        raise SafetyError("DO NOT TAP: target is missing or ambiguous.")
    item = matches[0]
    if (item.device_box is None or not math.isfinite(item.score) or not math.isfinite(item.threshold)
            or item.score < max(0.9, item.threshold)):
        raise SafetyError("DO NOT TAP: target evidence is insufficient.")
    return item


class FreeRewardGuard:
    """Bind one action to fresh evidence and consume permission before dispatch."""

    def __init__(self, index: int, name: str):
        self.identity = index, name
        self.transport: tuple[str, str] | None = None
        self.current: RewardScreen | None = None
        self.seen_captures: set[str] = set()
        self.claim_attempts: set[str] = set()

    def observe(self, screen: RewardScreen):
        self.current = None
        if (screen.index, screen.name) != self.identity:
            raise SafetyError("Account identity changed.")
        transport = screen.adb_target, screen.boot_id
        if not all(transport) or (self.transport is not None and transport != self.transport):
            raise SafetyError("Explicit ADB identity changed or is missing.")
        if not screen.capture_id or screen.capture_id in self.seen_captures:
            raise SafetyError("Stale screenshot cannot authorize another action.")
        self.transport = transport
        self.seen_captures.add(screen.capture_id)
        self.current = screen

    def consume(self, screen: RewardScreen, anchor: str):
        if self.current is not screen:
            raise SafetyError("A new account screenshot is required before every action.")
        evidence = verified_anchor(screen.detection, anchor)
        self.current = None
        return evidence.device_box.center

    def claim(self, screen: RewardScreen, reward: RewardEvidence):
        if reward not in screen.rewards or not reward.reward_id or reward.reward_id in self.claim_attempts:
            raise SafetyError("Reward is absent or already attempted; claim retry forbidden.")
        if sum(item.reward_id == reward.reward_id or item.action_anchor == reward.action_anchor
               for item in screen.rewards) != 1:
            raise SafetyError("DO NOT TAP: multiple rewards share this target identity.")
        if reward.cost != Cost.FREE or reward.ambiguous:
            raise SafetyError("DO NOT TAP: reward is paid, unavailable or ambiguous.")
        # A cooldown screen can retain its FREE label. Availability is separate.
        if len({reward.action_anchor, reward.free_anchor, reward.available_anchor}) != 3:
            raise SafetyError("Independent free and availability evidence is required.")
        verified_anchor(screen.detection, reward.free_anchor)
        verified_anchor(screen.detection, reward.available_anchor)
        point = self.consume(screen, reward.action_anchor)
        self.claim_attempts.add(reward.reward_id)
        return point


class ExplorerPort(Protocol):
    def observe(self) -> RewardScreen: ...

    def claim(self, screen: RewardScreen, reward: RewardEvidence, point: tuple[int, int]) -> None: ...

    def verify_claim(self, before: RewardScreen, after: RewardScreen, reward: RewardEvidence) -> bool: ...

    def navigate(self, screen: RewardScreen, route: Route, point: tuple[int, int]) -> None: ...

    def scroll(self, screen: RewardScreen, axis: str) -> None: ...

    def return_home(self, screen: RewardScreen) -> bool: ...


@dataclass(frozen=True)
class ExplorerLimits:
    max_steps: int = 60
    max_depth: int = 4
    max_scrolls: int = 6
    max_seconds: float = 120

    def __post_init__(self):
        if min(self.max_steps, self.max_depth, self.max_scrolls, self.max_seconds) <= 0:
            raise ValueError("Explorer limits must be positive.")


@dataclass
class ExplorerResult:
    status: str = "UNKNOWN_SCREEN"
    claimed: list[str] = field(default_factory=list)
    attempted: list[str] = field(default_factory=list)
    visited: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    coverage_complete: bool = False
    recovery_succeeded: bool = False
    error: str | None = None


class FreeRewardExplorer:
    """Traverse only adapter-recognized edges; no generic clicks on red dots.

    Adapters expose all currently known routes (including safe parent edges) and
    stable page identities. Each edge is followed at most once per page. Scrolling
    ends on repeated content; hitting a bound yields PARTIAL rather than claiming
    the shop has no more rewards. Reports retain independently verified claims
    even when later traversal or recovery fails.
    """

    def __init__(self, limits: ExplorerLimits | None = None, clock: Callable[[], float] = time.monotonic):
        self.limits = limits or ExplorerLimits()
        self.clock = clock

    def run(self, port: ExplorerPort, index: int, name: str, cancelled=lambda: False) -> ExplorerResult:
        result = ExplorerResult()
        guard = FreeRewardGuard(index, name)
        started = self.clock()
        edges: set[tuple[str, str]] = set()
        discovered_edges: set[tuple[str, str]] = set()
        discovered_axes: set[tuple[str, str]] = set()
        content: dict[tuple[str, str], set[str]] = {}
        scroll_counts: dict[tuple[str, str], int] = {}
        exhausted: set[tuple[str, str]] = set()
        coverage = True
        screen = None
        pending_reward = None
        pending_route = None
        pending_scroll = None
        before_claim = None

        try:
            for _ in range(self.limits.max_steps):
                if cancelled():
                    result.status = "CANCELLED"
                    break
                if self.clock() - started >= self.limits.max_seconds:
                    result.status = "TIMEOUT"
                    break
                screen = port.observe()
                guard.observe(screen)
                result.visited.append({
                    "page": screen.page, "fingerprint": screen.fingerprint,
                    "capture_id": screen.capture_id, "state": screen.detection.state.value,
                    "screenshot": str(screen.detection.source_image or ""),
                    "red_dot_candidates": list(screen.red_dot_candidates),
                })
                if screen.detection.state == ScreenState.UNKNOWN or screen.detection.confidence < 0.9:
                    result.status = "UNKNOWN_SCREEN"
                    break
                if not screen.page or not screen.fingerprint or not 0 <= screen.depth <= self.limits.max_depth:
                    result.status = "PARTIAL"
                    break
                coverage = coverage and screen.coverage_known
                discovered_edges.update((screen.page, route.id) for route in screen.routes)
                discovered_axes.update((screen.page, axis) for axis in screen.scroll_axes)
                if pending_reward is not None:
                    if not port.verify_claim(before_claim, screen, pending_reward):
                        result.status = "ACTION_RESULT_UNCERTAIN"
                        break
                    result.claimed.append(pending_reward.reward_id)
                    pending_reward = None
                if pending_route is not None:
                    if screen.page != pending_route.destination:
                        result.status = "UNKNOWN_SCREEN"
                        break
                    pending_route = None
                if pending_scroll is not None:
                    key = pending_scroll
                    if screen.page != key[0]:
                        result.status = "UNKNOWN_SCREEN"
                        break
                    if screen.fingerprint in content[key]:
                        exhausted.add(key)
                    content[key].add(screen.fingerprint)
                    pending_scroll = None

                # Check again immediately before dispatch (observation may block).
                if cancelled():
                    result.status = "CANCELLED"
                    break
                if self.clock() - started >= self.limits.max_seconds:
                    result.status = "TIMEOUT"
                    break
                rewards = sorted(screen.rewards, key=lambda reward: not reward.diamond_reward)
                reward = next((r for r in rewards if r.reward_id not in guard.claim_attempts), None)
                if reward is not None:
                    point = guard.claim(screen, reward)
                    result.attempted.append(reward.reward_id)
                    # Mark pending before dispatch: exceptions/timeouts are uncertain.
                    pending_reward, before_claim = reward, screen
                    result.actions.append(f"claim:{reward.reward_id}")
                    port.claim(screen, reward, point)
                    continue

                route = next((r for r in screen.routes if (screen.page, r.id) not in edges), None)
                if route is not None:
                    if route.kind not in {"tab", "submenu", "parent"}:
                        raise SafetyError("Unsupported navigation edge.")
                    point = guard.consume(screen, route.anchor)
                    edges.add((screen.page, route.id))
                    pending_route = route
                    result.actions.append(f"{route.kind}:{route.id}")
                    port.navigate(screen, route, point)
                    continue

                axis = next((a for a in screen.scroll_axes if (screen.page, a) not in exhausted), None)
                if axis is not None:
                    if axis not in {"vertical", "horizontal"}:
                        raise SafetyError("Unsupported scroll direction.")
                    key = screen.page, axis
                    if scroll_counts.get(key, 0) >= self.limits.max_scrolls:
                        result.status = "PARTIAL"
                        break
                    # Adapter must detect a safe scroll surface, not a purchase control.
                    guard.consume(screen, f"scroll:{axis}")
                    content.setdefault(key, set()).add(screen.fingerprint)
                    scroll_counts[key] = scroll_counts.get(key, 0) + 1
                    pending_scroll = key
                    result.actions.append(f"scroll:{axis}")
                    port.scroll(screen, axis)
                    continue

                result.coverage_complete = (
                    coverage and discovered_edges <= edges and discovered_axes <= exhausted
                )
                result.status = (
                    ("SUCCESS" if result.claimed else "NOT_AVAILABLE")
                    if result.coverage_complete else "PARTIAL"
                )
                break
            else:
                result.status = "PARTIAL"

            if pending_reward is not None:
                result.status = "ACTION_RESULT_UNCERTAIN"
            # Never try cleanup against stale evidence or after an uncertain input.
            if (screen is not None and guard.current is screen and pending_reward is None
                    and result.status in {"SUCCESS", "NOT_AVAILABLE", "PARTIAL"} and not cancelled()):
                result.recovery_succeeded = port.return_home(screen)
            return result
        except (OSError, RuntimeError, ValueError) as exc:
            result.status = "ACTION_RESULT_UNCERTAIN" if pending_reward is not None else "SAFETY_BLOCKED"
            result.error = str(exc)
            return result

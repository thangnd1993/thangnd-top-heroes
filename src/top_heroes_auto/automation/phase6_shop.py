"""Bounded, current-frame shop discovery primitives for Phase 6.

The index-2 survey did not prove a zero-cost daily-shop gift.  This module is
therefore an injectable discovery adapter, not a packaged Free Pack profile:
red dots and gift-shaped controls are recorded as diagnostics only, and claims
remain disabled unless the caller supplies independent post evidence and opts
in explicitly.

The survey path models scrolling at the axis level only.  It deliberately
reports partial coverage for any scroll-bearing page until independent
up/down or left/right boundary evidence is available.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable, Iterable, Protocol

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.free_rewards import (
    ClaimOutcome,
    Cost,
    ExplorerPort,
    RewardEvidence,
    RewardScreen,
    Route,
)
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.phase6_visual import Matcher, RewardRule
from top_heroes_auto.vision.exploration import (
    content_fingerprint,
    red_dot_candidates,
    unique_current_anchor,
)
from top_heroes_auto.vision.models import (
    AnchorEvidence,
    CapturedScreen,
    NormalizedRect,
    ScreenDetection,
    ScreenState,
    VisualAnchor,
)
from top_heroes_auto.vision.screenshot import ScreenshotService


@dataclass(frozen=True)
class ShopRouteRule:
    """A declared tab/submenu edge; its tap point is always current-frame evidence."""

    id: str
    role: str
    destination: str
    kind: str = "tab"


@dataclass(frozen=True)
class ShopVisualProfile:
    """Semantic shop scope with no coordinates or historical frame state."""

    task: str
    page: str
    anchors: tuple[tuple[str, VisualAnchor], ...]
    rewards: tuple[RewardRule, ...] = ()
    routes: tuple[ShopRouteRule, ...] = ()
    scroll_axes: tuple[str, ...] = ()
    coverage_known: bool = False
    claim_enabled: bool = False
    page_state: ScreenState = ScreenState.FREE_REWARD_PAGE

    def __post_init__(self):
        if not self.task.strip() or not self.page.strip():
            raise ValueError("Task and shop page are required.")
        roles = [role for role, _ in self.anchors]
        if len(roles) != len(set(roles)):
            raise ValueError("Shop anchor roles must be unique.")
        anchor_ids = [anchor.id for _, anchor in self.anchors]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("Shop anchor IDs must be unique.")
        known = set(roles)
        if "page" not in known:
            raise ValueError("A shop page anchor is required.")
        if any(axis not in {"vertical", "horizontal"} for axis in self.scroll_axes):
            raise ValueError("Only bounded vertical or horizontal shop scrolling is supported.")
        if len(set(self.scroll_axes)) != len(self.scroll_axes):
            raise ValueError("Shop scroll axes must be unique.")
        for route in self.routes:
            if route.role not in known:
                raise ValueError(f"Shop route {route.id!r} references missing role {route.role!r}.")
        for reward in self.rewards:
            for role in (reward.action_role, reward.free_role, reward.available_role, reward.paid_role):
                if role is not None and role not in known:
                    raise ValueError(f"Shop reward {reward.reward_id!r} references missing role {role!r}.")
        if self.claim_enabled and "post" not in known:
            raise ValueError("An enabled shop claim requires an independent post anchor.")

    @property
    def anchor_map(self) -> dict[str, VisualAnchor]:
        return dict(self.anchors)


@dataclass(frozen=True)
class ShopFrameObservation:
    captured: CapturedScreen
    screen: RewardScreen
    evidence: dict[str, AnchorEvidence]


class ShopSurveyStatus(StrEnum):
    """Observation-only shop survey outcomes."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN_SCREEN = "UNKNOWN_SCREEN"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    SAFETY_BLOCKED = "SAFETY_BLOCKED"
    ACTION_RESULT_UNCERTAIN = "ACTION_RESULT_UNCERTAIN"


@dataclass(frozen=True)
class ShopSurveyLimits:
    """Small bounds for discovery; these are not claim/retry limits."""

    max_steps: int = 40
    max_depth: int = 3
    max_scrolls_per_axis: int = 3
    max_seconds: float = 60.0

    def __post_init__(self):
        if self.max_steps <= 0 or self.max_depth < 0 or self.max_scrolls_per_axis <= 0:
            raise ValueError("Shop survey bounds must be positive, with non-negative depth.")
        if self.max_seconds <= 0:
            raise ValueError("Shop survey timeout must be positive.")


@dataclass
class ShopSurveyResult:
    """Durable-safe survey data; this model has no claim or journal operation."""

    status: ShopSurveyStatus = ShopSurveyStatus.UNKNOWN_SCREEN
    visited: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    partial_reasons: list[str] = field(default_factory=list)
    coverage_complete: bool = False
    claims: list[str] = field(default_factory=list)
    journal_rows: int = 0
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "result": self.status.value,
            "visited": list(self.visited),
            "actions": list(self.actions),
            "partial_reasons": list(self.partial_reasons),
            "coverage_complete": self.coverage_complete,
            # Explicitly prove that this path did not claim or journal.
            "claims": list(self.claims),
            "journal_rows": self.journal_rows,
            "error": self.error,
        }


class ShopSurveyPort(Protocol):
    """Injectable observation/navigation boundary with no claim method."""

    def observe(self) -> ShopFrameObservation: ...

    def navigate(self, observation: ShopFrameObservation, route: Route, point: tuple[int, int]) -> None: ...

    def scroll(self, observation: ShopFrameObservation, axis: str, point: tuple[int, int]) -> None: ...

    def backtrack(self, observation: ShopFrameObservation, route: Route, point: tuple[int, int]) -> None: ...


@dataclass
class _SurveyContext:
    page: str
    depth: int
    routes_seen: set[str]
    route_obligations: set[str]
    scroll_counts: dict[str, int]
    no_progress: set[str]


@dataclass(frozen=True)
class _PendingSurveyAction:
    kind: str
    expected_page: str
    previous_fingerprint: str | None = None
    route: Route | None = None
    axis: str | None = None


class _SurveyIdentityMismatch(SafetyError):
    pass


def _capture_id(screen: CapturedScreen) -> str:
    if screen.source_image:
        return str(screen.source_image)
    digest = hashlib.sha256(screen.normalized.tobytes()).hexdigest()
    return f"frame:{screen.timestamp}:{digest}"


def _strong(evidence: AnchorEvidence | None) -> bool:
    return bool(
        evidence
        and evidence.matched
        and evidence.device_box is not None
        and math.isfinite(evidence.score)
        and math.isfinite(evidence.threshold)
        and evidence.score >= max(0.9, evidence.threshold)
    )


class ShopSurveyEngine:
    """Traverse declared shop evidence without exposing a claim interface.

    This engine is intentionally separate from ``FreeRewardExplorer``.  Its
    port cannot claim a reward, and the engine never creates a journal adapter.
    It may navigate declared sibling tabs, scroll a verified current surface,
    and use a declared parent edge to backtrack.  Every action is followed by
    a fresh, same-account frame before the next action is considered.
    """

    def __init__(
        self,
        limits: ShopSurveyLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limits = limits or ShopSurveyLimits()
        self.clock = clock

    @staticmethod
    def _reason(result: ShopSurveyResult, reason: str) -> None:
        if reason not in result.partial_reasons:
            result.partial_reasons.append(reason)

    @staticmethod
    def _point(observation: ShopFrameObservation, anchor_id: str) -> tuple[int, int]:
        matches = [item for item in observation.evidence.values() if item.anchor_id == anchor_id]
        if len(matches) != 1:
            raise SafetyError(f"Shop survey action anchor {anchor_id!r} is missing or ambiguous.")
        evidence = matches[0]
        if not _strong(evidence):
            raise SafetyError(f"Shop survey action anchor {anchor_id!r} is missing or ambiguous.")
        if evidence.device_box is None:
            raise SafetyError(f"Shop survey action anchor {anchor_id!r} has no device point.")
        return evidence.device_box.center

    @staticmethod
    def _identity(observation: ShopFrameObservation) -> tuple[int, str, str, str]:
        captured = observation.captured
        screen = observation.screen
        captured_identity = captured.index, captured.name, captured.serial, captured.boot_id
        screen_identity = screen.index, screen.name, screen.adb_target, screen.boot_id
        if captured_identity != screen_identity:
            raise _SurveyIdentityMismatch("Shop frame identity disagrees with its captured transport.")
        if not all(screen_identity):
            raise _SurveyIdentityMismatch("Shop frame is missing explicit account or transport identity.")
        return screen_identity

    def _record_frame(
        self,
        result: ShopSurveyResult,
        observation: ShopFrameObservation,
        expected: tuple[int, str],
        identity: tuple[int, str, str, str] | None,
        seen_captures: set[str],
    ) -> tuple[int, str, str, str]:
        current = self._identity(observation)
        if current[:2] != expected:
            raise _SurveyIdentityMismatch("Shop survey account identity changed.")
        if identity is not None and current[2:] != identity[2:]:
            raise _SurveyIdentityMismatch("Shop survey serial or boot identity changed.")
        if not observation.screen.capture_id or observation.screen.capture_id in seen_captures:
            raise SafetyError("Shop survey requires a fresh screenshot for every observation.")
        seen_captures.add(observation.screen.capture_id)
        result.visited.append(
            {
                "page": observation.screen.page,
                "fingerprint": observation.screen.fingerprint,
                "capture_id": observation.screen.capture_id,
                "state": observation.screen.detection.state.value,
                "screenshot": str(observation.screen.detection.source_image or ""),
                "red_dot_candidates": list(observation.screen.red_dot_candidates),
                "routes": [route.id for route in observation.screen.routes],
                "scroll_axes": list(observation.screen.scroll_axes),
                "rewards": [
                    {
                        "reward_id": reward.reward_id,
                        "cost": reward.cost.value,
                        "ambiguous": reward.ambiguous,
                        "diamond_reward": reward.diamond_reward,
                        "action_anchor": reward.action_anchor,
                        "free_anchor": reward.free_anchor,
                        "available_anchor": reward.available_anchor,
                    }
                    for reward in observation.screen.rewards
                ],
            }
        )
        return current

    @staticmethod
    def _select_route(screen: RewardScreen, context: _SurveyContext) -> Route | None:
        for route in screen.routes:
            if route.kind not in {"tab", "submenu", "parent"}:
                raise SafetyError(f"Unsupported shop survey navigation edge: {route.kind!r}.")
            if route.kind != "parent" and route.id not in context.routes_seen:
                return route
        return None

    def run(
        self,
        port: ShopSurveyPort,
        index: int,
        name: str,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> ShopSurveyResult:
        result = ShopSurveyResult()
        expected = index, name
        identity: tuple[int, str, str, str] | None = None
        seen_captures: set[str] = set()
        contexts: list[_SurveyContext] = []
        pending: _PendingSurveyAction | None = None
        started = self.clock()
        coverage = True

        try:
            for _ in range(self.limits.max_steps):
                if cancelled():
                    result.status = ShopSurveyStatus.CANCELLED
                    break
                if self.clock() - started >= self.limits.max_seconds:
                    result.status = ShopSurveyStatus.TIMEOUT
                    self._reason(result, "time_bound")
                    break

                observation = port.observe()
                identity = self._record_frame(result, observation, expected, identity, seen_captures)
                screen = observation.screen
                if screen.detection.state == ScreenState.UNKNOWN or screen.detection.confidence < 0.9:
                    result.status = ShopSurveyStatus.UNKNOWN_SCREEN
                    self._reason(result, "unknown_or_low_confidence_screen")
                    break
                if not screen.page or not screen.fingerprint:
                    result.status = ShopSurveyStatus.PARTIAL
                    self._reason(result, "missing_page_identity")
                    break
                if not screen.coverage_known:
                    coverage = False
                    self._reason(result, "coverage_unknown_or_dynamic")
                if screen.scroll_axes:
                    # Scroll surfaces are represented by axis only in this
                    # milestone. Reverse boundaries (up/down or left/right)
                    # are not independently evidenced, so coverage remains
                    # PARTIAL whenever a scroll surface is exposed.
                    coverage = False
                    self._reason(result, f"directional_scroll_coverage_unproven:{screen.page}")

                if pending is not None:
                    if screen.page != pending.expected_page:
                        result.status = ShopSurveyStatus.PARTIAL
                        self._reason(result, f"destination_unverified:{pending.expected_page}")
                        result.error = (
                            f"Expected {pending.expected_page!r}, observed {screen.page!r} "
                            "after the last observation-only action."
                        )
                        break
                    if pending.kind == "navigate":
                        if pending.route is None:
                            raise SafetyError("Shop survey navigation lost its route state.")
                        if pending.route.kind == "parent":
                            if len(contexts) <= 1:
                                raise SafetyError("Shop survey parent edge has no nested context.")
                            contexts.pop()
                        else:
                            depth = contexts[-1].depth + 1
                            if depth > self.limits.max_depth:
                                result.status = ShopSurveyStatus.PARTIAL
                                self._reason(result, "depth_bound")
                                break
                            contexts.append(_SurveyContext(screen.page, depth, set(), set(), {}, set()))
                    elif pending.kind == "scroll":
                        context = contexts[-1]
                        if pending.axis is None or pending.previous_fingerprint is None:
                            raise SafetyError("Shop survey scroll lost its observation state.")
                        if screen.fingerprint == pending.previous_fingerprint:
                            context.no_progress.add(pending.axis)
                            coverage = False
                            self._reason(result, f"no_progress:{screen.page}:{pending.axis}")
                    pending = None

                if not contexts:
                    contexts.append(_SurveyContext(screen.page, 0, set(), set(), {}, set()))
                elif contexts[-1].page != screen.page:
                    result.status = ShopSurveyStatus.PARTIAL
                    self._reason(result, "unexpected_page_transition")
                    break

                context = contexts[-1]
                current_route_ids = {
                    route.id for route in screen.routes if route.kind != "parent"
                }
                missing_routes = context.route_obligations - context.routes_seen - current_route_ids
                if missing_routes:
                    coverage = False
                    for route_id in sorted(missing_routes):
                        self._reason(result, f"missing_route_after_backtrack:{route_id}")
                    result.status = ShopSurveyStatus.PARTIAL
                    break
                context.route_obligations.update(current_route_ids)
                if cancelled():
                    result.status = ShopSurveyStatus.CANCELLED
                    break
                if self.clock() - started >= self.limits.max_seconds:
                    result.status = ShopSurveyStatus.TIMEOUT
                    self._reason(result, "time_bound_before_dispatch")
                    break

                route = self._select_route(screen, context)
                if route is not None:
                    if context.depth >= self.limits.max_depth:
                        coverage = False
                        self._reason(result, "depth_bound")
                    else:
                        context.routes_seen.add(route.id)
                        point = self._point(observation, route.anchor)
                        pending = _PendingSurveyAction("navigate", route.destination, route=route)
                        result.actions.append(f"{route.kind}:{route.id}")
                        port.navigate(observation, route, point)
                        continue

                axis = next(
                    (
                        axis
                        for axis in screen.scroll_axes
                        if axis in {"vertical", "horizontal"}
                        and axis not in context.no_progress
                        and context.scroll_counts.get(axis, 0) < self.limits.max_scrolls_per_axis
                    ),
                    None,
                )
                for declared_axis in screen.scroll_axes:
                    if (
                        declared_axis in {"vertical", "horizontal"}
                        and declared_axis not in context.no_progress
                        and context.scroll_counts.get(declared_axis, 0) >= self.limits.max_scrolls_per_axis
                    ):
                        coverage = False
                        self._reason(result, f"scroll_bound:{screen.page}:{declared_axis}")
                        context.no_progress.add(declared_axis)
                if axis is not None:
                    evidence = observation.evidence.get(f"scroll:{axis}")
                    point = self._point(observation, f"scroll:{axis}")
                    context.scroll_counts[axis] = context.scroll_counts.get(axis, 0) + 1
                    pending = _PendingSurveyAction(
                        "scroll",
                        screen.page,
                        previous_fingerprint=screen.fingerprint,
                        axis=axis,
                    )
                    result.actions.append(f"scroll:{axis}")
                    # Keep the local binding to make it clear that no route or
                    # red-dot point is used for a scroll dispatch.
                    if evidence is None:
                        raise SafetyError("Shop survey scroll evidence disappeared before dispatch.")
                    port.scroll(observation, axis, point)
                    continue

                if context.depth > 0:
                    parent = next(
                        (
                            route
                            for route in screen.routes
                            if route.kind == "parent" and route.id not in context.routes_seen
                        ),
                        None,
                    )
                    if parent is None:
                        coverage = False
                        self._reason(result, f"missing_backtrack:{screen.page}")
                        result.status = ShopSurveyStatus.PARTIAL
                        break
                    if len(contexts) < 2 or parent.destination != contexts[-2].page:
                        coverage = False
                        self._reason(result, f"invalid_backtrack_destination:{parent.id}")
                        result.status = ShopSurveyStatus.PARTIAL
                        break
                    context.routes_seen.add(parent.id)
                    point = self._point(observation, parent.anchor)
                    pending = _PendingSurveyAction("navigate", parent.destination, route=parent)
                    result.actions.append(f"backtrack:{parent.id}")
                    port.backtrack(observation, parent, point)
                    continue
                elif any(route.kind == "parent" for route in screen.routes):
                    coverage = False
                    self._reason(result, f"invalid_root_parent:{screen.page}")

                result.coverage_complete = coverage
                result.status = ShopSurveyStatus.COMPLETE if coverage else ShopSurveyStatus.PARTIAL
                break
            else:
                result.status = ShopSurveyStatus.PARTIAL
                self._reason(result, "step_bound")
            return result
        except _SurveyIdentityMismatch as exc:
            result.status = ShopSurveyStatus.IDENTITY_MISMATCH
            result.error = str(exc)
            return result
        except SafetyError as exc:
            result.status = ShopSurveyStatus.SAFETY_BLOCKED
            result.error = str(exc)
            return result
        except (OSError, RuntimeError, ValueError) as exc:
            result.status = (
                ShopSurveyStatus.ACTION_RESULT_UNCERTAIN
                if result.actions
                else ShopSurveyStatus.SAFETY_BLOCKED
            )
            result.error = str(exc)
            return result


class FrameShopAdapter:
    """Interpret one current shop frame without reusing any prior coordinate."""

    def __init__(self, profile: ShopVisualProfile, matcher: Matcher = unique_current_anchor):
        self.profile = profile
        self.matcher = matcher

    def observe(self, captured: CapturedScreen) -> ShopFrameObservation:
        evidence = {
            role: self.matcher(captured, anchor)
            for role, anchor in self.profile.anchors
        }
        page = evidence["page"]
        page_matched = _strong(page)
        scores = [item.score for item in evidence.values() if item.matched]
        detection = ScreenDetection(
            self.profile.page_state if page_matched else ScreenState.UNKNOWN,
            float(min(scores) if page_matched and scores else 0.0),
            tuple(evidence.values()),
            captured.timestamp,
            captured.source_image,
            0.0,
        )
        routes = tuple(
            Route(route.id, evidence[route.role].anchor_id, route.destination, route.kind)
            for route in self.profile.routes
            if _strong(evidence.get(route.role))
        )
        axes = tuple(
            axis for axis in self.profile.scroll_axes
            if _strong(evidence.get(f"scroll:{axis}"))
        )
        rewards = tuple(self._reward(rule, evidence) for rule in self.profile.rewards)
        screen = RewardScreen(
            detection=detection,
            index=captured.index,
            name=captured.name,
            adb_target=captured.serial,
            boot_id=captured.boot_id,
            capture_id=_capture_id(captured),
            page=self.profile.page,
            fingerprint=content_fingerprint(captured, (NormalizedRect(0, 0, 1, 1),)),
            rewards=rewards,
            routes=routes,
            scroll_axes=axes,
            red_dot_candidates=tuple(
                f"red-dot:{box.x},{box.y},{box.width},{box.height}"
                for box in red_dot_candidates(captured, NormalizedRect(0, 0, 1, 1))
            ),
            coverage_known=(
                self.profile.coverage_known
                and page_matched
                and all(
                    _strong(evidence.get(route.role))
                    for route in self.profile.routes
                )
                and all(
                    _strong(evidence.get(f"scroll:{axis}"))
                    for axis in self.profile.scroll_axes
                )
            ),
        )
        return ShopFrameObservation(captured, screen, evidence)

    def classify_claim(self, before: RewardScreen, after: RewardScreen, reward: RewardEvidence) -> ClaimOutcome:
        """Classify only independently anchored receipt/cooldown frames."""

        if (before.index, before.name, before.adb_target, before.boot_id) != (
            after.index,
            after.name,
            after.adb_target,
            after.boot_id,
        ):
            return ClaimOutcome.IDENTITY_MISMATCH
        evidence = {item.anchor_id: item for item in after.detection.evidence}
        free_state = _strong(evidence.get(reward.action_anchor)) or _strong(
            evidence.get(reward.available_anchor)
        )
        if free_state:
            return ClaimOutcome.UNKNOWN
        post = self.profile.anchor_map.get("post")
        cooldown = self.profile.anchor_map.get("cooldown")
        post_match = bool(post and _strong(evidence.get(post.id)))
        cooldown_match = bool(cooldown and _strong(evidence.get(cooldown.id)))
        if post_match and cooldown_match:
            return ClaimOutcome.UNKNOWN
        if post_match:
            return ClaimOutcome.CLAIMED
        if cooldown_match:
            return ClaimOutcome.COOLDOWN
        return ClaimOutcome.UNKNOWN

    @staticmethod
    def _reward(rule: RewardRule, evidence: dict[str, AnchorEvidence]) -> RewardEvidence:
        action = evidence.get(rule.action_role)
        free = evidence.get(rule.free_role) if rule.free_role else None
        available = evidence.get(rule.available_role) if rule.available_role else None
        paid = evidence.get(rule.paid_role) if rule.paid_role else None
        if _strong(paid):
            cost, ambiguous = rule.paid_cost, False
        elif _strong(action) and _strong(free) and _strong(available):
            cost, ambiguous = Cost.FREE, False
        else:
            cost, ambiguous = Cost.UNKNOWN, True
        return RewardEvidence(
            reward_id=rule.reward_id,
            action_anchor=action.anchor_id if action else rule.action_role,
            free_anchor=free.anchor_id if free else (rule.free_role or "free-missing"),
            available_anchor=available.anchor_id if available else (rule.available_role or "available-missing"),
            cost=cost,
            ambiguous=ambiguous,
            diamond_reward=rule.diamond_reward,
        )


class ManagerShopPort(ExplorerPort):
    """Manager bridge for injected shop profiles with explicit safe actions."""

    def __init__(
        self,
        manager: Manager,
        snapshot: RunSnapshot,
        index: int,
        name: str,
        profile: ShopVisualProfile,
        folder: Path | None = None,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.adapter = FrameShopAdapter(profile)
        self.folder = folder
        self._last: ShopFrameObservation | None = None
        self._target: Target | None = None

    def _dispatch(self, action: str, values: tuple[int, ...]):
        if self._target is None:
            raise SafetyError("No current screenshot target is available.")
        return self.manager.execute(
            self.index,
            action,
            values=values,
            snapshot=self.snapshot,
            observed_target=self._target,
        )

    def observe(self) -> RewardScreen:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        if (target.index, target.name) != (self.index, self.name):
            raise SafetyError("Shop capture identity changed.")
        if self._target and (target.serial, target.boot_id) != (self._target.serial, self._target.boot_id):
            raise SafetyError("Shop capture transport identity changed.")
        self._target = target
        captured = ScreenshotService(lambda serial: payload if serial == target.serial else b"").take(
            target, self.folder, "phase6-shop"
        )
        self._last = self.adapter.observe(captured)
        return self._last.screen

    def _current(self, screen: RewardScreen) -> ShopFrameObservation:
        if self._last is None or self._last.screen is not screen:
            raise SafetyError("Shop action evidence is stale; capture a fresh frame.")
        return self._last

    def claim(self, screen, reward, point):
        self._current(screen)
        if not self.adapter.profile.claim_enabled:
            raise SafetyError("Free Pack claims are disabled until post evidence is proven.")
        if "post" not in self.adapter.profile.anchor_map:
            raise SafetyError("Free Pack claim requires an independent post anchor.")
        self._dispatch("tap", point)

    def classify_claim(self, before, after, reward) -> ClaimOutcome:
        self._current(after)
        return self.adapter.classify_claim(before, after, reward)

    def verify_claim(self, before, after, reward) -> bool:
        return self.classify_claim(before, after, reward) in {
            ClaimOutcome.CLAIMED,
        }

    def navigate(self, screen, route, point):
        self._current(screen)
        self._dispatch("tap", point)

    def scroll(self, screen, axis):
        observation = self._current(screen)
        evidence = observation.evidence.get(f"scroll:{axis}")
        if not _strong(evidence):
            raise SafetyError("No current-frame verified shop scroll surface.")
        box = evidence.device_box
        if box is None or box.width <= 1 or box.height <= 1:
            raise SafetyError("Shop scroll surface is unusable.")
        cx, cy = box.center
        if axis == "vertical":
            values = (cx, box.y + round(box.height * 0.8), cx, box.y + round(box.height * 0.2), 300)
        elif axis == "horizontal":
            values = (box.x + round(box.width * 0.8), cy, box.x + round(box.width * 0.2), cy, 300)
        else:
            raise SafetyError("Unsupported shop scroll direction.")
        self._dispatch("swipe", values)

    def return_home(self, screen):
        raise SafetyError("Shop cleanup requires an explicit fresh Home route.")


def free_pack_profile(
    anchors: dict[str, VisualAnchor],
    *,
    rewards: Iterable[RewardRule] = (),
    routes: Iterable[ShopRouteRule] = (),
    scroll_axes: Iterable[str] = (),
    coverage_known: bool = False,
    claim_enabled: bool = False,
) -> ShopVisualProfile:
    """Build an injectable shop profile; no packaged profile enables claims."""

    return ShopVisualProfile(
        "free-pack",
        "shop",
        tuple(anchors.items()),
        tuple(rewards),
        tuple(routes),
        tuple(scroll_axes),
        coverage_known=coverage_known,
        claim_enabled=claim_enabled,
    )

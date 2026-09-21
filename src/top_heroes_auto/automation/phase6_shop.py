"""Bounded, current-frame shop discovery primitives for Phase 6.

The index-2 survey did not prove a zero-cost daily-shop gift.  This module is
therefore an injectable discovery adapter, not a packaged Free Pack profile:
red dots and gift-shaped controls are recorded as diagnostics only, and claims
remain disabled unless the caller supplies independent post evidence and opts
in explicitly.

The survey path accepts explicit directional scroll surfaces, but deliberately
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
from top_heroes_auto.automation.phase6_promo_recovery import (
    PromoRecoveryResult,
    PromoRecoveryStatus,
)
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
    # Newer observation-only adapters may declare explicit directional
    # surfaces and masked fingerprint regions.  Keep these after the legacy
    # fields so positional profile construction remains compatible.
    scroll_directions: tuple[str, ...] = ()
    fingerprint_regions: tuple[NormalizedRect, ...] = ()

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
        if any(direction not in {"up", "down", "left", "right"} for direction in self.scroll_directions):
            raise ValueError("Shop scroll directions must be up, down, left, or right.")
        if len(set(self.scroll_directions)) != len(self.scroll_directions):
            raise ValueError("Shop scroll directions must be unique.")
        if self.scroll_axes and self.scroll_directions:
            raise ValueError("Declare legacy scroll axes or explicit directions, not both.")
        if any(not isinstance(region, NormalizedRect) for region in self.fingerprint_regions):
            raise ValueError("Shop fingerprint regions must be normalized rectangles.")
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
    max_scrolls_per_direction: int | None = None
    max_seconds: float = 60.0

    def __post_init__(self):
        if self.max_steps <= 0 or self.max_depth < 0 or self.max_scrolls_per_axis <= 0:
            raise ValueError("Shop survey bounds must be positive, with non-negative depth.")
        if self.max_seconds <= 0:
            raise ValueError("Shop survey timeout must be positive.")
        if self.max_scrolls_per_direction is not None and self.max_scrolls_per_direction <= 0:
            raise ValueError("Directional scroll budget must be positive when declared.")

    @property
    def scroll_budget(self) -> int:
        return self.max_scrolls_per_direction or self.max_scrolls_per_axis


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
    promo_recovery: PromoRecoveryResult | None = None

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
            "promo_recovery": self.promo_recovery.as_dict() if self.promo_recovery else None,
        }


class ShopSurveyPort(Protocol):
    """Injectable observation/navigation boundary with no claim method."""

    def observe(self) -> ShopFrameObservation: ...

    def navigate(self, observation: ShopFrameObservation, route: Route, point: tuple[int, int]) -> None: ...

    def scroll(self, observation: ShopFrameObservation, axis: str, point: tuple[int, int]) -> None: ...

    def backtrack(self, observation: ShopFrameObservation, route: Route, point: tuple[int, int]) -> None: ...


class _SurveyCancelled(SafetyError):
    """Cancellation reached a port boundary before a pending popup Back."""

    pass


@dataclass
class _SurveyContext:
    page: str
    depth: int
    routes_seen: set[str]
    route_obligations: set[str]
    scroll_counts: dict[str, int]
    no_progress: set[str]
    tab_parent: "_SurveyContext | None" = None


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
                "scroll_directions": list(observation.screen.scroll_directions),
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
    def _take_promo_recovery(port: ShopSurveyPort, result: ShopSurveyResult) -> None:
        take = getattr(port, "take_promo_recovery", None)
        if callable(take):
            promo = take()
            if promo is not None:
                result.promo_recovery = promo

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

                if pending is not None:
                    arm = getattr(port, "arm_pending_promo", None)
                    if callable(arm):
                        arm(pending.expected_page, cancelled)
                try:
                    observation = port.observe()
                except Exception:
                    self._take_promo_recovery(port, result)
                    raise
                self._take_promo_recovery(port, result)
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
                scroll_surfaces = screen.scroll_directions or screen.scroll_axes
                if scroll_surfaces:
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
                            current = contexts[-1]
                            if current.tab_parent is not None:
                                if pending.route.destination != current.tab_parent.page:
                                    raise SafetyError("Shop survey tab parent destination is not verified.")
                                restored = current.tab_parent
                                restored.routes_seen.update(current.routes_seen)
                                restored.route_obligations.update(current.route_obligations)
                                contexts[-1] = restored
                            else:
                                if len(contexts) <= 1:
                                    raise SafetyError("Shop survey parent edge has no nested context.")
                                contexts.pop()
                        else:
                            # A tab changes the current sibling page without
                            # increasing nested depth. A submenu creates a
                            # nested context that must later backtrack to its
                            # actual parent.
                            depth = contexts[-1].depth + (1 if pending.route.kind == "submenu" else 0)
                            if depth > self.limits.max_depth:
                                result.status = ShopSurveyStatus.PARTIAL
                                self._reason(result, "depth_bound")
                                break
                            if pending.route.kind == "tab":
                                previous = contexts[-1]
                                contexts[-1] = _SurveyContext(
                                    screen.page,
                                    depth,
                                    set(previous.routes_seen),
                                    set(previous.route_obligations),
                                    {},
                                    set(),
                                    previous.tab_parent or previous,
                                )
                            else:
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
                # A lateral tab temporarily replaces the current page.  Its
                # retained obligations belong to the tab parent and must be
                # checked only after the declared parent edge restores that
                # page, otherwise a valid backtrack is blocked before it can
                # expose a disappeared sibling.
                missing_routes = (
                    set()
                    if context.tab_parent is not None
                    else context.route_obligations - context.routes_seen - current_route_ids
                )
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
                    if route.kind == "submenu" and context.depth >= self.limits.max_depth:
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
                        for axis in scroll_surfaces
                        if axis in {"vertical", "horizontal", "up", "down", "left", "right"}
                        and axis not in context.no_progress
                        and context.scroll_counts.get(axis, 0) < self.limits.scroll_budget
                    ),
                    None,
                )
                for declared_axis in scroll_surfaces:
                    if (
                        declared_axis in {"vertical", "horizontal", "up", "down", "left", "right"}
                        and declared_axis not in context.no_progress
                        and context.scroll_counts.get(declared_axis, 0) >= self.limits.scroll_budget
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

                if len(contexts) > 1 or context.tab_parent is not None:
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
                    expected_parent = (
                        context.tab_parent.page
                        if context.tab_parent is not None
                        else contexts[-2].page
                        if len(contexts) >= 2
                        else None
                    )
                    if expected_parent is None or parent.destination != expected_parent:
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
        except _SurveyCancelled as exc:
            self._take_promo_recovery(port, result)
            result.status = ShopSurveyStatus.CANCELLED
            result.error = str(exc)
            return result
        except _SurveyIdentityMismatch as exc:
            self._take_promo_recovery(port, result)
            result.status = ShopSurveyStatus.IDENTITY_MISMATCH
            result.error = str(exc)
            return result
        except SafetyError as exc:
            self._take_promo_recovery(port, result)
            promo_status = result.promo_recovery.status if result.promo_recovery else None
            result.status = {
                PromoRecoveryStatus.CANCELLED: ShopSurveyStatus.CANCELLED,
                PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN: ShopSurveyStatus.ACTION_RESULT_UNCERTAIN,
                PromoRecoveryStatus.IDENTITY_MISMATCH: ShopSurveyStatus.IDENTITY_MISMATCH,
                PromoRecoveryStatus.TIMEOUT: ShopSurveyStatus.TIMEOUT,
            }.get(promo_status, ShopSurveyStatus.SAFETY_BLOCKED)
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
        axes = tuple(axis for axis in self.profile.scroll_axes if _strong(evidence.get(f"scroll:{axis}")))
        directions = tuple(
            direction
            for direction in self.profile.scroll_directions
            if _strong(evidence.get(f"scroll:{direction}"))
        )
        fingerprint_regions = self.profile.fingerprint_regions or (NormalizedRect(0, 0, 1, 1),)
        rewards = tuple(self._reward(rule, evidence) for rule in self.profile.rewards)
        screen = RewardScreen(
            detection=detection,
            index=captured.index,
            name=captured.name,
            adb_target=captured.serial,
            boot_id=captured.boot_id,
            capture_id=_capture_id(captured),
            page=self.profile.page,
            fingerprint=content_fingerprint(captured, fingerprint_regions),
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
                and all(
                    _strong(evidence.get(f"scroll:{direction}"))
                    for direction in self.profile.scroll_directions
                )
            ),
            scroll_directions=directions,
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


class ShopProfileRegistry:
    """Resolve a fresh frame to exactly one independently qualified profile.

    The registry is intentionally strict: a missing page anchor or two page
    anchors matching the same frame is a safety block, never a reason to pick
    the first profile or reuse a prior route.  Profiles may declare only the
    surfaces that have been qualified for the current account.
    """

    def __init__(
        self,
        profiles: Iterable[ShopVisualProfile],
        matcher: Matcher = unique_current_anchor,
    ):
        self.profiles = tuple(profiles)
        if not self.profiles:
            raise ValueError("At least one independently qualified shop profile is required.")
        pages = [profile.page for profile in self.profiles]
        if len(pages) != len(set(pages)):
            raise ValueError("Shop profile page names must be unique.")
        self.matcher = matcher

    def observe(self, captured: CapturedScreen) -> ShopFrameObservation:
        matches = []
        for profile in self.profiles:
            observation = FrameShopAdapter(profile, self.matcher).observe(captured)
            if _strong(observation.evidence.get("page")):
                matches.append(observation)
        if len(matches) != 1:
            if not matches:
                raise SafetyError("Current frame has no uniquely verified shop page.")
            raise SafetyError("Current frame ambiguously matches multiple shop pages.")
        return matches[0]


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


class ManagerShopSurveyPort:
    """Manager bridge for the claim-free, observation-only survey engine.

    This port exposes only fresh observation, navigation, and bounded scroll
    dispatch.  It deliberately has no ``claim`` or journal-facing methods.
    Every input is bound to the exact screenshot target that authorized it;
    after dispatch the observation is invalidated so one frame cannot authorize
    a repeated action.
    """

    def __init__(
        self,
        manager: Manager,
        snapshot: RunSnapshot,
        index: int,
        name: str,
        registry: ShopProfileRegistry,
        folder: Path | None = None,
        *,
        pending_promo_anchor: VisualAnchor | None = None,
        promo_budget_available: bool = False,
        promo_observations: int = 3,
        promo_wait_seconds: float = 0.25,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.registry = registry
        self.folder = folder
        if pending_promo_anchor is not None and pending_promo_anchor.state != ScreenState.POPUP_GENERIC:
            raise ValueError("Pending promo anchor must be a POPUP_GENERIC anchor.")
        if not 1 <= promo_observations <= 3:
            raise ValueError("Pending promo recovery allows one to three observations.")
        if promo_wait_seconds < 0:
            raise ValueError("Pending promo wait cannot be negative.")
        self.pending_promo_anchor = pending_promo_anchor
        self._promo_budget_available = promo_budget_available
        self._promo_observations = promo_observations
        self._promo_wait_seconds = promo_wait_seconds
        self._pending_expected_page: str | None = None
        self._pending_cancelled: Callable[[], bool] = lambda: False
        self._promo_recovery: PromoRecoveryResult | None = None
        self._last: ShopFrameObservation | None = None
        self._target: Target | None = None

    def arm_pending_promo(self, expected_page: str, cancelled: Callable[[], bool]) -> None:
        """Arm one popup probe for the fresh frame after a survey action."""

        self._pending_expected_page = expected_page
        self._pending_cancelled = cancelled

    def take_promo_recovery(self) -> PromoRecoveryResult | None:
        promo = self._promo_recovery
        self._promo_recovery = None
        return promo

    @staticmethod
    def _frame_dict(target: Target, captured: CapturedScreen) -> dict:
        return {
            "capture": _capture_id(captured),
            "instance": {"index": target.index, "name": target.name},
            "adb_target": target.serial,
            "boot_id": target.boot_id,
            "timestamp": captured.timestamp,
        }

    def _capture(
        self,
        tag: str,
        *,
        allow_transport_change: bool = False,
    ) -> tuple[Target, CapturedScreen]:
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        if (target.index, target.name) != (self.index, self.name):
            raise SafetyError("Shop survey capture identity changed.")
        if (
            self._target
            and not allow_transport_change
            and (target.serial, target.boot_id) != (self._target.serial, self._target.boot_id)
        ):
            raise _SurveyIdentityMismatch("Shop survey transport identity changed.")
        self._target = target
        captured = ScreenshotService(
            lambda serial: payload if serial == target.serial else b""
        ).take(target, self.folder, tag)
        return target, captured

    def _pending_promo_destination(self, target: Target, captured: CapturedScreen) -> ShopFrameObservation:
        expected_page = self._pending_expected_page
        anchor = self.pending_promo_anchor
        if expected_page is None or anchor is None or not self._promo_budget_available:
            raise SafetyError("Current frame has no uniquely verified shop page.")
        evidence = unique_current_anchor(captured, anchor)
        if not evidence.matched:
            self._promo_budget_available = False if evidence.score >= max(0.9, evidence.threshold) else self._promo_budget_available
            if evidence.score >= max(0.9, evidence.threshold):
                self._promo_recovery = PromoRecoveryResult(
                    status=PromoRecoveryStatus.BLOCKED,
                    trigger="pending_destination",
                    expected_page=expected_page,
                    before={**self._frame_dict(target, captured), "anchor": evidence.as_dict()},
                    error="Known promo title is ambiguous in the pending destination frame.",
                )
                self._promo_recovery.captures.append(_capture_id(captured))
                self._pending_expected_page = None
                raise SafetyError(self._promo_recovery.error)
            raise SafetyError("Current frame has no uniquely verified shop page.")

        promo = PromoRecoveryResult(
            trigger="pending_destination",
            expected_page=expected_page,
            before={**self._frame_dict(target, captured), "anchor": evidence.as_dict()},
        )
        promo.captures.append(_capture_id(captured))
        self._promo_recovery = promo
        # Reserve the shared budget before crossing the input boundary.  Any
        # uncertain keyevent is terminal and cannot be retried.
        self._promo_budget_available = False
        self._pending_expected_page = None
        if self._pending_cancelled():
            promo.status = PromoRecoveryStatus.CANCELLED
            raise _SurveyCancelled("Shop survey cancelled before pending promo Back.")
        promo.attempted = True
        try:
            self.manager.execute(
                self.index,
                "keyevent",
                values=(4,),
                snapshot=self.snapshot,
                observed_target=target,
            )
        except (OSError, RuntimeError, SafetyError) as exc:
            promo.status = PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN
            promo.error = str(exc)
            raise
        self._target = None
        promo.actions.append("keyevent:4")

        last_error: str | None = None
        for attempt in range(self._promo_observations):
            if self._pending_cancelled():
                promo.status = PromoRecoveryStatus.CANCELLED
                raise _SurveyCancelled("Shop survey cancelled while observing pending destination.")
            if attempt and self._promo_wait_seconds:
                time.sleep(self._promo_wait_seconds)
            try:
                next_target, next_captured = self._capture(
                    "phase6-shop-promo-destination",
                    allow_transport_change=True,
                )
            except (OSError, RuntimeError) as exc:
                promo.status = PromoRecoveryStatus.ACTION_RESULT_UNCERTAIN
                promo.error = str(exc)
                raise
            except SafetyError as exc:
                promo.status = PromoRecoveryStatus.IDENTITY_MISMATCH
                promo.error = str(exc)
                raise _SurveyIdentityMismatch(promo.error) from exc
            promo.captures.append(_capture_id(next_captured))
            if (next_target.serial, next_target.boot_id) != (target.serial, target.boot_id):
                promo.status = PromoRecoveryStatus.IDENTITY_MISMATCH
                promo.error = "Pending promo destination transport identity changed."
                promo.after = self._frame_dict(next_target, next_captured)
                raise _SurveyIdentityMismatch(promo.error)
            promo.after = self._frame_dict(next_target, next_captured)
            try:
                destination = self.registry.observe(next_captured)
            except SafetyError as exc:
                last_error = str(exc)
                continue
            if destination.screen.page != expected_page:
                promo.status = PromoRecoveryStatus.DESTINATION_UNVERIFIED
                promo.error = (
                    f"Expected pending page {expected_page!r}, observed {destination.screen.page!r}."
                )
                raise SafetyError(promo.error)
            promo.status = PromoRecoveryStatus.DESTINATION_SUCCESS
            promo.after = {
                **(promo.after or self._frame_dict(next_target, next_captured)),
                "page": destination.screen.page,
            }
            return destination
        promo.status = PromoRecoveryStatus.TIMEOUT
        promo.error = last_error or "Pending promo destination was not observed."
        raise SafetyError(promo.error)

    def observe(self) -> ShopFrameObservation:
        # Any new capture supersedes the previous action authority, including
        # a capture that later fails semantic page resolution.
        self._last = None
        target, captured = self._capture("phase6-shop-survey")
        if self._pending_expected_page is not None and self.pending_promo_anchor is not None:
            pending_evidence = unique_current_anchor(captured, self.pending_promo_anchor)
            if pending_evidence.matched or pending_evidence.score >= max(0.9, pending_evidence.threshold):
                try:
                    observation = self._pending_promo_destination(target, captured)
                except SafetyError:
                    if self._promo_recovery is None:
                        raise
                    raise
                self._pending_expected_page = None
                self._last = observation
                return observation
        try:
            observation = self.registry.observe(captured)
        except SafetyError as original:
            if self._pending_expected_page is None or self.pending_promo_anchor is None:
                raise
            try:
                observation = self._pending_promo_destination(target, captured)
            except SafetyError:
                if self._promo_recovery is None:
                    raise original
                raise
        self._pending_expected_page = None
        self._last = observation
        return observation

    def _current(self, observation: ShopFrameObservation) -> ShopFrameObservation:
        if self._last is None or self._last is not observation:
            raise SafetyError("Shop survey action evidence is stale; capture a fresh frame.")
        if self._target is None:
            raise SafetyError("Shop survey action has no verified transport target.")
        return observation

    def _dispatch(self, action: str, values: tuple[int, ...]) -> None:
        if self._target is None:
            raise SafetyError("Shop survey action has no verified transport target.")
        self.manager.execute(
            self.index,
            action,
            values=values,
            snapshot=self.snapshot,
            observed_target=self._target,
        )
        # A successful dispatch consumes the frame's action authority.  The
        # engine must observe again before it can dispatch anything else.
        self._last = None

    @staticmethod
    def _verified_point(observation: ShopFrameObservation, anchor_id: str, point: tuple[int, int]) -> None:
        matches = [item for item in observation.evidence.values() if item.anchor_id == anchor_id]
        if len(matches) != 1 or not _strong(matches[0]) or matches[0].device_box is None:
            raise SafetyError("Shop survey action anchor is missing or ambiguous.")
        if matches[0].device_box.center != point:
            raise SafetyError("Shop survey action point is not from the current frame.")

    def navigate(self, observation: ShopFrameObservation, route: Route, point: tuple[int, int]) -> None:
        current = self._current(observation)
        self._verified_point(current, route.anchor, point)
        self._dispatch("tap", point)

    def backtrack(self, observation: ShopFrameObservation, route: Route, point: tuple[int, int]) -> None:
        current = self._current(observation)
        self._verified_point(current, route.anchor, point)
        self._dispatch("tap", point)

    def scroll(self, observation: ShopFrameObservation, direction: str, point: tuple[int, int]) -> None:
        current = self._current(observation)
        evidence = current.evidence.get(f"scroll:{direction}")
        if not _strong(evidence) or evidence.device_box is None:
            raise SafetyError("No current-frame verified shop scroll surface.")
        box = evidence.device_box
        if box.width <= 1 or box.height <= 1:
            raise SafetyError("Shop scroll surface is unusable.")
        cx, cy = box.center
        if (cx, cy) != point:
            raise SafetyError("Shop survey scroll point is not from the current frame.")
        if direction in {"vertical", "up"}:
            values = (cx, box.y + round(box.height * 0.8), cx, box.y + round(box.height * 0.2), 300)
        elif direction == "down":
            values = (cx, box.y + round(box.height * 0.2), cx, box.y + round(box.height * 0.8), 300)
        elif direction in {"horizontal", "left"}:
            values = (box.x + round(box.width * 0.8), cy, box.x + round(box.width * 0.2), cy, 300)
        elif direction == "right":
            values = (box.x + round(box.width * 0.2), cy, box.x + round(box.width * 0.8), cy, 300)
        else:
            raise SafetyError("Unsupported shop scroll direction.")
        self._dispatch("swipe", values)


def free_pack_profile(
    anchors: dict[str, VisualAnchor],
    *,
    rewards: Iterable[RewardRule] = (),
    routes: Iterable[ShopRouteRule] = (),
    scroll_axes: Iterable[str] = (),
    scroll_directions: Iterable[str] = (),
    fingerprint_regions: Iterable[NormalizedRect] = (),
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
        scroll_directions=tuple(scroll_directions),
        fingerprint_regions=tuple(fingerprint_regions),
    )

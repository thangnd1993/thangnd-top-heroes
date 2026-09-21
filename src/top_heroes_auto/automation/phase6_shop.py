"""Bounded, current-frame shop discovery primitives for Phase 6.

The index-2 survey did not prove a zero-cost daily-shop gift.  This module is
therefore an injectable discovery adapter, not a packaged Free Pack profile:
red dots and gift-shaped controls are recorded as diagnostics only, and claims
remain disabled unless the caller supplies independent post evidence and opts
in explicitly.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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

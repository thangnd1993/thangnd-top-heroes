"""Fail-closed current-frame visual adapter primitives for Phase 6."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Iterable

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.free_rewards import (
    Cost,
    ExplorerPort,
    RewardEvidence,
    RewardScreen,
    Route,
    verified_anchor,
)
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.vision.exploration import content_fingerprint, red_dot_candidates, unique_current_anchor
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
class RewardRule:
    """Independent visual evidence for one reward candidate."""

    reward_id: str
    action_role: str = "claim"
    free_role: str | None = "free"
    available_role: str | None = "available"
    paid_role: str | None = None
    paid_cost: Cost = Cost.UNKNOWN
    diamond_reward: bool = False

    def __post_init__(self):
        if not self.reward_id.strip():
            raise ValueError("Reward ID is required.")
        if self.paid_role in {self.action_role, self.free_role, self.available_role}:
            raise ValueError("Paid evidence must be independent from action/free/availability anchors.")
        if self.paid_cost == Cost.FREE:
            raise ValueError("Paid evidence cannot have FREE cost.")


@dataclass(frozen=True)
class RewardVisualProfile:
    """Semantic roles mapped to current-frame visual anchors."""

    task: str
    page: str
    anchors: tuple[tuple[str, VisualAnchor], ...]
    rewards: tuple[RewardRule, ...]
    page_state: ScreenState = ScreenState.FREE_REWARD_PAGE

    def __post_init__(self):
        if not self.task.strip() or not self.page.strip():
            raise ValueError("Task and page are required.")
        roles = [role for role, _ in self.anchors]
        if len(roles) != len(set(roles)):
            raise ValueError("Anchor roles must be unique within a profile.")
        if "page" not in roles:
            raise ValueError("A page anchor is required.")
        known = set(roles)
        for rule in self.rewards:
            for role in (rule.action_role, rule.free_role, rule.available_role, rule.paid_role):
                if role is not None and role not in known:
                    raise ValueError(f"Reward {rule.reward_id!r} references missing role {role!r}.")

    @property
    def anchor_map(self) -> dict[str, VisualAnchor]:
        return dict(self.anchors)


Matcher = Callable[[CapturedScreen, VisualAnchor], AnchorEvidence]


@dataclass(frozen=True)
class RouteRule:
    id: str
    role: str
    destination: str
    kind: str = "tab"

    def route(self) -> Route:
        return Route(self.id, self.role, self.destination, self.kind)


@dataclass(frozen=True)
class FrameRewardObservation:
    captured: CapturedScreen
    screen: RewardScreen
    evidence: dict[str, AnchorEvidence]


def _matched(evidence: dict[str, AnchorEvidence], role: str | None) -> bool:
    return bool(role and evidence.get(role) and evidence[role].matched)


def _capture_id(screen: CapturedScreen) -> str:
    if screen.source_image:
        return str(screen.source_image)
    digest = hashlib.sha256(screen.normalized.tobytes()).hexdigest()
    return f"frame:{screen.timestamp}:{digest}"


class FrameRewardAdapter:
    """Interpret one current screenshot without reusing a prior coordinate."""

    def __init__(self, profile: RewardVisualProfile, matcher: Matcher = unique_current_anchor):
        self.profile = profile
        self.matcher = matcher

    def observe(self, captured: CapturedScreen) -> FrameRewardObservation:
        evidence = {
            role: self.matcher(captured, anchor)
            for role, anchor in self.profile.anchors
        }
        page = evidence["page"]
        page_matched = page.matched and page.device_box is not None and page.score >= max(0.9, page.threshold)
        state = self.profile.page_state if page_matched else ScreenState.UNKNOWN
        scores = [item.score for item in evidence.values() if item.matched]
        detection = ScreenDetection(
            state,
            float(min(scores) if page_matched and scores else 0.0),
            tuple(evidence.values()),
            captured.timestamp,
            captured.source_image,
            0.0,
        )
        screen = RewardScreen(
            detection=detection,
            index=captured.index,
            name=captured.name,
            adb_target=captured.serial,
            boot_id=captured.boot_id,
            capture_id=_capture_id(captured),
            page=self.profile.page,
            fingerprint=content_fingerprint(captured, (NormalizedRect(0, 0, 1, 1),)),
            rewards=tuple(self._reward(rule, evidence) for rule in self.profile.rewards),
            routes=(),
            red_dot_candidates=tuple(
                f"red-dot:{box.x},{box.y},{box.width},{box.height}"
                for box in red_dot_candidates(captured, NormalizedRect(0, 0, 1, 1))
            ),
        )
        return FrameRewardObservation(captured, screen, evidence)

    @staticmethod
    def _reward(rule: RewardRule, evidence: dict[str, AnchorEvidence]) -> RewardEvidence:
        action = evidence.get(rule.action_role)
        free = evidence.get(rule.free_role) if rule.free_role else None
        available = evidence.get(rule.available_role) if rule.available_role else None
        paid = evidence.get(rule.paid_role) if rule.paid_role else None
        if paid is not None and paid.matched:
            cost, ambiguous = rule.paid_cost, False
        elif action is not None and action.matched and _matched(evidence, rule.free_role) and _matched(evidence, rule.available_role):
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

    def verify_claim(self, before: RewardScreen, after: RewardScreen, reward: RewardEvidence) -> bool:
        """Require same identity, an independent post anchor, and no live free state."""
        if (before.index, before.name, before.adb_target, before.boot_id) != (
            after.index,
            after.name,
            after.adb_target,
            after.boot_id,
        ):
            return False
        post = self.profile.anchor_map.get("post")
        if post is None:
            return False
        try:
            verified_anchor(after.detection, post.id)
        except SafetyError:
            return False
        evidence = {item.anchor_id: item for item in after.detection.evidence}
        action = evidence.get(reward.action_anchor)
        available = evidence.get(reward.available_anchor)
        if action is not None and action.matched and available is not None and available.matched:
            return False
        return True


class ManagerRewardPort(ExplorerPort):
    """Bridge a visual profile to Manager's verified capture/input boundary."""

    def __init__(
        self,
        manager: Manager,
        snapshot: RunSnapshot,
        index: int,
        name: str,
        profile: RewardVisualProfile,
        folder=None,
        home_observer: Callable[[str, str], bool] | None = None,
    ):
        self.manager = manager
        self.snapshot = snapshot
        self.index = index
        self.name = name
        self.adapter = FrameRewardAdapter(profile)
        self.folder = folder
        self.home_observer = home_observer
        self._last: FrameRewardObservation | None = None
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
            raise SafetyError("Reward capture identity changed.")
        if self._target and (target.serial, target.boot_id) != (self._target.serial, self._target.boot_id):
            raise SafetyError("Reward capture transport identity changed.")
        self._target = target
        captured = ScreenshotService(lambda serial: payload if serial == target.serial else b"").take(
            target, self.folder, "phase6-reward"
        )
        self._last = self.adapter.observe(captured)
        return self._last.screen

    def _current(self, screen: RewardScreen):
        if self._last is None or self._last.screen is not screen:
            raise SafetyError("Action evidence is stale; capture a fresh frame.")
        return self._last

    def claim(self, screen: RewardScreen, reward: RewardEvidence, point: tuple[int, int]) -> None:
        self._current(screen)
        self._dispatch("tap", point)

    def verify_claim(self, before: RewardScreen, after: RewardScreen, reward: RewardEvidence) -> bool:
        self._current(after)
        return self.adapter.verify_claim(before, after, reward)

    def navigate(self, screen: RewardScreen, route: Route, point: tuple[int, int]) -> None:
        self._current(screen)
        self._dispatch("tap", point)

    def scroll(self, screen: RewardScreen, axis: str) -> None:
        raise SafetyError("No scroll surface was declared by this profile.")

    def return_home(self, screen: RewardScreen) -> bool:
        self._current(screen)
        if self.home_observer is None:
            raise SafetyError("A fresh GAME_HOME verifier is required before cleanup.")
        home = self.adapter.profile.anchor_map.get("home")
        if home is None:
            return False
        evidence = verified_anchor(screen.detection, home.id)
        if evidence.device_box is None:
            return False
        if self._target is None:
            raise SafetyError("No current target is available for Home cleanup.")
        expected_serial, expected_boot_id = self._target.serial, self._target.boot_id
        self._dispatch("tap", evidence.device_box.center)
        return bool(self.home_observer(expected_serial, expected_boot_id))


def profile_from_anchors(
    task: str,
    page: str,
    anchors: Iterable[tuple[str, VisualAnchor]],
    rewards: Iterable[RewardRule],
    **kwargs,
) -> RewardVisualProfile:
    return RewardVisualProfile(task, page, tuple(anchors), tuple(rewards), **kwargs)


def _named_profile(
    task: str,
    page: str,
    anchors: dict[str, VisualAnchor],
    reward_id: str,
    *,
    diamond_reward: bool,
) -> RewardVisualProfile:
    required = ("page", "claim", "free", "available", "post")
    missing = [role for role in required if role not in anchors]
    if missing:
        raise ValueError(f"Missing {task} visual roles: {', '.join(missing)}")
    return RewardVisualProfile(
        task,
        page,
        tuple((role, anchors[role]) for role in anchors),
        (RewardRule(reward_id, diamond_reward=diamond_reward),),
    )


def vip_reward_profile(anchors: dict[str, VisualAnchor]) -> RewardVisualProfile:
    """Build the VIP daily-free profile from packaged/account templates."""

    # The survey proves a free VIP opportunity, not the contents of its
    # eventual reward. Do not prioritize it as a diamond reward without a
    # separate verified reward-content anchor.
    return _named_profile("vip-reward", "vip", anchors, "vip-daily", diamond_reward=False)


def free_recruit_profile(anchors: dict[str, VisualAnchor]) -> RewardVisualProfile:
    """Build the free Recruit profile; ticket-based x10 is never this reward."""

    return _named_profile("free-recruit", "recruit", anchors, "free-recruit", diamond_reward=False)

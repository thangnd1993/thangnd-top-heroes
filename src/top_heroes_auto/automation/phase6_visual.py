"""Fail-closed current-frame visual adapter primitives for Phase 6."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable

import cv2

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.service import Manager
from top_heroes_auto.automation.free_rewards import (
    ClaimOutcome,
    Cost,
    ExplorerPort,
    RewardEvidence,
    RewardScreen,
    Route,
    verified_anchor,
)
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.overlays import OverlayBudget, dismiss_overlay_bottom_left
from top_heroes_auto.automation.vip_geometry import (
    validate_vip_claim_geometry,
    write_vip_geometry_overlay,
)
from top_heroes_auto.vision.exploration import content_fingerprint, red_dot_candidates, unique_current_anchor
from top_heroes_auto.vision.models import (
    AnchorEvidence,
    BoundingBox,
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
    forbidden_roles: tuple[str, ...] = ()
    geometry_required: bool = False
    coverage_known: bool = False

    def __post_init__(self):
        if not self.task.strip() or not self.page.strip():
            raise ValueError("Task and page are required.")
        roles = [role for role, _ in self.anchors]
        if len(roles) != len(set(roles)):
            raise ValueError("Anchor roles must be unique within a profile.")
        anchor_ids = [anchor.id for _, anchor in self.anchors]
        if len(anchor_ids) != len(set(anchor_ids)):
            raise ValueError("Anchor IDs must be unique within a profile.")
        if "page" not in roles:
            raise ValueError("A page anchor is required.")
        known = set(roles)
        if not set(self.forbidden_roles) <= known:
            raise ValueError("Forbidden roles must have current-frame visual anchors.")
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
        if profile.task == "vip-upper-gift" and matcher is unique_current_anchor:
            from top_heroes_auto.vision.gift_detector import gift_anchor_match

            matcher = gift_anchor_match
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
        vip_claimed = self._vip_claimed(evidence)
        screen = RewardScreen(
            detection=detection,
            index=captured.index,
            name=captured.name,
            adb_target=captured.serial,
            boot_id=captured.boot_id,
            capture_id=_capture_id(captured),
            page=self.profile.page,
            fingerprint=content_fingerprint(captured, (NormalizedRect(0, 0, 1, 1),)),
            rewards=() if vip_claimed else tuple(self._reward(rule, evidence) for rule in self.profile.rewards),
            routes=(),
            red_dot_candidates=tuple(
                f"red-dot:{box.x},{box.y},{box.width},{box.height}"
                for box in red_dot_candidates(captured, NormalizedRect(0, 0, 1, 1))
            ),
            coverage_known=self.profile.coverage_known,
        )
        return FrameRewardObservation(captured, screen, evidence)

    def _vip_claimed(self, evidence: dict[str, AnchorEvidence]) -> bool:
        if self.profile.task != "vip-reward":
            return False
        anchors = self.profile.anchor_map
        page = anchors.get("page")
        post = anchors.get("post")
        if page is None or post is None:
            return False
        if not self._strong_match(evidence, page.id) or not self._strong_match(evidence, post.id):
            return False
        return not any(
            self._strong_match(evidence, anchors[role].id)
            for role in ("claim", "available")
            if role in anchors
        )

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

    @staticmethod
    def _strong_match(evidence: dict[str, AnchorEvidence], anchor_id: str) -> bool:
        item = next((candidate for candidate in evidence.values() if candidate.anchor_id == anchor_id), None)
        return bool(
            item
            and item.matched
            and item.device_box is not None
            and math.isfinite(item.score)
            and math.isfinite(item.threshold)
            and item.score >= max(0.9, item.threshold)
        )

    def classify_claim(
        self, before: RewardScreen, after: RewardScreen, reward: RewardEvidence
    ) -> ClaimOutcome:
        """Classify a fresh result frame without requiring normal page detection.

        Result/cooldown anchors are matched in the current frame and must be
        independent of the live free/action controls. A generic popup or a
        disappeared button remains UNKNOWN and is never retried.
        """

        if (before.index, before.name, before.adb_target, before.boot_id) != (
            after.index,
            after.name,
            after.adb_target,
            after.boot_id,
        ):
            return ClaimOutcome.IDENTITY_MISMATCH
        evidence = {item.anchor_id: item for item in after.detection.evidence}
        claimable_anchors = (reward.action_anchor, reward.available_anchor)
        if self.profile.task != "vip-reward":
            claimable_anchors += (reward.free_anchor,)
        free_state = any(self._strong_match(evidence, anchor_id) for anchor_id in claimable_anchors)
        if free_state:
            return ClaimOutcome.UNKNOWN
        if self.profile.task == "vip-reward":
            anchors = self.profile.anchor_map
            page = anchors.get("page")
            post = anchors.get("post")
            if (
                page is not None
                and post is not None
                and after.detection.state == ScreenState.FREE_REWARD_PAGE
                and self._strong_match(evidence, page.id)
                and self._strong_match(evidence, post.id)
            ):
                return ClaimOutcome.CLAIMED
            # A result/receipt popup by itself is not proof that the daily
            # button changed state; retain RESERVED and never retry.
            return ClaimOutcome.UNKNOWN
        result_roles = ("post", "receipt", "result")
        result_matches = [
            role for role in result_roles
            if role in self.profile.anchor_map
            and self._strong_match(evidence, self.profile.anchor_map[role].id)
        ]
        cooldown = self.profile.anchor_map.get("cooldown")
        cooldown_match = bool(cooldown and self._strong_match(evidence, cooldown.id))
        if result_matches and cooldown_match:
            return ClaimOutcome.UNKNOWN
        if result_matches:
            return ClaimOutcome.CLAIMED
        if cooldown_match:
            return ClaimOutcome.COOLDOWN
        return ClaimOutcome.UNKNOWN

    def verify_claim(self, before: RewardScreen, after: RewardScreen, reward: RewardEvidence) -> bool:
        """Compatibility boolean for ports predating explicit result outcomes."""

        return self.classify_claim(before, after, reward) in {
            ClaimOutcome.CLAIMED,
        }


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
        self.entry_geometry: dict | None = None
        self.geometry_overlay_path: Path | None = None
        self.geometry_report: dict | None = None
        self._prepared_claim: tuple[str, str, tuple[int, int]] | None = None
        self.overlay_events: list[dict] = []
        self._overlay_budget = OverlayBudget(max_total=4, max_same=2)
        self._dismissed_captures: set[str] = set()

    def set_entry_geometry(self, geometry: dict | None) -> None:
        self.entry_geometry = geometry

    def _dispatch(self, action: str, values: tuple[int, ...], *, before_input=None):
        if self._target is None:
            raise SafetyError("No current screenshot target is available.")
        journal_hook = {"before_input": before_input} if before_input is not None else {}
        return self.manager.execute(
            self.index,
            action,
            values=values,
            snapshot=self.snapshot,
            observed_target=self._target,
            **journal_hook,
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

    def dismiss_receipts(self, screen: RewardScreen, *, sleep=time.sleep) -> RewardScreen:
        """Only receipt overlays after a claim; never infer success from a popup."""
        from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector

        detector = RecoveryScreenDetector()
        for attempt in range(5):
            current = self._current(screen)
            detection = detector.detect(current.captured)
            if detection.state == ScreenState.REWARD_RECEIPT:
                point = dismiss_overlay_bottom_left(current.captured, detection)
                if screen.capture_id in self._dismissed_captures:
                    raise SafetyError("Cannot reuse a dismissed overlay frame.")
                self._overlay_budget.reserve(detection)
                self._dismissed_captures.add(screen.capture_id)
                event = dict(before=screen.capture_id, detection=detection.as_dict(),
                             tap_point_adb=list(point), dispatched="POSSIBLE")
                self.overlay_events.append(event)
                self._save_overlay_events()
                self._dispatch("tap", point)
                event["dispatched"] = True
                sleep(.5)
                screen = self.observe()
                event["after"] = screen.capture_id
                following = detector.detect(self._current(screen).captured)
                event["after_detection"] = following.as_dict()
                event["underlying_page_verified"] = screen.detection.state == ScreenState.FREE_REWARD_PAGE
                event["same_receipt_detected"] = following.state == ScreenState.REWARD_RECEIPT
                self._save_overlay_events()
                continue
            if screen.detection.state == ScreenState.FREE_REWARD_PAGE:
                return screen
            if attempt < 2 and not self.overlay_events:
                # An immediate reward animation may not yet show the continue text.
                # Observation only; no generic UNKNOWN dismiss.
                sleep(.5)
                screen = self.observe()
                continue
            return screen
        return screen

    def _save_overlay_events(self):
        if self.folder is not None:
            (Path(self.folder) / "overlay-dismissals.json").write_text(
                json.dumps(self.overlay_events, ensure_ascii=False, indent=2), encoding="utf-8")

    def validate_claim(self, screen: RewardScreen, reward: RewardEvidence, point: tuple[int, int]) -> None:
        current = self._current(screen)
        if not self.adapter.profile.geometry_required:
            self._prepared_claim = (screen.capture_id, reward.reward_id, point)
            return
        profile = self.adapter.profile
        if not self.entry_geometry or not self.entry_geometry.get("normalized_image"):
            raise SafetyError("VIP entry geometry is unavailable; claim is blocked.")
        target_matches = [item for item in current.evidence.values()
                          if item.anchor_id == reward.action_anchor and item.matched]
        if len(target_matches) != 1 or target_matches[0].device_box is None:
            raise SafetyError("VIP free claim bbox is missing or ambiguous.")
        target = target_matches[0]
        if point != target.device_box.center:
            raise SafetyError("VIP ADB tap point differs from the current claim bbox center.")
        forbidden = []
        for role in profile.forbidden_roles:
            matches = [current.evidence[role]] if current.evidence.get(role) and current.evidence[role].matched else []
            if len(matches) != 1 or matches[0].device_box is None:
                raise SafetyError(f"VIP forbidden-region evidence {role!r} is missing or ambiguous.")
            forbidden.append(matches[0])
        geometry = validate_vip_claim_geometry(
            target.device_box,
            point,
            tuple(item.device_box for item in forbidden if item.device_box is not None),
        )
        entry_path = Path(self.entry_geometry["normalized_image"])
        home_image = cv2.imread(str(entry_path))
        if home_image is None or target.normalized_box is None:
            raise SafetyError("VIP geometry screenshots could not be decoded.")
        normalized_tap = target.normalized_box.center
        self.geometry_overlay_path = write_vip_geometry_overlay(
            home_image,
            current.captured.normalized,
            BoundingBox(**self.entry_geometry["normalized_bbox"]),
            target.normalized_box,
            normalized_tap,
            geometry.tap_point,
            tuple(item.normalized_box for item in forbidden if item.normalized_box is not None),
            Path(self.folder) / "vip-geometry-overlay.png",
        )
        self.geometry_report = {
            "entry_bbox": self.entry_geometry["normalized_bbox"],
            "entry_bbox_device": self.entry_geometry["device_bbox"],
            "entry_confidence": self.entry_geometry["confidence"],
            "claim_bbox": vars(target.device_box),
            "claim_confidence": round(target.score, 6),
            "tap_point_adb": list(geometry.tap_point),
            "tap_point_inside_allowed_bbox": True,
            "paid_region_bboxes": [vars(item.device_box) for item in forbidden],
            "tap_point_outside_paid_region": True,
            "claim_bbox_disjoint_from_paid_region": True,
            "overlay": str(self.geometry_overlay_path),
        }
        self._prepared_claim = (screen.capture_id, reward.reward_id, point)

    def claim(self, screen: RewardScreen, reward: RewardEvidence, point: tuple[int, int], *, before_input=None) -> None:
        self._current(screen)
        if self.adapter.profile.geometry_required and self._prepared_claim != (
            screen.capture_id,
            reward.reward_id,
            point,
        ):
            raise SafetyError("VIP claim geometry was not validated from this fresh frame.")
        self._prepared_claim = None
        self._dispatch("tap", point, before_input=before_input)

    def verify_claim(self, before: RewardScreen, after: RewardScreen, reward: RewardEvidence) -> bool:
        self._current(after)
        return self.adapter.verify_claim(before, after, reward)

    def classify_claim(
        self, before: RewardScreen, after: RewardScreen, reward: RewardEvidence
    ) -> ClaimOutcome:
        self._current(after)
        return self.adapter.classify_claim(before, after, reward)

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
    profile = _named_profile("vip-reward", "vip", anchors, "vip-daily", diamond_reward=False)
    return replace(
        profile,
        forbidden_roles=("paid",),
        geometry_required=True,
        coverage_known=True,
    )


def free_recruit_profile(anchors: dict[str, VisualAnchor]) -> RewardVisualProfile:
    """Build the free Recruit profile; ticket-based x10 is never this reward."""

    return _named_profile("free-recruit", "recruit", anchors, "free-recruit", diamond_reward=False)

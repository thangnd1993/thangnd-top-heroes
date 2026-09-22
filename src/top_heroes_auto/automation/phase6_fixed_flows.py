"""Versioned product intent for the three fixed Phase 6 daily flows.

This module deliberately contains semantic roles rather than coordinates.  A
runtime adapter must rediscover every role from the current account frame.
The user-supplied annotated screenshots describe intent only; they are never
loaded as templates and never prove that a reward is free.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

MANIFEST_VERSION = "phase6-fixed-flows-v1"


class CandidateDecision(StrEnum):
    READY = "READY"
    UNKNOWN = "UNKNOWN"
    FORBIDDEN = "FORBIDDEN"


@dataclass(frozen=True)
class FlowQualification:
    clean_current_account_anchors: bool = False
    zero_cost_proof: bool = False
    availability_proof: bool = False
    postcondition_proof: bool = False

    @property
    def activation_ready(self) -> bool:
        return all(
            (
                self.clean_current_account_anchors,
                self.zero_cost_proof,
                self.availability_proof,
                self.postcondition_proof,
            )
        )


@dataclass(frozen=True)
class FixedFlowSpec:
    id: str
    task: str | None
    route_roles: tuple[str, ...]
    page_role: str
    action_role: str
    free_role: str
    available_role: str
    post_role: str
    forbidden_roles: frozenset[str]
    discovery_roles: frozenset[str]
    qualification: FlowQualification = FlowQualification()

    def __post_init__(self):
        required = {
            self.page_role,
            self.action_role,
            self.free_role,
            self.available_role,
            self.post_role,
        }
        if not self.id or not self.route_roles or any(not role for role in required):
            raise ValueError("A fixed flow requires non-empty semantic roles.")
        if required & self.forbidden_roles:
            raise ValueError("A required role cannot also be forbidden.")

    @property
    def claim_roles(self) -> frozenset[str]:
        return frozenset(
            (self.page_role, self.action_role, self.free_role, self.available_role)
        )

    def decide(self, matched_roles: set[str] | frozenset[str]) -> CandidateDecision:
        """Classify one fresh frame; forbidden evidence always wins."""

        matched = frozenset(matched_roles)
        if matched & self.forbidden_roles:
            return CandidateDecision.FORBIDDEN
        if not self.qualification.activation_ready:
            return CandidateDecision.UNKNOWN
        if not self.claim_roles <= matched:
            return CandidateDecision.UNKNOWN
        return CandidateDecision.READY


VIP_DAILY = FixedFlowSpec(
    id="vip-daily",
    task="vip-reward",
    route_roles=("home-vip-entry", "vip-page"),
    page_role="vip-page",
    action_role="vip-daily-claim",
    free_role="vip-daily-free-label",
    available_role="vip-daily-available",
    post_role="vip-daily-postcondition",
    forbidden_roles=frozenset(("vip-paid-upgrade", "vip-attention-gift-unqualified")),
    discovery_roles=frozenset(("home-vip-attention", "vip-attention-dot")),
    qualification=FlowQualification(clean_current_account_anchors=True),
)


SHOP_DAILY = FixedFlowSpec(
    id="shop-daily-gift",
    task="free-pack",
    route_roles=("home-shop-entry", "shop-daily-offer-tab", "shop-daily-gift"),
    page_role="shop-daily-offer-page",
    action_role="shop-daily-gift",
    free_role="shop-daily-gift-free-label",
    available_role="shop-daily-gift-available",
    post_role="shop-daily-gift-postcondition",
    forbidden_roles=frozenset(
        (
            "shop-paid-offer",
            "shop-daily-pack-tab",
            "shop-weekly-pack-tab",
            "shop-construction-fund-tab",
            "shop-diamond-store-tab",
        )
    ),
    discovery_roles=frozenset(
        (
            "shop-attention-dot",
            "shop-weekly-card-tab",
            "shop-month-card-tab",
            "shop-persistent-card-tab",
        )
    ),
)


RANKING_CHEST = FixedFlowSpec(
    id="ranking-daily-chest",
    task=None,
    route_roles=("home-avatar-entry", "profile-ranking-tab", "ranking-page"),
    page_role="ranking-page",
    action_role="ranking-top-left-chest",
    free_role="ranking-chest-free-proof",
    available_role="ranking-chest-available",
    post_role="ranking-chest-postcondition",
    forbidden_roles=frozenset(("ranking-row", "profile-badge", "profile-settings")),
    discovery_roles=frozenset(("home-avatar-attention", "ranking-chest-attention")),
)


FIXED_FLOWS = (VIP_DAILY, SHOP_DAILY, RANKING_CHEST)


def fixed_flow_for_task(task: str) -> FixedFlowSpec | None:
    return next((flow for flow in FIXED_FLOWS if flow.task == task), None)


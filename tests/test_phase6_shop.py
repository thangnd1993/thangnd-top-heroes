from pathlib import Path

import numpy as np

from top_heroes_auto.automation.free_rewards import Cost
from top_heroes_auto.automation.phase6_shop import (
    FrameShopAdapter,
    ShopRouteRule,
    ShopVisualProfile,
    free_pack_profile,
)
from top_heroes_auto.automation.phase6_visual import RewardRule
from top_heroes_auto.vision.models import (
    AnchorEvidence,
    BoundingBox,
    CapturedScreen,
    NormalizedRect,
    ScreenState,
    VisualAnchor,
)


def _anchor(role):
    return VisualAnchor(
        f"{role}-anchor",
        ScreenState.FREE_REWARD_PAGE,
        Path(f"{role}.png"),
        NormalizedRect(0, 0, 1, 1),
        0.9,
    )


def _frame(stamp):
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    return CapturedScreen(
        2,
        "5-Emmmmm",
        "emulator-5558",
        "boot",
        image,
        image,
        (240, 120),
        (240, 120),
        (1, 1),
        timestamp=stamp,
    )


def _adapter(present_by_stamp, *, coverage_known=False):
    roles = (
        "page",
        "weekly",
        "scroll:vertical",
        "scroll:horizontal",
        "claim",
        "free",
        "available",
        "paid",
    )
    anchors = {role: _anchor(role) for role in roles}
    profile = free_pack_profile(
        anchors,
        rewards=(RewardRule("daily-gift", paid_role="paid", paid_cost=Cost.DIAMONDS),),
        routes=(ShopRouteRule("weekly", "weekly", "shop", "tab"),),
        scroll_axes=("vertical", "horizontal"),
        coverage_known=coverage_known,
    )

    def matcher(frame, anchor):
        present = present_by_stamp[frame.timestamp]
        matched = anchor.id.removesuffix("-anchor") in present
        offset = 10 if frame.timestamp == "first" else 90
        box = BoundingBox(offset, 10, 20, 20) if matched else None
        return AnchorEvidence(anchor.id, anchor.state, 0.99 if matched else 0.0, 0.9, matched, box, box)

    return FrameShopAdapter(profile, matcher)


def test_shop_adapter_exposes_only_current_frame_routes_and_scroll_surfaces():
    adapter = _adapter({
        "first": {"page", "weekly", "scroll:vertical", "scroll:horizontal"},
        "moved": {"page", "weekly", "scroll:vertical"},
    })
    first = adapter.observe(_frame("first")).screen
    moved = adapter.observe(_frame("moved")).screen
    assert first.detection.state == ScreenState.FREE_REWARD_PAGE
    assert [route.id for route in first.routes] == ["weekly"]
    assert first.scroll_axes == ("vertical", "horizontal")
    assert [route.anchor for route in moved.routes] == ["weekly-anchor"]
    assert moved.scroll_axes == ("vertical",)
    first_point = first.detection.evidence[1].device_box.center
    moved_point = moved.detection.evidence[1].device_box.center
    assert first_point != moved_point


def test_shop_gift_without_free_evidence_is_unknown_and_paid_wins():
    adapter = _adapter({
        "paid": {"page", "claim", "free", "available", "paid"},
    })
    observed = adapter.observe(_frame("paid")).screen
    reward = observed.rewards[0]
    assert reward.cost == Cost.DIAMONDS
    assert not reward.ambiguous

    adapter = _adapter({"ambiguous": {"page", "claim"}})
    unknown = adapter.observe(_frame("ambiguous")).screen.rewards[0]
    assert unknown.cost == Cost.UNKNOWN
    assert unknown.ambiguous


def test_free_pack_profile_is_discovery_only_until_explicit_claim_enablement():
    adapter = _adapter({"free": {"page", "claim", "free", "available"}})
    assert adapter.profile.claim_enabled is False
    assert "post" not in adapter.profile.anchor_map


def test_enabling_shop_claim_requires_a_post_anchor():
    anchors = {"page": _anchor("page")}
    try:
        ShopVisualProfile("free-pack", "shop", tuple(anchors.items()), claim_enabled=True)
    except ValueError as exc:
        assert "post anchor" in str(exc)
    else:
        raise AssertionError("claim-enabled shop profile must require post evidence")


def test_shop_coverage_is_unknown_when_declared_route_or_scroll_is_missing():
    missing_tab = _adapter(
        {"missing-tab": {"page", "scroll:vertical", "scroll:horizontal"}},
        coverage_known=True,
    ).observe(_frame("missing-tab")).screen
    assert missing_tab.coverage_known is False

    missing_scroll = _adapter(
        {"missing-scroll": {"page", "weekly", "scroll:vertical"}},
        coverage_known=True,
    ).observe(_frame("missing-scroll")).screen
    assert missing_scroll.coverage_known is False

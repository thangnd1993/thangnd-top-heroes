from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from top_heroes_auto.automation.free_rewards import Cost, RewardEvidence, RewardScreen, Route
from top_heroes_auto.automation.phase6_shop import (
    FrameShopAdapter,
    ShopFrameObservation,
    ShopRouteRule,
    ShopSurveyEngine,
    ShopSurveyLimits,
    ShopSurveyStatus,
    ShopVisualProfile,
)
from top_heroes_auto.vision.models import (
    AnchorEvidence,
    BoundingBox,
    CapturedScreen,
    NormalizedRect,
    ScreenDetection,
    ScreenState,
    VisualAnchor,
)

IDENTITY = (2, "5-Emmmmm", "emulator-5558", "boot-2")


def _observation(
    stamp,
    page,
    *,
    routes=(),
    axes=(),
    fingerprint=None,
    coverage=True,
    identity=IDENTITY,
    red_dots=(),
    rewards=(),
    missing_evidence=(),
    state=ScreenState.FREE_REWARD_PAGE,
):
    image = np.zeros((120, 240, 3), dtype=np.uint8)
    captured = CapturedScreen(
        identity[0],
        identity[1],
        identity[2],
        identity[3],
        image,
        image,
        (240, 120),
        (240, 120),
        (1, 1),
        timestamp=stamp,
    )
    evidence = {}
    for number, route in enumerate(routes):
        if route.anchor in missing_evidence:
            continue
        box = BoundingBox(10 + number * 20, 10, 16, 16)
        evidence[route.anchor] = AnchorEvidence(
            route.anchor,
            ScreenState.FREE_REWARD_PAGE,
            0.99,
            0.9,
            True,
            box,
            box,
        )
    for number, axis in enumerate(axes):
        box = BoundingBox(10 + number * 20, 70, 120, 30)
        evidence[f"scroll:{axis}"] = AnchorEvidence(
            f"scroll:{axis}",
            ScreenState.FREE_REWARD_PAGE,
            0.99,
            0.9,
            True,
            box,
            box,
        )
    detection = ScreenDetection(
        state,
        0.99 if state != ScreenState.UNKNOWN else 0.2,
        tuple(evidence.values()),
        stamp,
        None,
        0.1,
    )
    screen = RewardScreen(
        detection,
        identity[0],
        identity[1],
        identity[2],
        identity[3],
        f"capture:{stamp}",
        page,
        fingerprint or stamp,
        rewards=tuple(rewards),
        routes=tuple(routes),
        scroll_axes=tuple(axes),
        red_dot_candidates=tuple(red_dots),
        coverage_known=coverage,
    )
    return ShopFrameObservation(captured, screen, evidence)


class SurveyPort:
    """Synthetic observation/navigation boundary; deliberately no claim API."""

    def __init__(self, *frames):
        self.frames = iter(frames)
        self.actions = []

    def observe(self):
        return next(self.frames)

    def navigate(self, observation, route, point):
        self.actions.append(("navigate", route.id, observation.screen.capture_id, point))

    def scroll(self, observation, axis, point):
        self.actions.append(("scroll", axis, observation.screen.capture_id, point))

    def backtrack(self, observation, route, point):
        self.actions.append(("backtrack", route.id, observation.screen.capture_id, point))


def test_nested_siblings_backtrack_without_claim_or_journal():
    to_a = Route("to-a", "to-a-anchor", "child-a", "tab")
    to_b = Route("to-b", "to-b-anchor", "child-b", "tab")
    back_a = Route("back-a", "back-a-anchor", "root", "parent")
    back_b = Route("back-b", "back-b-anchor", "root", "parent")
    port = SurveyPort(
        _observation("root-1", "root", routes=(to_a, to_b)),
        _observation("child-a", "child-a", routes=(back_a,)),
        _observation("root-2", "root", routes=(to_b,)),
        _observation("child-b", "child-b", routes=(back_b,)),
        _observation("root-3", "root"),
    )

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.COMPLETE
    assert result.coverage_complete is True
    assert [action[0:2] for action in port.actions] == [
        ("navigate", "to-a"),
        ("backtrack", "back-a"),
        ("navigate", "to-b"),
        ("backtrack", "back-b"),
    ]
    assert result.claims == []
    assert result.journal_rows == 0
    assert result.as_dict()["claims"] == []


def test_red_dot_and_ambiguous_gift_are_reported_but_never_routes():
    reward = RewardEvidence("daily-gift", "gift-anchor", "free-anchor", "available-anchor", Cost.UNKNOWN, True)
    port = SurveyPort(
        _observation(
            "daily",
            "daily-shop",
            red_dots=("red-dot:10,10,12,12",),
            rewards=(reward,),
        )
    )

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.COMPLETE
    assert result.actions == []
    assert result.claims == []
    assert result.journal_rows == 0
    assert result.visited[0]["red_dot_candidates"] == ["red-dot:10,10,12,12"]
    assert result.visited[0]["rewards"] == [
        {
            "reward_id": "daily-gift",
            "cost": "UNKNOWN",
            "ambiguous": True,
            "diamond_reward": False,
            "action_anchor": "gift-anchor",
            "free_anchor": "free-anchor",
            "available_anchor": "available-anchor",
        }
    ]


@pytest.mark.parametrize(
    ("coverage", "reason"),
    [(False, "coverage_unknown_or_dynamic")],
)
def test_missing_or_dynamic_coverage_is_partial(coverage, reason):
    port = SurveyPort(_observation("dynamic", "daily-shop", coverage=coverage))

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.PARTIAL
    assert result.coverage_complete is False
    assert reason in result.partial_reasons
    assert result.actions == []


def test_missing_current_route_anchor_blocks_without_dispatch():
    route = Route("weekly", "weekly-anchor", "weekly", "tab")
    port = SurveyPort(_observation("root", "root", routes=(route,), missing_evidence=(route.anchor,)))

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.SAFETY_BLOCKED
    assert not port.actions
    assert result.claims == []


def test_destination_page_mismatch_is_partial_and_never_retried():
    route = Route("weekly", "weekly-anchor", "weekly", "tab")
    port = SurveyPort(
        _observation("root", "root", routes=(route,)),
        _observation("wrong", "different-page"),
    )

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.PARTIAL
    assert "destination_unverified:weekly" in result.partial_reasons
    assert [action[0:2] for action in port.actions] == [("navigate", "weekly")]


def test_disappearing_unvisited_sibling_is_partial_after_backtrack():
    to_a = Route("to-a", "to-a-anchor", "child-a", "tab")
    to_b = Route("to-b", "to-b-anchor", "child-b", "tab")
    back_a = Route("back-a", "back-a-anchor", "root", "parent")
    port = SurveyPort(
        _observation("root-1", "root", routes=(to_a, to_b)),
        _observation("child-a", "child-a", routes=(back_a,)),
        _observation("root-2", "root", routes=(to_a,)),
    )

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.PARTIAL
    assert "missing_route_after_backtrack:to-b" in result.partial_reasons
    assert [action[0:2] for action in port.actions] == [
        ("navigate", "to-a"),
        ("backtrack", "back-a"),
    ]


def test_invalid_parent_destination_blocks_backtrack_dispatch():
    to_a = Route("to-a", "to-a-anchor", "child-a", "tab")
    bad_parent = Route("back-a", "back-a-anchor", "not-root", "parent")
    port = SurveyPort(
        _observation("root", "root", routes=(to_a,)),
        _observation("child", "child-a", routes=(bad_parent,)),
    )

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.PARTIAL
    assert "invalid_backtrack_destination:back-a" in result.partial_reasons
    assert [action[0:2] for action in port.actions] == [("navigate", "to-a")]


def test_scroll_no_progress_is_partial_and_stops_that_axis():
    port = SurveyPort(
        _observation("top", "daily-shop", axes=("vertical",), fingerprint="same"),
        _observation("repeat", "daily-shop", axes=("vertical",), fingerprint="same"),
    )

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.PARTIAL
    assert "no_progress:daily-shop:vertical" in result.partial_reasons
    assert "directional_scroll_coverage_unproven:daily-shop" in result.partial_reasons
    assert [action[0:2] for action in port.actions] == [("scroll", "vertical")]


def test_scroll_bound_is_partial_even_when_content_keeps_changing():
    port = SurveyPort(
        _observation("top", "daily-shop", axes=("vertical",), fingerprint="p0"),
        _observation("middle", "daily-shop", axes=("vertical",), fingerprint="p1"),
        _observation("bottom", "daily-shop", axes=("vertical",), fingerprint="p2"),
    )

    result = ShopSurveyEngine(ShopSurveyLimits(max_scrolls_per_axis=1)).run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.PARTIAL
    assert "scroll_bound:daily-shop:vertical" in result.partial_reasons
    assert "directional_scroll_coverage_unproven:daily-shop" in result.partial_reasons
    assert [action[0:2] for action in port.actions] == [("scroll", "vertical")]


def test_frame_shop_adapter_route_anchor_is_resolved_by_unique_anchor_id():
    page = VisualAnchor(
        "page-anchor",
        ScreenState.FREE_REWARD_PAGE,
        Path("page.png"),
        NormalizedRect(0, 0, 1, 1),
        0.9,
    )
    weekly = VisualAnchor(
        "weekly-anchor",
        ScreenState.FREE_REWARD_PAGE,
        Path("weekly.png"),
        NormalizedRect(0, 0, 1, 1),
        0.9,
    )
    profile = ShopVisualProfile(
        "free-pack",
        "shop",
        (("page", page), ("weekly", weekly)),
        routes=(ShopRouteRule("weekly", "weekly", "shop", "tab"),),
        coverage_known=True,
    )

    def matcher(frame, anchor):
        matched = anchor.id == "page-anchor" or (
            frame.timestamp == "adapter-root" and anchor.id == "weekly-anchor"
        )
        box = BoundingBox(30, 20, 10, 10) if matched else None
        return AnchorEvidence(anchor.id, anchor.state, 0.99 if matched else 0, 0.9, matched, box, box)

    adapter = FrameShopAdapter(profile, matcher)
    captures = iter(
        [
            _observation("adapter-root", "unused").captured,
            _observation("adapter-child", "unused").captured,
        ]
    )

    class AdapterPort(SurveyPort):
        def observe(self):
            return adapter.observe(next(captures))

    port = AdapterPort()
    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.PARTIAL
    assert result.actions == ["tab:weekly"]
    assert port.actions[0][3] == (35, 25)


def test_cancellation_after_observation_does_not_dispatch_another_action():
    route = Route("weekly", "weekly-anchor", "weekly", "tab")
    cancelled = False

    class CancellingPort(SurveyPort):
        def navigate(self, observation, route, point):
            nonlocal cancelled
            super().navigate(observation, route, point)
            cancelled = True

    port = CancellingPort(
        _observation("root", "root", routes=(route,)),
        _observation("weekly", "weekly"),
    )
    result = ShopSurveyEngine().run(port, *IDENTITY[:2], cancelled=lambda: cancelled)

    assert result.status == ShopSurveyStatus.CANCELLED
    assert [action[0:2] for action in port.actions] == [("navigate", "weekly")]
    assert result.claims == []


def test_serial_or_boot_change_fails_closed_before_follow_up_action():
    to_a = Route("to-a", "to-a-anchor", "child-a", "tab")
    back = Route("back", "back-anchor", "root", "parent")
    changed = replace(
        _observation("child", "child-a", routes=(back,)),
        captured=replace(_observation("unused", "unused").captured, boot_id="boot-new"),
    )
    # Keep the screen's identity aligned with its captured frame so the
    # engine reaches the explicit continuity check against the initial boot.
    changed_screen = replace(changed.screen, boot_id="boot-new", adb_target="emulator-5558")
    changed = replace(changed, screen=changed_screen)
    port = SurveyPort(
        _observation("root", "root", routes=(to_a,)),
        changed,
    )

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.IDENTITY_MISMATCH
    assert [action[0:2] for action in port.actions] == [("navigate", "to-a")]
    assert result.claims == []


def test_unknown_frame_is_reported_without_any_action():
    port = SurveyPort(_observation("unknown", "daily-shop", state=ScreenState.UNKNOWN))

    result = ShopSurveyEngine().run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.UNKNOWN_SCREEN
    assert result.actions == []
    assert result.journal_rows == 0

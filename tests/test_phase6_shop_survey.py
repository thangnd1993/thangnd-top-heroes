from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

import top_heroes_auto.app.phase6_runtime as phase6_runtime
from top_heroes_auto.app.phase6_runtime import shop_survey_registry
from top_heroes_auto.automation.free_rewards import Cost, RewardEvidence, RewardScreen, Route
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.phase6_shop import (
    FrameShopAdapter,
    ManagerShopSurveyPort,
    ShopFrameObservation,
    ShopProfileRegistry,
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


def test_production_shop_survey_factory_uses_60_second_deadline(monkeypatch):
    seen = {}

    class Engine:
        def __init__(self, limits):
            seen["limits"] = limits

        def run(self, *args):
            return "survey-result"

    monkeypatch.setattr(phase6_runtime, "ShopSurveyEngine", Engine)
    result = phase6_runtime.shop_survey_factory(
        object(),
        None,
        *IDENTITY[:2],
        None,
    )

    assert result == "survey-result"
    assert seen["limits"].max_seconds == 60.0
    assert seen["limits"].max_steps == 12
    assert seen["limits"].max_depth == 2
    assert seen["limits"].max_scrolls_per_direction == 1


def _observation(
    stamp,
    page,
    *,
    routes=(),
    axes=(),
    directions=(),
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
    for number, direction in enumerate(directions):
        box = BoundingBox(10 + number * 20, 70, 120, 30)
        evidence[f"scroll:{direction}"] = AnchorEvidence(
            f"scroll:{direction}",
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
        scroll_directions=tuple(directions),
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


def test_time_boundary_blocks_next_dispatch_and_remains_claim_free():
    to_a = Route("to-a", "to-a-anchor", "child-a", "tab")
    to_b = Route("to-b", "to-b-anchor", "child-b", "tab")

    class BoundaryClock:
        def __init__(self):
            self.values = iter((0.0, 1.0, 59.0, 60.0))

        def __call__(self):
            return next(self.values)

    port = SurveyPort(_observation("root", "root", routes=(to_a, to_b)))
    result = ShopSurveyEngine(
        ShopSurveyLimits(max_steps=12, max_depth=2, max_seconds=60.0),
        clock=BoundaryClock(),
    ).run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.TIMEOUT
    assert result.coverage_complete is False
    assert [action[0:2] for action in port.actions] == [("navigate", "to-a")]
    assert result.claims == []
    assert result.journal_rows == 0


def test_profile_registry_requires_one_current_page_match():
    page = VisualAnchor(
        "qualified-page",
        ScreenState.FREE_REWARD_PAGE,
        Path("page.png"),
        NormalizedRect(0, 0, 1, 1),
        0.9,
    )
    profile = ShopVisualProfile("survey", "daily", (("page", page),))

    def matcher(frame, anchor):
        matched = frame.timestamp == "daily" and anchor.id == "qualified-page"
        box = BoundingBox(20, 20, 12, 12) if matched else None
        return AnchorEvidence(anchor.id, anchor.state, 0.99 if matched else 0, 0.9, matched, box, box)

    registry = ShopProfileRegistry((profile,), matcher)
    assert registry.observe(_observation("daily", "unused").captured).screen.page == "daily"
    with pytest.raises(SafetyError, match="no uniquely verified"):
        registry.observe(_observation("other", "unused").captured)


def test_profile_registry_rejects_duplicate_page_names():
    anchor = VisualAnchor(
        "page",
        ScreenState.FREE_REWARD_PAGE,
        Path("page.png"),
        NormalizedRect(0, 0, 1, 1),
        0.9,
    )
    with pytest.raises(ValueError, match="page names"):
        ShopProfileRegistry(
            (ShopVisualProfile("survey", "same", (("page", anchor),)),
             ShopVisualProfile("survey", "same", (("page", anchor),))),
        )


def test_manager_shop_survey_port_consumes_frame_and_maps_directional_swipe(monkeypatch, tmp_path):
    page = VisualAnchor(
        "qualified-page",
        ScreenState.FREE_REWARD_PAGE,
        Path("page.png"),
        NormalizedRect(0, 0, 1, 1),
        0.9,
    )
    surface = VisualAnchor(
        "scroll-up",
        ScreenState.FREE_REWARD_PAGE,
        Path("scroll.png"),
        NormalizedRect(0, 0, 1, 1),
        0.9,
    )
    profile = ShopVisualProfile(
        "survey",
        "daily",
        (("page", page), ("scroll:up", surface)),
        scroll_directions=("up",),
    )

    def matcher(frame, anchor):
        matched = anchor.id in {"qualified-page", "scroll-up"}
        box = BoundingBox(20, 20, 100, 40) if matched else None
        return AnchorEvidence(anchor.id, anchor.state, 0.99, 0.9, matched, box, box)

    class ManagerStub:
        def __init__(self):
            self.actions = []

        def capture_verified(self, index, snapshot):
            return Target(index, "5-Emmmmm", "emulator-5558", "boot-2"), b"ignored"

        def execute(self, index, action, **kwargs):
            self.actions.append((index, action, kwargs))

    from top_heroes_auto.adb.client import Target
    from top_heroes_auto.vision.screenshot import ScreenshotService

    captured = _observation("frame", "unused", directions=("up",)).captured
    monkeypatch.setattr(ScreenshotService, "take", lambda *args, **kwargs: captured)
    manager = ManagerStub()
    port = ManagerShopSurveyPort(
        manager,
        RunSnapshot("ns", ((2, "5-Emmmmm"),), True),
        2,
        "5-Emmmmm",
        ShopProfileRegistry((profile,), matcher),
        tmp_path,
    )
    observation = port.observe()
    port.scroll(observation, "up", (70, 40))
    assert manager.actions[0][1] == "swipe"
    assert manager.actions[0][2]["observed_target"].boot_id == "boot-2"
    assert manager.actions[0][2]["values"] == (70, 52, 70, 28, 300)
    with pytest.raises(SafetyError, match="stale"):
        port.scroll(observation, "up", (70, 40))


def test_lateral_tabs_replace_context_and_retain_sibling_obligations():
    tabs = tuple(
        Route(f"tab-{letter}", f"anchor-{letter}", f"tab-{letter}", "tab")
        for letter in ("a", "b", "c")
    )
    frames = [_observation("root-1", "root", routes=tabs)]
    for number, letter in enumerate(("a", "b", "c"), start=2):
        frames.extend(
            (
                _observation(f"tab-{letter}", f"tab-{letter}", routes=(Route(f"back-{letter}", f"back-{letter}", "root", "parent"),)),
                _observation(f"root-{number}", "root", routes=tabs[number - 2 :]),
            )
        )
    frames.append(_observation("root-final", "root"))
    port = SurveyPort(*frames)

    result = ShopSurveyEngine(ShopSurveyLimits(max_depth=0)).run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.COMPLETE
    assert [action[0:2] for action in port.actions] == [
        ("navigate", "tab-a"),
        ("backtrack", "back-a"),
        ("navigate", "tab-b"),
        ("backtrack", "back-b"),
        ("navigate", "tab-c"),
        ("backtrack", "back-c"),
    ]


def test_packaged_registry_route_is_partial_and_claim_free():
    packaged = shop_survey_registry()
    wanted = {
        "home-1": {"home-bottom-navigation", "home-shop-entry"},
        "daily-1": {"phase6-daily-page", "phase6-daily-info-button", "phase6-daily-exit"},
        "popup": {"phase6-daily-info-popup", "phase6-daily-info-close"},
        "daily-2": {"phase6-daily-page", "phase6-daily-exit"},
        "home-2": {"home-bottom-navigation"},
    }

    def matcher(frame, anchor):
        matched = anchor.id in wanted[frame.timestamp]
        box = BoundingBox(20, 20, 16, 16) if matched else None
        return AnchorEvidence(anchor.id, anchor.state, 0.99 if matched else 0.0, 0.9, matched, box, box)

    registry = ShopProfileRegistry(packaged.profiles, matcher)

    class Port:
        def __init__(self):
            self.frames = iter(
                _observation(stamp, "unused").captured
                for stamp in ("home-1", "daily-1", "popup", "daily-2", "home-2")
            )
            self.actions = []

        def observe(self):
            return registry.observe(next(self.frames))

        def navigate(self, observation, route, point):
            self.actions.append(("navigate", route.id, point))

        def backtrack(self, observation, route, point):
            self.actions.append(("backtrack", route.id, point))

        def scroll(self, observation, direction, point):
            self.actions.append(("scroll", direction, point))

    class Run12Clock:
        def __init__(self):
            self.now = 0.0

        def __call__(self):
            value = self.now
            self.now += 4.0
            return value

    port = Port()
    clock = Run12Clock()
    result = ShopSurveyEngine(clock=clock).run(port, *IDENTITY[:2])

    assert result.status == ShopSurveyStatus.PARTIAL
    assert result.coverage_complete is False
    assert [item[0:2] for item in port.actions] == [
        ("navigate", "home-shop-entry"),
        ("navigate", "daily-info"),
        ("backtrack", "daily-info-close"),
        ("backtrack", "daily-exit"),
    ]
    assert [item["page"] for item in result.visited] == [
        "game-home",
        "daily-offer",
        "daily-info-popup",
        "daily-offer",
        "game-home",
    ]
    assert result.claims == []
    assert result.journal_rows == 0
    assert clock.now < 60.0


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

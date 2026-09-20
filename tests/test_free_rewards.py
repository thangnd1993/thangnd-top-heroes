from dataclasses import replace

import pytest

from top_heroes_auto.automation.free_rewards import (
    Cost,
    ExplorerLimits,
    FreeRewardExplorer,
    FreeRewardGuard,
    RewardEvidence,
    RewardScreen,
    Route,
)
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenDetection, ScreenState


def screen(capture="1", *, page="shop", fingerprint="A", x=10, **kwargs):
    anchors = tuple(
        AnchorEvidence(a, ScreenState.GAME_HOME, 0.99, 0.9, True, None, BoundingBox(x, 20, 10, 10))
        for a in ("claim", "free", "available", "tab", "scroll:vertical", "scroll:horizontal")
    )
    detection = ScreenDetection(ScreenState.GAME_HOME, 0.99, anchors, capture, None, 1)
    return RewardScreen(detection, 4, "3-Chíp", "emulator-5562", "boot", capture, page, fingerprint, **kwargs)


def reward(**kwargs):
    return replace(RewardEvidence("gift", "claim", "free", "available", Cost.FREE, False), **kwargs)


class Port:
    def __init__(self, screens, *, verified=True, failure=False):
        self.screens = iter(screens)
        self.actions = []
        self.verified = verified
        self.failure = failure

    def observe(self):
        return next(self.screens)

    def claim(self, observation, item, point):
        self.actions.append(("claim", item.reward_id, point))
        if self.failure:
            raise OSError("transport lost after input")

    def verify_claim(self, before, after, item):
        return self.verified

    def navigate(self, observation, route, point):
        self.actions.append((route.kind, route.id, point))

    def scroll(self, observation, axis):
        self.actions.append(("scroll", axis))

    def return_home(self, observation):
        self.actions.append(("home",))
        return True


@pytest.mark.parametrize("cost", [c for c in Cost if c != Cost.FREE])
def test_resource_and_unknown_costs_rejected(cost):
    r = reward(cost=cost)
    p = Port([screen(rewards=(r,))])
    result = FreeRewardExplorer().run(p, 4, "3-Chíp")
    assert result.status == "SAFETY_BLOCKED"
    assert not p.actions


def test_ambiguous_free_reward_rejected():
    p = Port([screen(rewards=(reward(ambiguous=True),))])
    assert FreeRewardExplorer().run(p, 4, "3-Chíp").status == "SAFETY_BLOCKED"
    assert not p.actions


def test_free_label_without_available_evidence_rejected():
    r = reward()
    s = screen(rewards=(r,))
    s = replace(s, detection=replace(s.detection, evidence=s.detection.evidence[:2]))
    p = Port([s])
    assert FreeRewardExplorer().run(p, 4, "3-Chíp").status == "SAFETY_BLOCKED"
    assert not p.actions


def test_free_claim_is_verified_then_recovered_and_never_retried():
    r = reward()
    p = Port([screen(rewards=(r,)), screen("2", rewards=(r,), coverage_known=True)])
    result = FreeRewardExplorer().run(p, 4, "3-Chíp")
    assert result.status == "PARTIAL"  # initial page coverage was not known
    assert result.claimed == result.attempted == ["gift"]
    assert p.actions == [("claim", "gift", (15, 25)), ("home",)]
    assert result.recovery_succeeded


@pytest.mark.parametrize("failure", [True, False])
def test_uncertain_claim_never_retried_or_cleaned_up_blindly(failure):
    p = Port([screen(rewards=(reward(),)), screen("2")], verified=False, failure=failure)
    result = FreeRewardExplorer().run(p, 4, "3-Chíp")
    assert result.status == "ACTION_RESULT_UNCERTAIN"
    assert result.attempted == ["gift"]
    assert not result.claimed
    assert len(p.actions) == 1


def test_target_rediscovered_after_capture_and_across_accounts():
    g = FreeRewardGuard(4, "3-Chíp")
    a, b = screen(x=10), screen("2", x=400)
    g.observe(a)
    assert g.consume(a, "tab") == (15, 25)
    with pytest.raises(SafetyError):
        g.consume(a, "tab")
    g.observe(b)
    assert g.consume(b, "tab") == (405, 25)
    other = replace(screen("3", x=800), index=5, name="other", adb_target="emulator-5564")
    with pytest.raises(SafetyError):
        g.observe(other)
    other_guard = FreeRewardGuard(5, "other")
    other_guard.observe(other)
    assert other_guard.consume(other, "tab") == (805, 25)


@pytest.mark.parametrize("field,value", [("adb_target", ""), ("adb_target", "other"), ("boot_id", "new")])
def test_transport_identity_change_invalidates_evidence(field, value):
    g = FreeRewardGuard(4, "3-Chíp")
    g.observe(screen())
    with pytest.raises(SafetyError):
        g.observe(replace(screen("2"), **{field: value}))
    assert g.current is None


def test_stale_capture_rejected():
    g = FreeRewardGuard(4, "3-Chíp")
    g.observe(screen())
    with pytest.raises(SafetyError):
        g.observe(screen())


@pytest.mark.parametrize("unknown", [True, False])
def test_unknown_or_low_confidence_no_input(unknown):
    s = screen(rewards=(reward(),))
    s = replace(s, detection=replace(
        s.detection, state=ScreenState.UNKNOWN if unknown else ScreenState.GAME_HOME,
        confidence=0.99 if unknown else 0.89,
    ))
    p = Port([s])
    assert FreeRewardExplorer().run(p, 4, "3-Chíp").status == "UNKNOWN_SCREEN"
    assert not p.actions


def test_nested_tabs_require_verified_destination_and_fresh_coordinates():
    child = Route("weekly", "tab", "weekly", "submenu")
    parent = Route("back", "tab", "shop", "parent")
    p = Port([
        screen(routes=(child,), coverage_known=True),
        screen("2", page="weekly", depth=1, routes=(parent,), x=400, coverage_known=True),
        screen("3", routes=(child,), coverage_known=True),
    ])
    result = FreeRewardExplorer().run(p, 4, "3-Chíp")
    assert result.status == "NOT_AVAILABLE"
    assert result.coverage_complete
    assert p.actions == [("submenu", "weekly", (15, 25)), ("parent", "back", (405, 25)), ("home",)]


def test_wrong_destination_stops_without_another_input():
    p = Port([screen(routes=(Route("weekly", "tab", "weekly"),)), screen("2", page="purchase")])
    assert FreeRewardExplorer().run(p, 4, "3-Chíp").status == "UNKNOWN_SCREEN"
    assert len(p.actions) == 1


def test_vertical_and_horizontal_scroll_stop_on_repeated_content():
    p = Port([
        screen(str(i), fingerprint=fp, scroll_axes=("vertical", "horizontal"), coverage_known=True)
        for i, fp in enumerate(("A", "B", "B", "C", "C"))
    ])
    result = FreeRewardExplorer().run(p, 4, "3-Chíp")
    assert result.status == "NOT_AVAILABLE"
    assert p.actions == [("scroll", "vertical")] * 2 + [("scroll", "horizontal")] * 2 + [("home",)]


def test_unscanned_parent_content_cannot_be_reported_as_complete():
    p = Port([
        screen(routes=(Route("weekly", "tab", "weekly"),), scroll_axes=("vertical",), coverage_known=True),
        screen("2", page="weekly", coverage_known=True),
    ])
    result = FreeRewardExplorer().run(p, 4, "3-Chíp")
    assert result.status == "PARTIAL"
    assert not result.coverage_complete


def test_scroll_bound_is_partial_not_unavailable():
    p = Port([screen(str(i), fingerprint=str(i), scroll_axes=("vertical",), coverage_known=True) for i in range(3)])
    result = FreeRewardExplorer(ExplorerLimits(max_scrolls=2)).run(p, 4, "3-Chíp")
    assert result.status == "PARTIAL"
    assert not result.coverage_complete


def test_red_dot_is_discovery_only():
    p = Port([screen(red_dot_candidates=("unknown-gift",))])
    result = FreeRewardExplorer().run(p, 4, "3-Chíp")
    assert result.status == "PARTIAL"
    assert result.visited[0]["red_dot_candidates"] == ["unknown-gift"]
    assert p.actions == [("home",)]


def test_cancel_after_observation_prevents_dispatch():
    cancelled = iter((False, True))
    p = Port([screen(rewards=(reward(),))])
    assert FreeRewardExplorer().run(p, 4, "3-Chíp", lambda: next(cancelled)).status == "CANCELLED"
    assert not p.actions


def test_diamond_rewards_prioritized():
    r1, r2 = reward(reward_id="items", action_anchor="item-claim"), reward(
        reward_id="diamonds", diamond_reward=True,
    )
    p = Port([screen(rewards=(r1, r2))], failure=True)
    result = FreeRewardExplorer().run(p, 4, "3-Chíp")
    assert result.attempted == ["diamonds"]


def test_shared_claim_target_rejected():
    p = Port([screen(rewards=(reward(), reward(reward_id="duplicate")))])
    assert FreeRewardExplorer().run(p, 4, "3-Chíp").status == "SAFETY_BLOCKED"
    assert not p.actions


def test_nonfinite_confidence_rejected_at_dispatch():
    s = screen(rewards=(reward(),))
    s = replace(s, detection=replace(s.detection, confidence=float("nan")))
    p = Port([s])
    assert FreeRewardExplorer().run(p, 4, "3-Chíp").status == "SAFETY_BLOCKED"
    assert not p.actions

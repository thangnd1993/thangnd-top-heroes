"""Versioned Phase 6 survey anchors are evidence, not claim authorization."""

from pathlib import Path

import cv2
import pytest

from top_heroes_auto.automation.phase6_visual import free_recruit_profile, vip_reward_profile
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.models import ScreenState

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "tasks" / "phase6"


@pytest.mark.parametrize("name", ["vip", "recruit"])
def test_fixed_reward_anchors_have_only_the_expected_qualification(name):
    anchors = load_anchors(ASSETS / name)
    roles = {anchor.id.removeprefix(f"{name}-"): anchor for anchor in anchors}
    expected = {"page", "free", "available", "claim", "home"}
    if name == "vip":
        expected |= {"post", "paid"}
    assert set(roles) == expected
    assert all(anchor.state == ScreenState.FREE_REWARD_PAGE for anchor in anchors)
    for anchor in anchors:
        image = cv2.imread(str(anchor.template))
        assert image is not None and min(image.shape[:2]) >= 10
        assert image.std() >= 1
    factory = vip_reward_profile if name == "vip" else free_recruit_profile
    if name == "vip":
        profile = factory({
            "page": roles["page"], "free": roles["free"], "available": roles["available"],
            "claim": roles["claim"], "home": roles["home"], "post": roles["post"],
            "paid": roles["paid"],
        })
        assert profile.geometry_required
        assert profile.forbidden_roles == ("paid",)
        assert profile.coverage_known
    else:
        with pytest.raises(ValueError, match="post"):
            factory(roles)


def test_home_route_assets_are_navigation_evidence_only():
    anchors = load_anchors(ASSETS / "home")
    assert {anchor.id for anchor in anchors} == {
        "home-vip-entry", "home-shop-entry", "home-tavern",
        "tavern-selected-name", "tavern-recruit-entry",
    }
    assert all(anchor.state == ScreenState.GAME_HOME for anchor in anchors)
    assert not any("claim" in anchor.id or "post" in anchor.id for anchor in anchors)


def test_tavern_action_anchor_rejects_surveyed_animated_matches():
    anchors = {anchor.id: anchor for anchor in load_anchors(ASSETS / "home")}
    tavern = anchors["home-tavern"]
    assert tavern.threshold == pytest.approx(0.97)
    assert 0.9449 < tavern.threshold
    assert 0.8363 < tavern.threshold

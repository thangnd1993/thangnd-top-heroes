from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.free_reward_tasks import _load_profile_details
from top_heroes_auto.automation.free_rewards import ClaimOutcome, Cost
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.phase6_visual import FrameRewardAdapter
from top_heroes_auto.automation.vip_geometry import (
    validate_vip_claim_geometry,
    write_vip_geometry_overlay,
)
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import AnchorEvidence, ScreenState
from top_heroes_auto.vision.screenshot import ScreenshotService

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "phase6_vip"
ASSETS = ROOT / "assets" / "tasks" / "phase6"
IDENTITY = Target(2, "5-Emmmmm", "emulator-5558", "fixture-boot")


def _fixture(name):
    path = FIXTURES / name
    return ScreenshotService(lambda _serial: path.read_bytes()).take(IDENTITY)


def _profile():
    profile, error = _load_profile_details("vip-reward")
    assert error is None and profile is not None
    return profile


def test_vip_entry_is_uniquely_detected_from_clean_current_account_home():
    screen = _fixture("index2-home.png")
    anchor = next(a for a in load_anchors(ASSETS / "home") if a.id == "home-vip-entry")
    found = unique_current_anchor(screen, anchor)
    assert found.matched and found.score >= 0.9
    assert found.normalized_box is not None and found.device_box is not None


def test_claim_geometry_uses_live_vip_bbox_and_excludes_paid_region(tmp_path):
    profile = _profile()
    home = _fixture("index2-home.png")
    vip = _fixture("index2-vip-claimable.png")
    entry_anchor = next(a for a in load_anchors(ASSETS / "home") if a.id == "home-vip-entry")
    entry = unique_current_anchor(home, entry_anchor)
    observation = FrameRewardAdapter(profile).observe(vip)
    reward = observation.screen.rewards[0]
    assert observation.screen.detection.state == ScreenState.FREE_REWARD_PAGE
    assert reward.cost == Cost.FREE and not reward.ambiguous

    evidence = {item.anchor_id: item for item in observation.screen.detection.evidence}
    claim = evidence["vip-claim"]
    paid = evidence["vip-paid"]
    assert claim.matched and paid.matched
    geometry = validate_vip_claim_geometry(
        claim.device_box,
        claim.device_box.center,
        (paid.device_box,),
    )
    assert geometry.tap_point == claim.device_box.center
    assert claim.device_box.x <= geometry.tap_point[0] < claim.device_box.x + claim.device_box.width
    assert claim.device_box.y <= geometry.tap_point[1] < claim.device_box.y + claim.device_box.height
    assert not (
        paid.device_box.x <= geometry.tap_point[0] < paid.device_box.x + paid.device_box.width
        and paid.device_box.y <= geometry.tap_point[1] < paid.device_box.y + paid.device_box.height
    )

    overlay = write_vip_geometry_overlay(
        home.normalized,
        vip.normalized,
        entry.normalized_box,
        claim.normalized_box,
        claim.normalized_box.center,
        geometry.tap_point,
        (paid.normalized_box,),
        tmp_path / "vip-geometry-overlay.png",
    )
    image = cv2.imread(str(overlay))
    assert image is not None and image.size
    # Draw in panel-local coordinates before concatenation; boxes must be visible.
    x_offset = home.normalized.shape[1]
    assert tuple(image[claim.normalized_box.y + 42, claim.normalized_box.x + x_offset]) == (30, 220, 40)
    assert tuple(image[paid.normalized_box.y + 42, paid.normalized_box.x + x_offset]) == (30, 30, 240)


def test_paid_region_overlap_is_rejected_before_any_claim_reservation():
    claim = _profile().anchor_map["claim"]
    assert claim.threshold >= 0.9
    from top_heroes_auto.vision.models import BoundingBox

    allowed = BoundingBox(200, 300, 90, 50)
    overlapping_paid = BoundingBox(240, 320, 90, 70)
    with pytest.raises(SafetyError, match="intersects"):
        validate_vip_claim_geometry(allowed, allowed.center, (overlapping_paid,))


def test_vip_claim_postcondition_requires_claimed_button_and_live_page():
    profile = _profile()
    before = FrameRewardAdapter(profile).observe(_fixture("index2-vip-claimable.png"))
    available = next(
        item for item in before.screen.detection.evidence if item.anchor_id == "vip-available"
    )
    claim = next(item for item in before.screen.detection.evidence if item.anchor_id == "vip-claim")
    post_template = cv2.imread(str(profile.anchor_map["post"].template))
    assert available.normalized_box is not None and claim.normalized_box is not None
    changed = before.captured.normalized.copy()
    x0 = min(available.normalized_box.x, claim.normalized_box.x)
    y0 = min(available.normalized_box.y, claim.normalized_box.y)
    x1 = max(available.normalized_box.x + available.normalized_box.width,
             claim.normalized_box.x + claim.normalized_box.width)
    y1 = max(available.normalized_box.y + available.normalized_box.height,
             claim.normalized_box.y + claim.normalized_box.height)
    changed[y0:y1, x0:x1] = (20, 35, 55)
    changed[
        available.normalized_box.y:available.normalized_box.y + post_template.shape[0],
        available.normalized_box.x:available.normalized_box.x + post_template.shape[1],
    ] = post_template
    fresh = replace(
        before.captured,
        original=changed,
        normalized=changed,
        source_image=None,
        timestamp="fresh-postclaim-frame",
    )
    after = FrameRewardAdapter(profile).observe(fresh)
    assert after.screen.detection.state == ScreenState.FREE_REWARD_PAGE
    assert after.screen.rewards == ()
    assert FrameRewardAdapter(profile).classify_claim(
        before.screen, after.screen, before.screen.rewards[0]
    ) == ClaimOutcome.CLAIMED


def test_popup_only_receipt_or_unchanged_claimable_state_is_not_verified():
    profile = _profile()
    adapter = FrameRewardAdapter(profile)
    before = adapter.observe(_fixture("index2-vip-claimable.png"))
    reward = before.screen.rewards[0]
    evidence = tuple(
        item for item in before.screen.detection.evidence
        if item.anchor_id != "vip-post"
    ) + (
        AnchorEvidence(
            "vip-receipt", ScreenState.POPUP_GENERIC, 0.999, 0.96, True,
            before.screen.detection.evidence[0].normalized_box,
            before.screen.detection.evidence[0].device_box,
        ),
    )
    popup = replace(
        before.screen,
        detection=replace(
            before.screen.detection,
            state=ScreenState.FREE_REWARD_PAGE,
            evidence=evidence,
        ),
        capture_id="popup-only-fresh-capture",
    )
    assert adapter.classify_claim(before.screen, popup, reward) == ClaimOutcome.UNKNOWN
    assert adapter.classify_claim(before.screen, before.screen, reward) == ClaimOutcome.UNKNOWN

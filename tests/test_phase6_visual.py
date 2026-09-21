from dataclasses import replace

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.app.phase6_runtime import reward_port_factory
from top_heroes_auto.automation.free_rewards import Cost
from top_heroes_auto.automation.phase6_visual import (
    FrameRewardAdapter,
    RewardRule,
    RewardVisualProfile,
)
from top_heroes_auto.vision.models import CapturedScreen, NormalizedRect, ScreenState, VisualAnchor


def _templates(tmp_path):
    paths = {}
    for number, role in enumerate(("page", "claim", "free", "available", "post", "paid"), 1):
        image = np.random.default_rng(number).integers(1, 255, (14, 16, 3), dtype=np.uint8)
        path = tmp_path / f"{role}.png"
        assert cv2.imwrite(str(path), image)
        paths[role] = (image, path)
    return paths


def _profile(tmp_path, *, task="vip-reward", paid=False):
    templates = _templates(tmp_path)
    roles = ("page", "claim", "free", "available", "post") + (("paid",) if paid else ())
    anchors = tuple(
        (
            role,
            VisualAnchor(
                f"{role}-anchor",
                ScreenState.FREE_REWARD_PAGE,
                templates[role][1],
                NormalizedRect(0, 0, 1, 1),
                0.95,
            ),
        )
        for role in roles
    )
    rule = RewardRule(
        "vip-daily" if task == "vip-reward" else "recruit-free",
        diamond_reward=task == "vip-reward",
        paid_role="paid" if paid else None,
        paid_cost=Cost.TICKETS if paid else Cost.UNKNOWN,
    )
    return RewardVisualProfile(task, task.removesuffix("-reward"), anchors, (rule,)), templates


def _capture(templates, present, *, shift=0, index=2, name="5-Emmmmm", stamp="frame"):
    image = np.full((180, 320, 3), 18, dtype=np.uint8)
    positions = {
        "page": (8 + shift, 8),
        "claim": (56 + shift, 24),
        "free": (112 + shift, 44),
        "available": (168 + shift, 66),
        "post": (224 + shift, 88),
        "paid": (72 + shift, 132),
    }
    for role in present:
        template = templates[role][0]
        x, y = positions[role]
        image[y:y + template.shape[0], x:x + template.shape[1]] = template
    return CapturedScreen(
        index,
        name,
        "emulator-5558",
        "70b1cc0e-24e0-4657-9e54-4025067f47aa",
        image,
        image,
        (320, 180),
        (320, 180),
        (1, 1),
        timestamp=stamp,
    )


@pytest.mark.parametrize("task", ["vip-reward", "free-recruit"])
def test_vip_and_recruit_use_current_frame_anchor_positions(tmp_path, task):
    profile, templates = _profile(tmp_path, task=task)
    adapter = FrameRewardAdapter(profile)
    before = adapter.observe(_capture(templates, ("page", "claim", "free", "available"), stamp="before"))
    reward = before.screen.rewards[0]
    assert before.screen.detection.state == ScreenState.FREE_REWARD_PAGE
    assert reward.cost == Cost.FREE and not reward.ambiguous
    first_point = next(item for item in before.screen.detection.evidence if item.anchor_id == "claim-anchor")
    assert first_point.device_box is not None

    moved = adapter.observe(
        _capture(templates, ("page", "claim", "free", "available"), shift=70, stamp="moved")
    )
    second_point = next(item for item in moved.screen.detection.evidence if item.anchor_id == "claim-anchor")
    assert second_point.device_box is not None
    assert second_point.device_box.center != first_point.device_box.center


def test_missing_availability_is_ambiguous_and_never_free(tmp_path):
    profile, templates = _profile(tmp_path)
    observed = FrameRewardAdapter(profile).observe(_capture(templates, ("page", "claim", "free")))
    reward = observed.screen.rewards[0]
    assert reward.cost == Cost.UNKNOWN
    assert reward.ambiguous


def test_paid_evidence_wins_over_free_labels(tmp_path):
    profile, templates = _profile(tmp_path, paid=True)
    observed = FrameRewardAdapter(profile).observe(
        _capture(templates, ("page", "claim", "free", "available", "paid"))
    )
    reward = observed.screen.rewards[0]
    assert reward.cost == Cost.TICKETS
    assert not reward.ambiguous


def test_postcondition_requires_fresh_post_anchor_and_free_state_is_not_receipt(tmp_path):
    profile, templates = _profile(tmp_path)
    adapter = FrameRewardAdapter(profile)
    before = adapter.observe(_capture(templates, ("page", "claim", "free", "available"), stamp="before"))
    reward = before.screen.rewards[0]
    after = adapter.observe(_capture(templates, ("page", "post"), stamp="after"))
    assert adapter.verify_claim(before.screen, after.screen, reward)

    still_claimable = adapter.observe(
        _capture(templates, ("page", "claim", "free", "available", "post"), stamp="still-free")
    )
    assert not adapter.verify_claim(before.screen, still_claimable.screen, reward)


def test_postcondition_rejects_wrong_account_or_transport(tmp_path):
    profile, templates = _profile(tmp_path)
    adapter = FrameRewardAdapter(profile)
    before = adapter.observe(_capture(templates, ("page", "claim", "free", "available"), stamp="before"))
    after = adapter.observe(_capture(templates, ("page", "post"), stamp="after"))
    reward = before.screen.rewards[0]
    assert not adapter.verify_claim(before.screen, replace(after.screen, index=7), reward)
    assert not adapter.verify_claim(before.screen, replace(after.screen, boot_id="other"), reward)


def test_runtime_home_observer_rejects_boot_change_after_reward_dispatch(tmp_path):
    profile, _ = _profile(tmp_path)

    class Manager:
        def capture_verified(self, index, snapshot):
            return Target(index, "5-Emmmmm", "serial-a", "boot-b"), b"unused"

    port = reward_port_factory(Manager(), None, 2, "5-Emmmmm", profile, tmp_path)
    assert port.home_observer("serial-a", "boot-a") is False

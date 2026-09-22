import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.phase6_vip_survey import (
    GuardedVipSurvey,
    VipSurveyFrame,
    VipSurveyStatus,
)
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import CapturedScreen, ScreenDetection, ScreenState

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ("emulator-5558", "boot-2")


def _anchors():
    home = {anchor.id: anchor for anchor in load_anchors(ROOT / "assets" / "tasks" / "phase6" / "home")}
    vip = {anchor.id: anchor for anchor in load_anchors(ROOT / "assets" / "tasks" / "phase6" / "vip")}
    template_home = {
        anchor.id: anchor for anchor in load_anchors(ROOT / "assets" / "templates" / "home")
    }
    return {
        "home_entry": home["home-vip-entry"],
        "page": vip["vip-page"],
        "free": vip["vip-free"],
        "available": vip["vip-available"],
        "claim": vip["vip-claim"],
        "exit": vip["vip-home"],
        "home": template_home["home-bottom-navigation"],
    }


def _image(anchors, page, *, duplicate=None, omit=()):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)

    positions = {
        "home_entry": (1040, 30),
        "page": (1150, 300),
        "free": (320, 110),
        "available": (500, 250),
        "claim": (600, 500),
        "exit": (20, 20),
        "home": (150, 560),
    }
    if page == "home":
        roles = ("home_entry", "home")
    else:
        roles = ("page", "free", "available", "claim", "exit")
    for role in roles:
        if role in omit:
            continue
        template = cv2.imread(str(anchors[role].template), cv2.IMREAD_COLOR)
        assert template is not None
        x, y = positions[role]
        height, width = template.shape[:2]
        image[y : y + height, x : x + width] = template
        if duplicate == role:
            image[y + 90 : y + 90 + height, x : x + width] = template
    return image


def _captured(image, *, boot="boot-2", tag="frame"):
    return CapturedScreen(
        2,
        "5-Emmmmm",
        "emulator-5558",
        boot,
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        timestamp=tag,
    )


class FakePort:
    def __init__(self, frames, *, fail_tap_at=None, missing_capture=False):
        self.frames = iter(frames)
        self.actions = []
        self.fail_tap_at = fail_tap_at
        self.missing_capture = missing_capture

    def observe(self, tag):
        if self.missing_capture:
            raise OSError("capture unavailable")
        target, image = next(self.frames)
        return VipSurveyFrame(target, _captured(image, boot=target.boot_id, tag=tag))

    def tap(self, frame, point):
        self.actions.append((frame.target, point))
        if self.fail_tap_at == len(self.actions):
            raise OSError("tap dispatch uncertain")


def _survey(port, anchors, *, cancelled=lambda: False, clock=None):
    def detector(screen):
        return ScreenDetection(ScreenState.GAME_HOME, 1.0, (), screen.timestamp, None, 0.0)

    kwargs = {"clock": clock} if clock else {}
    return GuardedVipSurvey(
        port,
        anchors,
        detector,
        IDENTITY,
        max_seconds=30.0,
        **kwargs,
    ).run(cancelled)


def test_vip_survey_observes_diagnostics_and_round_trip_without_claim_input():
    anchors = _anchors()
    port = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "vip")),
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
        ]
    )

    result = _survey(port, anchors)

    assert result.status == VipSurveyStatus.SUCCESS
    assert len(port.actions) == 2
    assert len(result.captures) == 3
    assert result.actions == ["tap:home-vip-entry", "tap:vip-exit"]
    assert result.diagnostics[result.captures[1]]["anchors"]["free"]["matched"] is True
    assert result.receipt_available is False
    assert result.claim_readiness == "NOT_IMPLEMENTED"
    assert result.claims == []
    assert result.journal_rows == 0


def test_vip_survey_rejects_ambiguous_entry_and_missing_capture_without_input():
    anchors = _anchors()
    duplicate = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home", duplicate="home_entry")),
        ]
    )
    result = _survey(duplicate, anchors)
    assert result.status == VipSurveyStatus.BLOCKED
    assert duplicate.actions == []

    missing = FakePort([], missing_capture=True)
    result = _survey(missing, anchors)
    assert result.status == VipSurveyStatus.BLOCKED
    assert missing.actions == []


def test_vip_survey_rejects_bad_destination_and_identity_without_exit_retry():
    anchors = _anchors()
    bad_page = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "vip", omit=("page",))),
        ]
    )
    result = _survey(bad_page, anchors)
    assert result.status == VipSurveyStatus.DESTINATION_UNVERIFIED
    assert len(bad_page.actions) == 1

    boot_change = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
            (Target(2, "5-Emmmmm", "emulator-5558", "boot-new"), _image(anchors, "vip")),
        ]
    )
    result = _survey(boot_change, anchors)
    assert result.status == VipSurveyStatus.IDENTITY_MISMATCH
    assert len(boot_change.actions) == 1


def test_vip_survey_treats_reward_controls_as_diagnostics_only():
    anchors = _anchors()
    port = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
            (
                Target(2, "5-Emmmmm", *IDENTITY),
                _image(anchors, "vip", omit=("free", "available", "claim")),
            ),
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
        ]
    )

    result = _survey(port, anchors)

    assert result.status == VipSurveyStatus.SUCCESS
    assert len(port.actions) == 2
    diagnostics = result.diagnostics[result.captures[1]]["anchors"]
    assert diagnostics["page"]["matched"] is True
    assert diagnostics["free"]["matched"] is False
    assert diagnostics["available"]["matched"] is False
    assert diagnostics["claim"]["matched"] is False


def test_vip_survey_allows_missing_diagnostic_anchor_assets():
    anchors = _anchors()
    required = {role: anchor for role, anchor in anchors.items() if role not in {"free", "available", "claim"}}
    port = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "vip")),
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
        ]
    )

    result = GuardedVipSurvey(
        port,
        required,
        lambda screen: ScreenDetection(ScreenState.GAME_HOME, 1.0, (), screen.timestamp, None, 0.0),
        IDENTITY,
    ).run()

    assert result.status == VipSurveyStatus.SUCCESS
    diagnostics = result.diagnostics[result.captures[1]]["anchors"]
    assert diagnostics["free"] == {
        "anchor": None,
        "required": False,
        "available": False,
        "proven": False,
    }


def test_vip_survey_cancellation_and_uncertain_input_never_retry():
    anchors = _anchors()
    port = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "vip")),
        ]
    )
    result = _survey(port, anchors, cancelled=lambda: bool(port.actions))
    assert result.status == VipSurveyStatus.CANCELLED
    assert len(port.actions) == 1

    uncertain = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
        ],
        fail_tap_at=1,
    )
    result = _survey(uncertain, anchors)
    assert result.status == VipSurveyStatus.ACTION_RESULT_UNCERTAIN
    assert len(uncertain.actions) == 1

    uncertain_exit = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "vip")),
        ],
        fail_tap_at=2,
    )
    result = _survey(uncertain_exit, anchors)
    assert result.status == VipSurveyStatus.ACTION_RESULT_UNCERTAIN
    assert len(uncertain_exit.actions) == 2


def test_vip_survey_deadline_blocks_before_next_dispatch():
    anchors = _anchors()
    port = FakePort(
        [
            (Target(2, "5-Emmmmm", *IDENTITY), _image(anchors, "home")),
        ]
    )
    ticks = iter((0.0, 31.0))
    result = _survey(port, anchors, clock=lambda: next(ticks))
    assert result.status == VipSurveyStatus.TIMEOUT
    assert port.actions == []


RUN_VIP = Path(
    os.environ.get(
        "THA_PHASE6_VIP_OPEN",
        r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\vision\5-Emmmmm\20260920-180241-073168Z-phase6-vip-open-after.png",
    )
)
RUN_VIP_SECOND = Path(
    os.environ.get(
        "THA_PHASE6_VIP_SECOND",
        r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\vision\5-Emmmmm\20260921-174132-284341Z-phase6-20260922-vip-current-after.png",
    )
)
RUN_HOME_AFTER = Path(
    os.environ.get(
        "THA_PHASE6_VIP_HOME_AFTER",
        r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\vision\5-Emmmmm\20260920-180319-616391Z-phase6-vip-exit-after.png",
    )
)
RUN_DAILY = RUN_VIP.parent / "20260920-172408-371450Z-phase6-shop-daily-top-before.png"
RUN_PACK = RUN_VIP.parent / "20260920-172802-484980Z-phase6-shop-daily-pack-before.png"


@pytest.mark.skipif(not RUN_VIP.is_file(), reason="saved index-2 VIP frame is not available")
def test_vip_home_exit_anchor_is_page_gated_and_matches_vip_frames():
    anchor = _anchors()["exit"]
    for path in (RUN_VIP, RUN_VIP_SECOND):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert image is not None
        captured = _captured(image, tag=path.name)
        evidence = unique_current_anchor(captured, anchor)
        assert evidence.matched
        assert evidence.score >= 0.97
    if RUN_HOME_AFTER.is_file():
        image = cv2.imread(str(RUN_HOME_AFTER), cv2.IMREAD_COLOR)
        assert image is not None
        captured = _captured(image, tag=RUN_HOME_AFTER.name)
        evidence = unique_current_anchor(captured, anchor)
        assert not evidence.matched
    # The same generic arrow also appears on shop frames.  Those are an
    # intentional overmatch probe: the survey must require the VIP page proof
    # before dispatching this exit anchor (covered by the bad-destination test).
    for path in (RUN_DAILY, RUN_PACK):
        if path.is_file():
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            assert image is not None
            captured = _captured(image, tag=path.name)
            assert unique_current_anchor(captured, anchor).matched

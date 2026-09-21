from pathlib import Path

import cv2
import numpy as np

from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.phase6_shop_navigation import (
    GuardedShopNavigation,
    ShopNavigationFrame,
    ShopNavigationProfile,
    ShopNavigationStatus,
)
from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.models import CapturedScreen, ScreenDetection, ScreenState

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "tasks" / "phase6"
TARGET = Target(2, "5-Emmmmm", "emulator-5558", "boot-2")
TARGET_MEMBER = (TARGET.index, TARGET.name)


def _profile() -> ShopNavigationProfile:
    home = {item.id: item for item in load_anchors(ASSETS / "home")}
    shop = {item.id: item for item in load_anchors(ASSETS / "shop")}
    return ShopNavigationProfile(
        home["home-shop-entry"],
        shop["phase6-daily-page"],
        shop["phase6-daily-info-button"],
        shop["phase6-daily-info-popup"],
        shop["phase6-daily-info-close"],
        shop["phase6-daily-exit"],
    )


def _image(*anchors, duplicate=None):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    locations = {
        "home-shop-entry": (1120, 540),
        "phase6-daily-page": (1120, 0),
        "phase6-daily-info-button": (1120, 540),
        "phase6-daily-info-popup": (1080, 100),
        "phase6-daily-info-close": (83, 320),
        "phase6-daily-exit": (0, 0),
    }
    for anchor in anchors:
        template = cv2.imread(str(anchor.template), cv2.IMREAD_COLOR)
        assert template is not None
        height, width = template.shape[:2]
        x, y = locations[anchor.id]
        image[y : y + height, x : x + width] = template
    if duplicate is not None:
        template = cv2.imread(str(duplicate.template), cv2.IMREAD_COLOR)
        height, width = template.shape[:2]
        duplicate_locations = {
            "home-shop-entry": (1200, 540),
            "phase6-daily-page": (998, 0),
            "phase6-daily-info-button": (960, 540),
            "phase6-daily-info-popup": (930, 100),
            "phase6-daily-info-close": (240, 320),
            "phase6-daily-exit": (150, 0),
        }
        x, y = duplicate_locations[duplicate.id]
        image[y : y + height, x : x + width] = template
    return image


def _frame(tmp_path, image, label, *, target=TARGET):
    source = tmp_path / f"{label}.png"
    return ShopNavigationFrame(
        target,
        CapturedScreen(
            target.index,
            target.name,
            target.serial,
            target.boot_id,
            image,
            image,
            (1280, 720),
            (1280, 720),
            (1.0, 1.0),
            source_image=source,
        ),
    )


def _home_detector(screen):
    is_home = screen.source_image is not None and "home" in screen.source_image.stem
    return ScreenDetection(
        ScreenState.GAME_HOME if is_home else ScreenState.FREE_REWARD_PAGE,
        0.99,
        (),
        screen.timestamp,
        screen.source_image,
        0.1,
    )


class Port:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.taps = []

    def observe(self, tag):
        return next(self.frames)

    def tap(self, frame, point):
        self.taps.append((frame.capture_id, point))


def _route_frames(tmp_path, profile=None):
    profile = profile or _profile()
    return [
        _frame(tmp_path, _image(profile.home_shop_entry), "home-before"),
        _frame(tmp_path, _image(profile.daily_page, profile.info_button, profile.daily_exit), "daily-after-entry"),
        _frame(tmp_path, _image(profile.info_popup, profile.info_close), "popup-after-info"),
        _frame(tmp_path, _image(profile.daily_page, profile.info_button, profile.daily_exit), "daily-after-close"),
        _frame(tmp_path, _image(profile.home_shop_entry), "home-after-exit"),
    ]


def _navigator(port, profile=None, **kwargs):
    return GuardedShopNavigation(
        port,
        profile or _profile(),
        _home_detector,
        destination_wait_seconds=0,
        **kwargs,
    )


def test_four_action_route_is_observation_only_and_fresh(tmp_path):
    port = Port(_route_frames(tmp_path))
    result = _navigator(port).run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.SUCCESS
    assert result.actions == [
        "tap:home-shop-entry",
        "tap:phase6-daily-info-button",
        "tap:phase6-daily-info-close",
        "tap:phase6-daily-exit",
    ]
    assert len(port.taps) == 4
    assert len(result.captures) == 5
    assert result.as_dict()["claims"] == []
    assert result.as_dict()["journal_rows"] == 0


def test_ambiguous_current_anchor_dispatches_zero_inputs(tmp_path):
    profile = _profile()
    home = _frame(
        tmp_path,
        _image(profile.home_shop_entry, duplicate=profile.home_shop_entry),
        "home-ambiguous",
    )
    result = _navigator(Port([home])).run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.BLOCKED
    assert result.actions == []


def test_wrong_initial_identity_dispatches_zero_inputs(tmp_path):
    profile = _profile()
    wrong = Target(2, "other", TARGET.serial, TARGET.boot_id)
    port = Port([_frame(tmp_path, _image(profile.home_shop_entry), "wrong", target=wrong)])
    result = _navigator(port).run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.IDENTITY_MISMATCH
    assert not port.taps


def test_missing_daily_info_button_stops_before_second_tap(tmp_path):
    profile = _profile()
    frames = [
        _frame(tmp_path, _image(profile.home_shop_entry), "home-before"),
        _frame(tmp_path, _image(profile.daily_page, profile.daily_exit), "daily-missing-info"),
    ]
    port = Port(frames)
    result = _navigator(port).run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.DESTINATION_UNVERIFIED
    assert result.actions == ["tap:home-shop-entry"]
    assert len(port.taps) == 1


def test_cancel_between_popup_and_close_dispatches_no_third_tap(tmp_path):
    port = Port(_route_frames(tmp_path))
    result = _navigator(port).run(*TARGET_MEMBER, cancelled=lambda: len(port.taps) >= 2)

    assert result.status == ShopNavigationStatus.CANCELLED
    assert len(port.taps) == 2
    assert result.actions[-1] == "tap:phase6-daily-info-button"


def test_delayed_destination_is_bounded_and_never_retries_input(tmp_path):
    profile = _profile()
    delayed = [
        _frame(tmp_path, _image(profile.home_shop_entry), "home-before"),
        _frame(tmp_path, _image(profile.home_shop_entry), "not-daily-yet"),
        *_route_frames(tmp_path, profile)[1:],
    ]
    port = Port(delayed)
    waits = []
    navigator = GuardedShopNavigation(
        port,
        profile,
        _home_detector,
        destination_observations=3,
        destination_wait_seconds=0.25,
        sleep=waits.append,
    )
    result = navigator.run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.SUCCESS
    assert len(port.taps) == 4
    assert waits == [0.25]


def test_destination_timeout_has_no_blind_retry(tmp_path):
    profile = _profile()
    port = Port([_frame(tmp_path, _image(profile.home_shop_entry), "home-before")])
    result = _navigator(port).run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.TIMEOUT
    assert result.actions == ["tap:home-shop-entry"]
    assert len(port.taps) == 1


def test_empty_initial_observation_is_bounded_timeout(tmp_path):
    result = _navigator(Port([])).run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.TIMEOUT
    assert result.actions == []


def test_boot_change_after_action_is_identity_failure(tmp_path):
    profile = _profile()
    changed = Target(2, "5-Emmmmm", TARGET.serial, "boot-changed")
    frames = _route_frames(tmp_path, profile)
    frames[2] = _frame(
        tmp_path,
        _image(profile.info_popup, profile.info_close),
        "popup-boot-changed",
        target=changed,
    )
    port = Port(frames)
    result = _navigator(port).run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.IDENTITY_MISMATCH
    assert len(port.taps) == 2


def test_generic_neighbor_exit_is_never_authorized_without_daily_identity(tmp_path):
    profile = _profile()
    frames = [
        _frame(tmp_path, _image(profile.home_shop_entry), "home-before"),
        _frame(tmp_path, _image(profile.daily_page, profile.info_button, profile.daily_exit), "daily-after-entry"),
        _frame(tmp_path, _image(profile.info_popup, profile.info_close), "popup-after-info"),
        _frame(tmp_path, _image(profile.daily_page, profile.info_button, profile.daily_exit), "daily-after-close"),
        _frame(tmp_path, _image(profile.daily_exit), "neighbor-with-generic-exit"),
    ]
    port = Port(frames)
    result = _navigator(port).run(*TARGET_MEMBER)

    assert result.status == ShopNavigationStatus.DESTINATION_UNVERIFIED
    assert len(port.taps) == 4

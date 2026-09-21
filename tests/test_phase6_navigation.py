from dataclasses import replace

import cv2
import numpy as np
import pytest

import top_heroes_auto.automation.phase6_navigation as navigation_module
from top_heroes_auto.adb.client import Target
from top_heroes_auto.automation.guard import RunSnapshot, SafetyError
from top_heroes_auto.automation.phase6_navigation import (
    EntryFrame,
    GuardedEntryNavigator,
    ManagerEntryPort,
    NavigationStatus,
    recruit_entry_profile,
    vip_entry_profile,
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

IDENTITY = Target(2, "5-Emmmmm", "emulator-5558", "70b1cc0e-24e0-4657-9e54-4025067f47aa")


def _anchor(tmp_path, anchor_id, state, seed):
    image = np.random.default_rng(seed).integers(1, 255, (14, 16, 3), dtype=np.uint8)
    path = tmp_path / f"{anchor_id}.png"
    assert cv2.imwrite(str(path), image)
    return VisualAnchor(anchor_id, state, path, NormalizedRect(0, 0, 1, 1), 0.95), image


def _capture(templates, present, *, stamp, target=IDENTITY, shift=0, duplicate=None):
    image = np.full((180, 320, 3), 18, dtype=np.uint8)
    positions = {name: (12 + n * 42 + shift, 20 + n * 18) for n, name in enumerate(templates)}
    for name in present:
        template = templates[name][1]
        x, y = positions[name]
        image[y:y + template.shape[0], x:x + template.shape[1]] = template
    if duplicate:
        template = templates[duplicate][1]
        image[140:140 + template.shape[0], 250:250 + template.shape[1]] = template
    return CapturedScreen(
        target.index,
        target.name,
        target.serial,
        target.boot_id,
        image,
        image,
        (320, 180),
        (320, 180),
        (1, 1),
        timestamp=stamp,
    )


class Port:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.taps = []

    def observe(self, tag):
        return next(self.frames)

    def tap(self, frame, point):
        self.taps.append((frame.capture_id, point))


def home_detector(screen):
    return ScreenDetection(ScreenState.GAME_HOME, 0.99, (), screen.timestamp, None, 1.0)


def unknown_detector(screen):
    return ScreenDetection(ScreenState.UNKNOWN, 0.99, (), screen.timestamp, None, 1.0)


def test_vip_route_uses_current_frame_and_fresh_destination(tmp_path):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 1)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 2)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, ("page",), stamp="vip")),
    ])
    result = GuardedEntryNavigator(port, vip_entry_profile(home, page), home_detector).run()
    assert result.status == NavigationStatus.SUCCESS
    assert result.actions == ["tap:home-vip-entry"]
    assert len(port.taps) == 1
    assert port.taps[0][1] != (0, 0)


def test_recruit_route_requires_selected_tavern_before_second_action(tmp_path):
    tavern, tavern_image = _anchor(tmp_path, "home-tavern", ScreenState.GAME_HOME, 3)
    selected, selected_image = _anchor(tmp_path, "tavern-selected-name", ScreenState.GAME_HOME, 4)
    entry, entry_image = _anchor(tmp_path, "tavern-recruit-entry", ScreenState.GAME_HOME, 5)
    page, page_image = _anchor(tmp_path, "recruit-page", ScreenState.FREE_REWARD_PAGE, 6)
    templates = {
        "tavern": (tavern, tavern_image),
        "selected": (selected, selected_image),
        "entry": (entry, entry_image),
        "page": (page, page_image),
    }
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("tavern",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, ("selected",), stamp="selected")),
        EntryFrame(IDENTITY, _capture(templates, ("page",), stamp="recruit")),
    ])
    result = GuardedEntryNavigator(
        port,
        recruit_entry_profile(tavern, selected, entry, page),
        home_detector,
    ).run()
    assert result.status == NavigationStatus.DESTINATION_UNVERIFIED
    assert result.actions == ["tap:home-tavern"]
    assert len(port.taps) == 1


def test_recruit_route_accepts_selected_name_before_recruit_action(tmp_path):
    tavern, tavern_image = _anchor(tmp_path, "home-tavern", ScreenState.GAME_HOME, 21)
    selected, selected_image = _anchor(tmp_path, "tavern-selected-name", ScreenState.GAME_HOME, 22)
    entry, entry_image = _anchor(tmp_path, "tavern-recruit-entry", ScreenState.GAME_HOME, 23)
    page, page_image = _anchor(tmp_path, "recruit-page", ScreenState.FREE_REWARD_PAGE, 24)
    templates = {
        "tavern": (tavern, tavern_image),
        "selected": (selected, selected_image),
        "entry": (entry, entry_image),
        "page": (page, page_image),
    }
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("tavern",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, ("selected", "entry"), stamp="selected")),
        EntryFrame(IDENTITY, _capture(templates, ("page",), stamp="recruit")),
    ])
    result = GuardedEntryNavigator(
        port,
        recruit_entry_profile(tavern, selected, entry, page),
        home_detector,
    ).run()
    assert result.status == NavigationStatus.SUCCESS
    assert result.actions == ["tap:home-tavern", "tap:tavern-recruit-entry"]
    assert len(port.taps) == 2


def test_cancellation_between_recruit_steps_dispatches_no_second_tap(tmp_path):
    tavern, tavern_image = _anchor(tmp_path, "home-tavern", ScreenState.GAME_HOME, 31)
    selected, selected_image = _anchor(tmp_path, "tavern-selected-name", ScreenState.GAME_HOME, 32)
    entry, entry_image = _anchor(tmp_path, "tavern-recruit-entry", ScreenState.GAME_HOME, 33)
    page, page_image = _anchor(tmp_path, "recruit-page", ScreenState.FREE_REWARD_PAGE, 34)
    templates = {
        "tavern": (tavern, tavern_image),
        "selected": (selected, selected_image),
        "entry": (entry, entry_image),
        "page": (page, page_image),
    }
    cancelled = False

    class CancellingPort(Port):
        def tap(self, frame, point):
            nonlocal cancelled
            super().tap(frame, point)
            cancelled = True

    port = CancellingPort([
        EntryFrame(IDENTITY, _capture(templates, ("tavern",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, ("selected", "entry"), stamp="selected")),
    ])
    result = GuardedEntryNavigator(
        port,
        recruit_entry_profile(tavern, selected, entry, page),
        home_detector,
    ).run(lambda: cancelled)
    assert result.status == NavigationStatus.CANCELLED
    assert result.actions == ["tap:home-tavern"]
    assert len(port.taps) == 1


@pytest.mark.parametrize("present,duplicate", [((), None), (("home",), "home")])
def test_missing_or_ambiguous_home_entry_dispatches_zero(tmp_path, present, duplicate):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 7)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 8)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, present, stamp="home", duplicate=duplicate)),
    ])
    result = GuardedEntryNavigator(port, vip_entry_profile(home, page), home_detector).run()
    assert result.status == NavigationStatus.BLOCKED
    assert not port.taps


def test_destination_missing_dispatches_once_and_never_retries(tmp_path):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 9)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 10)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, (), stamp="unknown")),
    ])
    result = GuardedEntryNavigator(port, vip_entry_profile(home, page), home_detector).run()
    assert result.status == NavigationStatus.DESTINATION_UNVERIFIED
    assert len(port.taps) == 1


def test_delayed_destination_is_observed_without_repeating_input(tmp_path):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 41)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 42)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, (), stamp="transition")),
        EntryFrame(IDENTITY, _capture(templates, ("page",), stamp="vip")),
    ])
    result = GuardedEntryNavigator(
        port,
        vip_entry_profile(home, page),
        home_detector,
        destination_observations=3,
        destination_wait_seconds=0,
    ).run()
    assert result.status == NavigationStatus.SUCCESS
    assert len(port.taps) == 1
    assert len(result.captures) == 3


def test_destination_observation_timeout_never_repeats_input(tmp_path):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 43)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 44)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, (), stamp="transition-1")),
        EntryFrame(IDENTITY, _capture(templates, (), stamp="transition-2")),
        EntryFrame(IDENTITY, _capture(templates, (), stamp="transition-3")),
    ])
    result = GuardedEntryNavigator(
        port,
        vip_entry_profile(home, page),
        home_detector,
        destination_observations=3,
        destination_wait_seconds=0,
    ).run()
    assert result.status == NavigationStatus.DESTINATION_UNVERIFIED
    assert "3 bounded observations" in result.error
    assert len(port.taps) == 1
    assert len(result.captures) == 4


def test_boot_change_during_delayed_destination_fails_closed(tmp_path):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 45)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 46)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    changed = replace(IDENTITY, boot_id="ce068632-fc3e-4090-a8d7-ae8d9fe353f5")
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, (), stamp="transition")),
        EntryFrame(changed, _capture(templates, ("page",), stamp="wrong-boot", target=changed)),
    ])
    result = GuardedEntryNavigator(
        port,
        vip_entry_profile(home, page),
        home_detector,
        destination_observations=3,
        destination_wait_seconds=0,
    ).run()
    assert result.status == NavigationStatus.DESTINATION_UNVERIFIED
    assert "identity changed" in result.error
    assert len(port.taps) == 1
    assert len(result.captures) == 2


def test_cancellation_during_delayed_destination_stops_observation(tmp_path):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 47)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 48)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    cancelled = False

    class CancellingDestinationPort(Port):
        def observe(self, tag):
            nonlocal cancelled
            frame = super().observe(tag)
            if tag == "vip-reward-after-step-1":
                cancelled = True
            return frame

    port = CancellingDestinationPort([
        EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, (), stamp="transition")),
        EntryFrame(IDENTITY, _capture(templates, ("page",), stamp="vip")),
    ])
    result = GuardedEntryNavigator(
        port,
        vip_entry_profile(home, page),
        home_detector,
        destination_observations=3,
        destination_wait_seconds=0,
    ).run(lambda: cancelled)
    assert result.status == NavigationStatus.CANCELLED
    assert len(port.taps) == 1
    assert len(result.captures) == 2


@pytest.mark.parametrize("score", [0.9449, 0.8363])
def test_surveyed_animated_tavern_matches_dispatch_zero(tmp_path, monkeypatch, score):
    home, home_image = _anchor(tmp_path, "home-tavern", ScreenState.GAME_HOME, 49)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 50)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    port = Port([EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home"))])

    def surveyed_match(screen, anchor):
        return AnchorEvidence(
            anchor.id,
            anchor.state,
            score,
            0.97,
            False,
        )

    monkeypatch.setattr(navigation_module, "unique_current_anchor", surveyed_match)
    result = GuardedEntryNavigator(port, vip_entry_profile(home, page), home_detector).run()
    assert result.status == NavigationStatus.BLOCKED
    assert not port.taps


def test_stable_tavern_match_dispatches_once(tmp_path, monkeypatch):
    home, home_image = _anchor(tmp_path, "home-tavern", ScreenState.GAME_HOME, 51)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 52)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home")),
        EntryFrame(IDENTITY, _capture(templates, ("page",), stamp="vip")),
    ])

    def stable_match(screen, anchor):
        return AnchorEvidence(
            anchor.id,
            anchor.state,
            0.9888,
            0.97,
            True,
            BoundingBox(12, 20, 16, 14),
            BoundingBox(12, 20, 16, 14),
        )

    monkeypatch.setattr(navigation_module, "unique_current_anchor", stable_match)
    result = GuardedEntryNavigator(port, vip_entry_profile(home, page), home_detector).run()
    assert result.status == NavigationStatus.SUCCESS
    assert len(port.taps) == 1


def test_tap_transport_error_is_uncertain_and_never_retried(tmp_path):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 17)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 18)
    templates = {"home": (home, home_image), "page": (page, page_image)}

    class FailingPort(Port):
        def tap(self, frame, point):
            raise OSError("transport lost after dispatch")

    port = FailingPort([
        EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home")),
    ])
    result = GuardedEntryNavigator(port, vip_entry_profile(home, page), home_detector).run()
    assert result.status == NavigationStatus.ACTION_RESULT_UNCERTAIN
    assert not port.taps


def test_boot_change_after_action_blocks_next_route_step(tmp_path):
    tavern, tavern_image = _anchor(tmp_path, "home-tavern", ScreenState.GAME_HOME, 11)
    selected, selected_image = _anchor(tmp_path, "tavern-selected-name", ScreenState.GAME_HOME, 12)
    entry, entry_image = _anchor(tmp_path, "tavern-recruit-entry", ScreenState.GAME_HOME, 13)
    page, page_image = _anchor(tmp_path, "recruit-page", ScreenState.FREE_REWARD_PAGE, 14)
    templates = {
        "tavern": (tavern, tavern_image),
        "selected": (selected, selected_image),
        "entry": (entry, entry_image),
        "page": (page, page_image),
    }
    changed = replace(IDENTITY, boot_id="ce068632-fc3e-4090-a8d7-ae8d9fe353f5")
    port = Port([
        EntryFrame(IDENTITY, _capture(templates, ("tavern",), stamp="home")),
        EntryFrame(changed, _capture(templates, ("selected",), stamp="selected", target=changed)),
    ])
    result = GuardedEntryNavigator(
        port,
        recruit_entry_profile(tavern, selected, entry, page),
        home_detector,
    ).run()
    assert result.status == NavigationStatus.DESTINATION_UNVERIFIED
    assert len(port.taps) == 1


def test_home_detector_unknown_dispatches_zero(tmp_path):
    home, home_image = _anchor(tmp_path, "home-vip-entry", ScreenState.GAME_HOME, 15)
    page, page_image = _anchor(tmp_path, "vip-page", ScreenState.FREE_REWARD_PAGE, 16)
    templates = {"home": (home, home_image), "page": (page, page_image)}
    port = Port([EntryFrame(IDENTITY, _capture(templates, ("home",), stamp="home"))])
    result = GuardedEntryNavigator(port, vip_entry_profile(home, page), unknown_detector).run()
    assert result.status == NavigationStatus.BLOCKED
    assert not port.taps


def test_manager_entry_port_rejects_wrong_index_before_decoding(tmp_path):
    class WrongManager:
        def capture_verified(self, index, snapshot):
            return Target(4, "3-Chíp", "emulator-5562", "ce068632-fc3e-4090-a8d7-ae8d9fe353f5"), b"not-a-png"

    port = ManagerEntryPort(
        WrongManager(),
        RunSnapshot("installation", ((2, "5-Emmmmm"),), True),
        2,
        "5-Emmmmm",
    )
    with pytest.raises(SafetyError, match="identity"):
        port.observe("home")

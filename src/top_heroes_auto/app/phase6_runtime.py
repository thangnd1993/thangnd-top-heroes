"""Production-safe Phase 6 visual factories.

This module composes the already verified current-frame adapters with the
packaged index-2 route anchors.  It never supplies coordinates directly:
``ManagerEntryPort`` and ``ManagerRewardPort`` derive every input point from
the frame immediately preceding that input and preserve the Manager target
identity checks.
"""

from __future__ import annotations

import sys
from pathlib import Path

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.phase6_navigation import (
    EntryProfile,
    GuardedEntryNavigator,
    ManagerEntryPort,
    recruit_entry_profile,
    vip_entry_profile,
)
from top_heroes_auto.automation.phase6_visual import ManagerRewardPort, RewardVisualProfile
from top_heroes_auto.vision.detector import ScreenDetector, load_anchors
from top_heroes_auto.vision.models import ScreenState, VisualAnchor
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.screenshot import ScreenshotService


def phase6_asset_root() -> Path:
    root = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
    return root / "assets" / "tasks" / "phase6"


def _anchor(folder: Path, anchor_id: str) -> VisualAnchor:
    matches = [item for item in load_anchors(folder) if item.id == anchor_id]
    if len(matches) != 1:
        raise SafetyError(f"Expected one independently verified Phase 6 anchor: {anchor_id!r}.")
    return matches[0]


def _entry_profile(task: str, reward_profile: RewardVisualProfile) -> EntryProfile:
    home = phase6_asset_root() / "home"
    page = reward_profile.anchor_map.get("page")
    if page is None:
        raise SafetyError("Reward destination anchor is unavailable.")
    if task == "vip-reward":
        return vip_entry_profile(_anchor(home, "home-vip-entry"), page)
    if task == "free-recruit":
        return recruit_entry_profile(
            _anchor(home, "home-tavern"),
            _anchor(home, "tavern-selected-name"),
            _anchor(home, "tavern-recruit-entry"),
            page,
        )
    raise SafetyError(f"No independently verified entry route exists for {task!r}.")


def entry_navigator_factory(manager, snapshot, index, name, profile, folder, cancelled=lambda: False):
    """Build and run one guarded Home-to-task route from current-frame anchors."""

    route = _entry_profile(profile.task, profile)
    port = ManagerEntryPort(manager, snapshot, index, name, folder)
    detector = ScreenDetector.from_folder(template_folder())
    return GuardedEntryNavigator(port, route, detector.detect).run(cancelled)


def reward_port_factory(manager, snapshot, index, name, profile, folder):
    """Build the reward port with a fresh, generic GAME_HOME cleanup verifier."""

    detector = ScreenDetector.from_folder(template_folder())

    def home_observer(expected_serial: str, expected_boot_id: str) -> bool:
        target, payload = manager.capture_verified(index, snapshot)
        if (target.index, target.name) != (index, name):
            raise SafetyError("Home cleanup capture identity changed.")
        if (target.serial, target.boot_id) != (expected_serial, expected_boot_id):
            return False
        captured = ScreenshotService(
            lambda serial: payload if serial == target.serial else b""
        ).take(target, folder, "phase6-home-verified")
        detection = detector.detect(captured)
        return detection.state == ScreenState.GAME_HOME and detection.confidence >= 0.9

    return ManagerRewardPort(
        manager,
        snapshot,
        index,
        name,
        profile,
        folder,
        home_observer=home_observer,
    )

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
from top_heroes_auto.automation.phase6_promo_recovery import (
    GuardedPromoRecovery,
    ManagerPromoRecoveryPort,
)
from top_heroes_auto.automation.phase6_shop import (
    ManagerShopSurveyPort,
    ShopProfileRegistry,
    ShopRouteRule,
    ShopSurveyEngine,
    ShopSurveyLimits,
    ShopVisualProfile,
)
from top_heroes_auto.automation.phase6_shop_navigation import (
    GuardedShopNavigation,
    ManagerShopNavigationPort,
    ShopNavigationProfile,
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
    return GuardedEntryNavigator(
        port,
        route,
        detector.detect,
        # A transition may need a few fresh captures.  This is observation
        # only: no action is retried and each frame remains target-bound.
        destination_observations=3,
        destination_wait_seconds=0.25,
    ).run(cancelled)


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


def shop_navigation_profile() -> ShopNavigationProfile:
    """Load the independently qualified, navigation-only shop profile."""

    shop = phase6_asset_root() / "shop"
    home = phase6_asset_root() / "home"
    return ShopNavigationProfile(
        home_shop_entry=_anchor(home, "home-shop-entry"),
        daily_page=_anchor(shop, "phase6-daily-page"),
        info_button=_anchor(shop, "phase6-daily-info-button"),
        info_popup=_anchor(shop, "phase6-daily-info-popup"),
        info_close=_anchor(shop, "phase6-daily-info-close"),
        daily_exit=_anchor(shop, "phase6-daily-exit"),
    )


def shop_navigation_factory(
    manager,
    snapshot,
    index,
    name,
    profile: ShopNavigationProfile,
    folder,
    cancelled=lambda: False,
):
    """Run the bounded daily-offer survey route; no reward adapter is built."""

    port = ManagerShopNavigationPort(manager, snapshot, index, name, folder)
    detector = ScreenDetector.from_folder(template_folder())
    return GuardedShopNavigation(
        port,
        profile,
        detector.detect,
        destination_observations=3,
        destination_wait_seconds=0.25,
    ).run(index, name, cancelled)


def pending_promo_anchor() -> VisualAnchor:
    """Return the qualified Stranger Things title for shop-only fallback."""

    return _anchor(phase6_asset_root() / "promo", "promo-stranger-title")


def shop_survey_registry() -> ShopProfileRegistry:
    """Load only the independently qualified Home/daily/help surfaces.

    No neighboring tab or scroll boundary is packaged: the resulting survey
    therefore reports ``PARTIAL`` even when this small route completes.  The
    profile is navigation-only and contains no reward or claim rule.
    """

    shop = phase6_asset_root() / "shop"
    home = phase6_asset_root() / "home"
    home_page = _anchor(template_folder() / "home", "home-bottom-navigation")
    daily_page = _anchor(shop, "phase6-daily-page")
    popup_page = _anchor(shop, "phase6-daily-info-popup")
    return ShopProfileRegistry(
        (
            ShopVisualProfile(
                "phase6-shop-survey",
                "game-home",
                (("page", home_page), ("shop-entry", _anchor(home, "home-shop-entry"))),
                routes=(
                    ShopRouteRule("home-shop-entry", "shop-entry", "daily-offer", "submenu"),
                ),
                coverage_known=False,
                claim_enabled=False,
                page_state=ScreenState.GAME_HOME,
            ),
            ShopVisualProfile(
                "phase6-shop-survey",
                "daily-offer",
                (
                    ("page", daily_page),
                    ("info-entry", _anchor(shop, "phase6-daily-info-button")),
                    ("exit", _anchor(shop, "phase6-daily-exit")),
                ),
                routes=(
                    ShopRouteRule("daily-info", "info-entry", "daily-info-popup", "submenu"),
                    ShopRouteRule("daily-exit", "exit", "game-home", "parent"),
                ),
                coverage_known=False,
                claim_enabled=False,
            ),
            ShopVisualProfile(
                "phase6-shop-survey",
                "daily-info-popup",
                (
                    ("page", popup_page),
                    ("close", _anchor(shop, "phase6-daily-info-close")),
                ),
                routes=(
                    ShopRouteRule("daily-info-close", "close", "daily-offer", "parent"),
                ),
                coverage_known=False,
                claim_enabled=False,
            ),
        )
    )


def shop_survey_factory(
    manager,
    snapshot,
    index,
    name,
    folder,
    cancelled=lambda: False,
    *,
    pending_promo_anchor: VisualAnchor | None = None,
    initial_promo_anchor: VisualAnchor | None = None,
    initial_promo_identity: tuple[str, str] | None = None,
    promo_budget_available: bool = False,
):
    """Run the bounded claim-free survey over qualified surfaces only."""

    registry = shop_survey_registry()
    port = ManagerShopSurveyPort(
        manager,
        snapshot,
        index,
        name,
        registry,
        folder,
        pending_promo_anchor=pending_promo_anchor,
        initial_promo_anchor=initial_promo_anchor,
        initial_promo_identity=initial_promo_identity,
        promo_budget_available=promo_budget_available,
    )
    return ShopSurveyEngine(
        ShopSurveyLimits(max_steps=12, max_depth=2, max_scrolls_per_direction=1, max_seconds=60.0)
    ).run(port, index, name, cancelled)


def promo_recovery_factory(
    manager,
    snapshot,
    index,
    name,
    folder,
    cancelled=lambda: False,
    *,
    expected_transport=None,
):
    """Recover only the known promo popup; no normal recovery fallback here."""

    promo = phase6_asset_root() / "promo"
    anchor = _anchor(promo, "promo-stranger-title")
    port = ManagerPromoRecoveryPort(manager, snapshot, index, name, folder)
    detector = ScreenDetector.from_folder(template_folder())
    return GuardedPromoRecovery(
        port,
        anchor,
        detector.detect,
        destination_observations=3,
        destination_wait_seconds=0.25,
    ).run(index, name, cancelled, expected_transport=expected_transport)

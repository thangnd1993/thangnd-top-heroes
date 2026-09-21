import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import CapturedScreen, ScreenState

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "tasks" / "phase6" / "shop"
EVIDENCE_ROOT = Path(
    os.environ.get(
        "THA_PHASE6_EVIDENCE_ROOT",
        r"C:\Users\ADMIN\AppData\Local\TopHeroesAutoManager\diagnostics\vision\5-Emmmmm",
    )
)
ANCHOR_IDS = {
    "phase6-daily-page",
    "phase6-daily-info-popup",
    "phase6-daily-info-close",
    "phase6-daily-exit",
}


def _anchors():
    return {anchor.id: anchor for anchor in load_anchors(ASSETS)}


def _synthetic(anchor, *, duplicate=False):
    template = cv2.imread(str(anchor.template), cv2.IMREAD_COLOR)
    assert template is not None
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    locations = {
        "phase6-daily-page": (1120, 0),
        "phase6-daily-info-popup": (1080, 100),
        "phase6-daily-info-close": (83, 320),
        "phase6-daily-exit": (0, 0),
    }
    x, y = locations[anchor.id]
    height, width = template.shape[:2]
    image[y : y + height, x : x + width] = template
    if duplicate:
        duplicate_locations = {
            "phase6-daily-page": (998, 0),
            "phase6-daily-info-popup": (930, 100),
            "phase6-daily-info-close": (240, 320),
            "phase6-daily-exit": (150, 0),
        }
        x, y = duplicate_locations[anchor.id]
        image[y : y + height, x : x + width] = template
    return CapturedScreen(
        2,
        "5-Emmmmm",
        "emulator-5558",
        "a475da84-8ba9-4e3f-947f-e0282791a39d",
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
    )


def test_daily_offer_assets_are_navigation_only():
    anchors = _anchors()
    assert set(anchors) == ANCHOR_IDS
    assert anchors["phase6-daily-page"].state == ScreenState.FREE_REWARD_PAGE
    assert anchors["phase6-daily-info-popup"].state == ScreenState.POPUP_GENERIC
    assert anchors["phase6-daily-info-close"].state == ScreenState.POPUP_GENERIC
    assert anchors["phase6-daily-exit"].state == ScreenState.FREE_REWARD_PAGE
    assert all(anchor.threshold == pytest.approx(0.97) for anchor in anchors.values())
    assert all("claim" not in anchor.id and "reward" not in anchor.id for anchor in anchors.values())


@pytest.mark.parametrize("anchor_id", sorted(ANCHOR_IDS))
def test_daily_offer_assets_require_unique_current_frame(anchor_id):
    anchor = _anchors()[anchor_id]
    evidence = unique_current_anchor(_synthetic(anchor), anchor)
    assert evidence.matched
    assert evidence.score >= anchor.threshold
    duplicate = unique_current_anchor(_synthetic(anchor, duplicate=True), anchor)
    assert not duplicate.matched


@pytest.mark.parametrize("anchor_id", sorted(ANCHOR_IDS))
def test_daily_offer_assets_reject_other_navigation_surfaces(anchor_id):
    anchors = _anchors()
    anchor = anchors[anchor_id]
    other = next(item for item in anchors.values() if item.id != anchor_id)
    assert not unique_current_anchor(_synthetic(other), anchor).matched


def _saved_screen(path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert image is not None
    return CapturedScreen(
        2,
        "5-Emmmmm",
        "emulator-5558",
        "a475da84-8ba9-4e3f-947f-e0282791a39d",
        image,
        image,
        (1280, 720),
        (1280, 720),
        (1.0, 1.0),
        source_image=path,
    )


@pytest.mark.skipif(not EVIDENCE_ROOT.exists(), reason="index-2 diagnostic captures are not available")
@pytest.mark.parametrize(
    ("anchor_id", "positive_stems"),
    [
        (
            "phase6-daily-page",
            (
                "20260921-173758-972814Z-phase6-20260922-shop-entry-after",
                "20260921-173846-143161Z-phase6-20260922-daily-info-before",
                "20260921-173955-365363Z-phase6-20260922-info-close-after",
            ),
        ),
        (
            "phase6-daily-info-popup",
            (
                "20260921-173850-589371Z-phase6-20260922-daily-info-after",
                "20260921-173950-840227Z-phase6-20260922-info-close-before",
            ),
        ),
        (
            "phase6-daily-info-close",
            (
                "20260921-173850-589371Z-phase6-20260922-daily-info-after",
                "20260921-173950-840227Z-phase6-20260922-info-close-before",
            ),
        ),
        (
            "phase6-daily-exit",
            (
                "20260921-173758-972814Z-phase6-20260922-shop-entry-after",
                "20260921-173846-143161Z-phase6-20260922-daily-info-before",
                "20260921-173955-365363Z-phase6-20260922-info-close-after",
            ),
        ),
    ],
)
def test_saved_index2_frames_match_only_the_qualified_navigation_surface(anchor_id, positive_stems):
    anchor = _anchors()[anchor_id]
    for stem in positive_stems:
        evidence = unique_current_anchor(_saved_screen(EVIDENCE_ROOT / f"{stem}.png"), anchor)
        assert evidence.matched, (anchor_id, stem, evidence.as_dict())
        assert evidence.score >= anchor.threshold

    negatives = (
        "20260921-173502-952419Z-phase6-20260922-fresh-home-before",
        "20260921-173703-800199Z-phase6-20260922-promo-before",
        "20260921-173754-456023Z-phase6-20260922-shop-entry-before",
        "20260921-174127-641081Z-phase6-20260922-vip-current-before",
    )
    for stem in negatives:
        evidence = unique_current_anchor(_saved_screen(EVIDENCE_ROOT / f"{stem}.png"), anchor)
        assert not evidence.matched, (anchor_id, stem, evidence.as_dict())

    same_shop_negatives = {
        "phase6-daily-page": (
            "20260920-173247-648785Z-phase6-weekly-pack-top-before",
            "20260920-174052-458281Z-phase6-shop-monthly-card-before",
            "20260920-175319-460676Z-phase6-diamond-shop-before",
            "20260921-173850-589371Z-phase6-20260922-daily-info-after",
        ),
        "phase6-daily-exit": (
            "20260921-173850-589371Z-phase6-20260922-daily-info-after",
        ),
        "phase6-daily-info-popup": (
            "20260921-173758-972814Z-phase6-20260922-shop-entry-after",
            "20260921-173846-143161Z-phase6-20260922-daily-info-before",
            "20260921-173955-365363Z-phase6-20260922-info-close-after",
        ),
        "phase6-daily-info-close": (
            "20260921-173758-972814Z-phase6-20260922-shop-entry-after",
            "20260921-173846-143161Z-phase6-20260922-daily-info-before",
            "20260921-173955-365363Z-phase6-20260922-info-close-after",
        ),
    }
    for stem in same_shop_negatives[anchor_id]:
        evidence = unique_current_anchor(_saved_screen(EVIDENCE_ROOT / f"{stem}.png"), anchor)
        assert not evidence.matched, (anchor_id, stem, evidence.as_dict())


@pytest.mark.skipif(not EVIDENCE_ROOT.exists(), reason="index-2 diagnostic captures are not available")
def test_daily_exit_is_gated_by_daily_page_identity():
    anchors = _anchors()
    neighboring_tab = _saved_screen(
        EVIDENCE_ROOT / "20260920-173247-648785Z-phase6-weekly-pack-top-before.png"
    )
    # The back arrow is intentionally generic and matches this neighboring
    # tab; only the independently verified daily-page identity can authorize
    # treating it as the daily-page exit action.
    assert unique_current_anchor(neighboring_tab, anchors["phase6-daily-exit"]).matched
    assert not unique_current_anchor(neighboring_tab, anchors["phase6-daily-page"]).matched

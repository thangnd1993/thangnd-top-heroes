from dataclasses import replace

import cv2
import pytest
import test_event_paid_modal as original

from top_heroes_auto.vision.event_paid_modal import paid_modal_navigation


@pytest.mark.parametrize("name", ["paid-multi-old", "paid-multi-current"])
def test_price_and_art_variants_allow_only_owned_close(name):
    im = original.image(name)
    result = paid_modal_navigation(im)
    assert result and not result["claim_authorized"] and not result["coverage_known"]
    assert result["permission"] == "NAVIGATION_ONLY"
    b = result["close"]
    paid = result["paid_region"]
    assert b.y + b.height < paid.y
    moved = im.copy()
    patch = im[b.y : b.y + b.height, b.x : b.x + b.width].copy()
    moved[b.y : b.y + b.height, b.x : b.x + b.width] = 0
    moved[b.y + 4 : b.y + 4 + b.height, b.x - 5 : b.x - 5 + b.width] = patch
    assert paid_modal_navigation(moved)["close"] == replace(b, x=b.x - 5, y=b.y + 4)


@pytest.mark.parametrize("role", ["close", "label", "currency", "duplicate-close"])
def test_incomplete_or_conflicting_multi_offer_cannot_close(role):
    im = original.image("paid-multi-current")
    if role == "close":
        im[115:160, 638:682] = 0
    if role == "label":
        im[558:592, 87:210] = 0
    if role == "currency":
        im[658:680, 470:522] = 0
    if role == "duplicate-close":
        im[350:395, 300:344] = im[115:160, 638:682].copy()
    assert paid_modal_navigation(im) is None


def test_production_multi_offer_has_no_claim_controls_and_consumes_close(tmp_path, monkeypatch):
    im = original.image("paid-multi-current")
    monkeypatch.setattr(original, "image", lambda: im)
    p, sent = original.port(tmp_path, monkeypatch)
    frame = p.observe()
    assert frame.page.endswith(":paid-modal") and frame.controls == ()
    assert frame.parent and not frame.coverage_known
    p.navigate(frame, frame.parent)
    assert len(sent) == 1 and sent[0][1:] == ("tap", frame.parent.box.center)


def test_unrelated_green_reward_and_home_cannot_become_paid_close():
    for name in ("inline-objective-free", "menu-mixed-width", "home-entry-jitter-a"):
        assert paid_modal_navigation(cv2.imread("tests/fixtures/phase8/" + name + ".png")) is None


def test_other_qualified_close_raster_is_conflicting():
    im = original.image("paid-multi-current")
    older = original.image("paid-offer-one")
    b = paid_modal_navigation(older)["close"]
    im[350 : 350 + b.height, 300 : 300 + b.width] = older[b.y : b.y + b.height, b.x : b.x + b.width]
    assert paid_modal_navigation(im) is None

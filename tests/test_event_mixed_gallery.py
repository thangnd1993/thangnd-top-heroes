"""Mixed-width current Event gallery remains navigation-only."""

from dataclasses import replace

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import discover_menu_tiles, event_body_contract, menu_card_boxes


def image():
    return cv2.imread("tests/fixtures/phase8/menu-mixed-width.png")


def body(im, words="20 Ngay 20 Ngay"):
    return event_body_contract(
        im, (), cv2.imread("assets/tasks/phase8/personal-task-tab.png"), reader=lambda _: [{"text": words}]
    )


def test_full_width_cards_share_current_half_width_gallery_structure():
    im = image()
    cards = menu_card_boxes(im)
    assert len(cards) == 4
    assert len([b for b in cards if b.width > im.shape[1] * 0.85]) == 2
    assert body(im) == "MENU_GRID"
    # The badge-bearing bottom card is clipped, so no child/claim is exposed yet.
    assert not discover_menu_tiles(im)
    moved = cv2.warpAffine(im, np.float32([[1, 0, 3], [0, 1, 5]]), (720, 1280))
    assert set(menu_card_boxes(moved)) == {replace(b, x=b.x + 3, y=b.y + 5) for b in cards}
    assert body(moved) == "MENU_GRID"


def test_large_artwork_without_the_paired_gallery_structure_is_not_navigation():
    im = image()
    im[714:1005] = 0
    assert not menu_card_boxes(im)
    assert body(im) == "UNSUPPORTED"


def test_mixed_gallery_does_not_qualify_paid_free_or_unreadable_content():
    for text in ("20 Ngay 20 Ngay VND", "20 Ngay 20 Ngay Nhận", "20 Ngay 20 Ngay Mua Ngay", ""):
        assert body(image(), text) == "UNSUPPORTED"
    im = image()
    cv2.rectangle(im, (200, 200), (430, 270), (0, 180, 255), -1)
    assert body(im) == "UNSUPPORTED"

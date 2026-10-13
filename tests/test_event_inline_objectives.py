"""Saved inline free objective, geometry/cost negatives and conservative post-condition."""

import json
from dataclasses import asdict, replace

import cv2
import numpy as np
import pytest

from top_heroes_auto.app.event_claim_reconciliation import bind_saved_rewards
from top_heroes_auto.vision.event_inline_objectives import inline_objective_rows


def image():
    return cv2.imread("tests/fixtures/phase8/inline-objective-free.png")


def reader(crop, *, fraction="1/1", label="nhan"):
    return [
        {"text": f"Hoan thanh 1 lan thu thap mo sa thach ({fraction})" if crop.shape[1] > 1000 else label}
    ]


def test_current_unique_completed_objective_reacquires_moved_bbox():
    im = image()
    rows = inline_objective_rows(im, reader=reader)
    assert len(rows) == 1 and rows[0]["state"] == "AVAILABLE"
    b = rows[0]["box"]
    r = rows[0]["row"]
    assert r.x < b.center[0] < r.x + r.width and r.y < b.center[1] < r.y + r.height
    moved = cv2.warpAffine(im, np.float32([[1, 0, 4], [0, 1, 6]]), (720, 1280))
    new = inline_objective_rows(moved, reader=reader)
    assert len(new) == 1 and new[0]["state"] == "AVAILABLE"
    assert new[0]["box"] == replace(b, x=b.x + 4, y=b.y + 6)
    assert new[0]["identity"] == rows[0]["identity"]


@pytest.mark.parametrize("fraction", ["0/1", "1/0", "2/1", "?/?"])
def test_incomplete_or_ambiguous_progress_cannot_claim(fraction):
    assert not any(
        r["state"] == "AVAILABLE"
        for r in inline_objective_rows(image(), reader=lambda c: reader(c, fraction=fraction))
    )


@pytest.mark.parametrize("label", ["nhan 10", "10 VND", "mua ngay", "", "nhan mien phi 20"])
def test_any_extra_or_unreadable_cost_text_rejected(label):
    assert not any(
        r["state"] == "AVAILABLE"
        for r in inline_objective_rows(image(), reader=lambda c: reader(c, label=label))
    )


def test_currency_icon_duplicate_caption_and_missing_items_fail_closed():
    im = image()
    cv2.circle(im, (510, 850), 13, (220, 20, 220), -1)
    assert not any(r["state"] == "AVAILABLE" for r in inline_objective_rows(im, reader=reader))
    im = image()
    im[520:672] = im[757:909].copy()
    assert not any(r["state"] == "AVAILABLE" for r in inline_objective_rows(im, reader=reader))
    im = image()
    im[811:902, 45:145] = 0
    im[811:902, 240:442] = 0
    assert not inline_objective_rows(im, reader=reader)


@pytest.mark.parametrize("name", ["paid-offer-one", "home-entry-jitter-a", "menu-mixed-width"])
def test_unrelated_ui_has_no_inline_claim(name):
    im = cv2.imread("tests/fixtures/phase8/" + name + ".png")
    assert not any(r["state"] == "AVAILABLE" for r in inline_objective_rows(im, reader=reader))


def test_saved_uncertain_inline_caption_keeps_same_lock(tmp_path):
    im = image()
    row = inline_objective_rows(im, reader=reader)[0]
    p = tmp_path / "saved.png"
    cv2.imwrite(str(p), im)
    p.with_suffix(".event.json").write_text(
        json.dumps({"reward_rows": [{**row, "row": asdict(row["row"]), "box": asdict(row["box"])}]})
    )
    claim = dict(
        reward_id="event:original",
        status="RESERVED",
        dispatch_state="POSSIBLE",
        after_evidence="[]",
        before_evidence=json.dumps(
            dict(
                persistent_identity="disk",
                identity=[13, "disk", "explicit", "boot"],
                event="current",
                page="event:current:inline-objectives",
                reward=row["identity"],
                capture=str(p),
                evidence=row["evidence"],
            )
        ),
    )
    current = dict(row, identity="new-raster-key")
    bound = bind_saved_rewards(
        im, [current], [claim], persistent_identity="disk", index=13, family="inline-objectives"
    )
    assert bound[0]["identity"] == row["identity"]


@pytest.mark.parametrize("explicit", [True, False])
def test_inline_needs_two_explicit_underlying_claimed_frames(monkeypatch, explicit):
    from test_event_postcondition_capture import frame, harness

    evidence = (
        ("explicit-claimed-label", "original-green-control-absent") if explicit else ("unmet-objective",)
    )
    p, target, _, _ = harness(
        monkeypatch,
        [frame(n) for n in range(7)],
        [dict(identity="reward", state="NOT_AVAILABLE", evidence=evidence)],
    )
    target = replace(target, evidence=("qualified-inline-objectives",))
    proof = p._claim_postcondition(frame("before"), target, "current")
    assert len(proof) == (2 if explicit else 0)


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows OCR")
def test_real_saved_frame_ocr_proves_only_nhan_and_completed_fraction():
    from top_heroes_auto.vision.local_ocr import read_words

    rows = inline_objective_rows(image(), reader=read_words)
    assert len(rows) == 1 and rows[0]["state"] == "AVAILABLE"

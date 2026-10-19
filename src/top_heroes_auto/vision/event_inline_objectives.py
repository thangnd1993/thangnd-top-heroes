"""Inline objective rewards: current inventory tiles, completed fraction and sole free label."""

import hashlib
import re
from collections import Counter

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import folded
from top_heroes_auto.vision.models import BoundingBox


def objective_label_glyph(image, row):
    crop = image[row.y : row.y + round(row.height * 0.36), row.x + 6 : row.x + row.width - 6]
    mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (0, 0, 180), (179, 110, 255))
    # Public group-buy objectives use brown captions on a pale card. This
    # glyph excludes green progress; the paired titles/caption prove the schema.
    if np.mean(mask>0)>.35:
        mask=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),(0,85,40),(25,255,190))
    # Only white objective text: green/red progress numbers are separate evidence.
    points = cv2.findNonZero(mask)
    if points is None or len(points) < 150:
        return None
    x, y, w, h = cv2.boundingRect(points)
    return cv2.resize(mask[y : y + h, x : x + w], (480, 40), interpolation=cv2.INTER_NEAREST)


def inline_objective_rows(image, *, reader):
    from top_heroes_auto.vision.event_group_buy import group_buy_rows

    public=group_buy_rows(image,reader=reader,glyph_reader=objective_label_glyph)
    if public:
        return public
    h, w = image.shape[:2]
    edge = cv2.Canny(image, 40, 120)
    contours = cv2.findContours(edge, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
    tiles = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if (
            0.09 * w < bw < 0.14 * w
            and 0.92 < bw / bh < 1.08
            and h * 0.4 < y
            and y + bh < h * 0.84
            and x < w * 0.65
            and cv2.contourArea(c) / (bw * bh) > 0.88
            and not any(abs(x - b.x) < 6 and abs(y - b.y) < 6 for b in tiles)
        ):
            tiles.append(BoundingBox(x, y, bw, bh))
    panels = []
    edges = cv2.morphologyEx(edge, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    for c in cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(c)
        if 0.9 * w < bw < 0.99 * w and 0.7 * h < bh < 0.87 * h and cv2.contourArea(c) / (bw * bh) > 0.98:
            panels.append(BoundingBox(x, y, bw, bh))
    if not panels:
        return ()
    panel = min(panels, key=lambda b: b.width * b.height)
    rows = []
    used = set()
    for tile in sorted(tiles, key=lambda b: (b.y, b.x)):
        if tile in used:
            continue
        group = sorted(
            [b for b in tiles if abs(b.y - tile.y) < 5 and abs(b.height - tile.height) < 5], key=lambda b: b.x
        )
        used.update(group)
        if len(group) < 3 or any(
            not 0.95 * tile.width < b.x - a.x < 2.3 * tile.width for a, b in zip(group, group[1:])
        ):
            continue
        left = group[0].x - 8
        right = panel.x + panel.width - round(w * 0.04)
        top = tile.y - round(tile.height * 0.6)
        bottom = tile.y + tile.height + 8
        row = BoundingBox(left, top, right - left, bottom - top)
        if left < panel.x or bottom > panel.y + panel.height or row.width < w * 0.75:
            continue
        header = image[top : tile.y - 5, left:right]
        texts = [
            folded(" ".join(q["text"] for q in reader(cv2.resize(header, None, fx=s, fy=s)))) for s in (2, 3)
        ]
        fractions = [re.findall(r"(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)", t) for t in texts]
        if (
            len(fractions[0]) != 1
            or fractions[0] != fractions[1]
            or any(sum(c.isalpha() for c in t) < 15 for t in texts)
        ):
            continue
        current, goal = map(int, fractions[0][0])
        if goal < 1 or current > goal:
            continue
        glyph = objective_label_glyph(image, row)
        if glyph is None:
            continue
        column = BoundingBox(
            group[-1].x + group[-1].width + round(tile.width * 0.25),
            tile.y,
            right - group[-1].x - group[-1].width - round(tile.width * 0.25),
            tile.height,
        )
        if column.width < tile.width * 1.5:
            continue
        crop = image[column.y : column.y + column.height, column.x : column.x + column.width]
        green = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (35, 60, 80), (85, 255, 255))
        buttons = []
        for c in cv2.findContours(green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x, y, bw, bh = cv2.boundingRect(c)
            if (
                bw > column.width * 0.75
                and tile.height * 0.6 < bh < tile.height * 0.95
                and cv2.contourArea(c) / (bw * bh) > 0.9
            ):
                buttons.append(BoundingBox(column.x + x, column.y + y, bw, bh))
        state = "UNKNOWN"
        box = column
        evidence = (
            "qualified-inline-objectives",
            "complete-reward-card",
            "inventory-reward-items",
            "independent-objective-caption",
        )
        if len(buttons) == 1 and current == goal:
            b = buttons[0]
            inside = image[b.y + 5 : b.y + b.height - 5, b.x + 5 : b.x + b.width - 5]
            hsv = cv2.cvtColor(inside, cv2.COLOR_BGR2HSV)
            foreign = (
                (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 120) & ((hsv[:, :, 0] < 30) | (hsv[:, :, 0] > 85))
            )
            white = cv2.inRange(hsv, (0, 0, 185), (179, 90, 255))
            rendered = cv2.copyMakeBorder(
                cv2.cvtColor(255 - white, cv2.COLOR_GRAY2BGR),
                15,
                15,
                15,
                15,
                cv2.BORDER_CONSTANT,
                value=(255, 255, 255),
            )
            # Remove only the local outline of the independently read caption.
            # Colored currency elsewhere and extra cost text still reject it.
            foreign &= cv2.dilate(white, np.ones((5, 5), np.uint8)) == 0
            labels = [
                folded(" ".join(q["text"] for q in reader(cv2.resize(rendered, None, fx=s, fy=s))))
                for s in (1, 2)
            ]
            if labels == ["nhan", "nhan"] and np.mean(foreign) < 0.015:
                state = "AVAILABLE"
                box = b
                evidence += (
                    "qualified-control-color",
                    "completed-objective-fraction",
                    "sole-no-cost-claim-label",
                )
        elif not np.count_nonzero(green):
            labels = [
                folded(" ".join(q["text"] for q in reader(cv2.resize(crop, None, fx=s, fy=s))))
                for s in (2, 3)
            ]
            if labels == ["da nhan", "da nhan"]:
                state = "NOT_AVAILABLE"
                evidence += ("explicit-claimed-label", "original-green-control-absent")
            elif current < goal and labels == ["chua dat", "chua dat"]:
                state = "NOT_AVAILABLE"
                evidence += ("unmet-objective",)
        rows.append(
            dict(
                identity=hashlib.sha256(glyph.tobytes()).hexdigest(),
                row=row,
                box=box,
                state=state,
                evidence=evidence,
            )
        )
    counts = Counter(r["identity"] for r in rows)
    for r in rows:
        if counts[r["identity"]] != 1:
            r["state"] = "UNKNOWN"
    return tuple(rows)

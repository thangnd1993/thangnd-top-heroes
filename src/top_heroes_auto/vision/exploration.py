"""Current-frame visual primitives for reward exploration.

These primitives find evidence, not permission to interact. A screen-specific
adapter must associate a candidate with a known safe menu/action before dispatch.
"""

from __future__ import annotations

import hashlib

import cv2
import numpy as np

from top_heroes_auto.vision.models import (
    AnchorEvidence,
    BoundingBox,
    CapturedScreen,
    NormalizedRect,
    VisualAnchor,
)


def content_fingerprint(screen: CapturedScreen, regions: tuple[NormalizedRect, ...]) -> str:
    """Hash declared content regions, excluding clocks/animations via the adapter.

    Exact hashes deliberately err toward additional bounded observations instead
    of treating similar-looking, different rewards as already inspected content.
    Callers include semantic page/tab identity separately in their visited key.
    """
    if not regions:
        raise ValueError("Known content regions are required for a fingerprint.")
    height, width = screen.normalized.shape[:2]
    digest = hashlib.sha256()
    for region in regions:
        left, top, right, bottom = region.pixels(width, height)
        crop = screen.normalized[top:bottom, left:right]
        digest.update(str((left, top, right, bottom, crop.shape)).encode("ascii"))
        digest.update(crop.tobytes())
    return digest.hexdigest()


def unique_current_anchor(screen: CapturedScreen, anchor: VisualAnchor) -> AnchorEvidence:
    """Search the current account image; reject two spatially distinct matches.

    Movable building adapters should use the whole game viewport as expected_region.
    No account's previous coordinates participate in this search. Scores within one
    template footprint are suppressed so adjacent pixels of one match do not count
    as distinct candidates.
    """
    template = cv2.imdecode(np.frombuffer(anchor.template.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError("Anchor template cannot be decoded.")
    height, width = screen.normalized.shape[:2]
    left, top, right, bottom = anchor.expected_region.pixels(width, height)
    region = screen.normalized[top:bottom, left:right]
    th, tw = template.shape[:2]
    if th > region.shape[0] or tw > region.shape[1] or float(template.std()) < 1:
        return AnchorEvidence(anchor.id, anchor.state, 0, anchor.threshold, False)
    scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(scores)
    threshold = max(0.9, anchor.threshold)
    if not np.isfinite(score) or score < threshold:
        return AnchorEvidence(anchor.id, anchor.state, float(score), threshold, False)
    # Even a partly overlapping duplicate must not silently choose a target.
    scores[max(0, y - th // 2):y + th // 2 + 1, max(0, x - tw // 2):x + tw // 2 + 1] = -1
    if float(scores.max()) >= threshold:
        return AnchorEvidence(anchor.id, anchor.state, float(score), threshold, False)
    box = BoundingBox(left + x, top + y, tw, th)
    return AnchorEvidence(anchor.id, anchor.state, float(score), threshold, True, box, screen.to_device_box(box))


def red_dot_candidates(screen: CapturedScreen, region: NormalizedRect) -> tuple[BoundingBox, ...]:
    """Return red circular discovery candidates only; never action anchors."""
    height, width = screen.normalized.shape[:2]
    left, top, right, bottom = region.pixels(width, height)
    hsv = cv2.cvtColor(screen.normalized[top:bottom, left:right], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 130, 140), (10, 255, 255)) | cv2.inRange(hsv, (170, 130, 140), (179, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if (6 <= w <= 48 and 6 <= h <= 48 and 0.65 <= w / h <= 1.5
                and perimeter and 4 * np.pi * area / perimeter ** 2 >= 0.55):
            found.append(BoundingBox(left + x, top + y, w, h))
    return tuple(sorted(found, key=lambda box: (box.y, box.x)))

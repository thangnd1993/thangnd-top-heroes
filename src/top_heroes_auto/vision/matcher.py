from __future__ import annotations

import cv2

from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, CapturedScreen, VisualAnchor


def match_anchor(screen: CapturedScreen, anchor: VisualAnchor) -> AnchorEvidence:
    template = cv2.imread(str(anchor.template), cv2.IMREAD_COLOR)
    if template is None or template.size == 0:
        raise ValueError(f"Template cannot be decoded: {anchor.template}")
    height, width = screen.normalized.shape[:2]
    left, top, right, bottom = anchor.expected_region.pixels(width, height)
    region = screen.normalized[top:bottom, left:right]
    template_height, template_width = template.shape[:2]
    if template_width > region.shape[1] or template_height > region.shape[0]:
        return AnchorEvidence(anchor.id, anchor.state, 0.0, anchor.threshold, False)
    scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, location = cv2.minMaxLoc(scores)
    box = BoundingBox(left + location[0], top + location[1], template_width, template_height)
    return AnchorEvidence(
        anchor.id,
        anchor.state,
        float(score),
        anchor.threshold,
        float(score) >= anchor.threshold,
        box,
        screen.to_device_box(box),
    )

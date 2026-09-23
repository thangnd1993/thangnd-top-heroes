"""Screenshot-derived VIP claim geometry and review overlay helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import BoundingBox


@dataclass(frozen=True)
class VipClaimGeometry:
    claim_box: BoundingBox
    tap_point: tuple[int, int]
    forbidden_boxes: tuple[BoundingBox, ...]


def boxes_intersect(first: BoundingBox, second: BoundingBox) -> bool:
    return not (
        first.x + first.width <= second.x
        or second.x + second.width <= first.x
        or first.y + first.height <= second.y
        or second.y + second.height <= first.y
    )


def point_inside(box: BoundingBox, point: tuple[int, int]) -> bool:
    x, y = point
    return box.x <= x < box.x + box.width and box.y <= y < box.y + box.height


def validate_vip_claim_geometry(
    claim_box: BoundingBox,
    tap_point: tuple[int, int],
    forbidden_boxes: tuple[BoundingBox, ...],
) -> VipClaimGeometry:
    """Require a center tap inside the fresh allowed box, clear of paid UI."""

    if claim_box.width <= 0 or claim_box.height <= 0 or tap_point != claim_box.center:
        raise SafetyError("VIP tap point must be the center of the current claim bbox.")
    if not point_inside(claim_box, tap_point):
        raise SafetyError("VIP tap point is outside the allowed claim bbox.")
    if not forbidden_boxes:
        raise SafetyError("VIP paid-region evidence is missing; claim is blocked.")
    if any(boxes_intersect(claim_box, forbidden) for forbidden in forbidden_boxes):
        raise SafetyError("VIP free claim bbox intersects a forbidden paid region.")
    if any(point_inside(forbidden, tap_point) for forbidden in forbidden_boxes):
        raise SafetyError("VIP tap point intersects a forbidden paid region.")
    return VipClaimGeometry(claim_box, tap_point, forbidden_boxes)


def write_vip_geometry_overlay(
    home_image: np.ndarray,
    vip_image: np.ndarray,
    entry_box: BoundingBox,
    claim_box: BoundingBox,
    normalized_tap_point: tuple[int, int],
    adb_tap_point: tuple[int, int],
    paid_boxes: tuple[BoundingBox, ...],
    path: Path,
) -> Path:
    """Save a two-frame overlay with current-frame boxes and the exact ADB tap."""

    if home_image.ndim != 3 or vip_image.ndim != 3 or home_image.size == 0 or vip_image.size == 0:
        raise OSError("VIP geometry overlay requires two decoded screenshots.")
    height = max(home_image.shape[0], vip_image.shape[0])

    def panel(image: np.ndarray, title: str) -> np.ndarray:
        if image.shape[0] != height:
            scale = height / image.shape[0]
            image = cv2.resize(image, (round(image.shape[1] * scale), height))
        header = np.zeros((42, image.shape[1], 3), dtype=np.uint8)
        cv2.putText(header, title, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (245, 245, 245), 2)
        return np.vstack((header, image.copy()))

    left = panel(home_image, "Current Home: detected VIP entry")
    right = panel(vip_image, "Current VIP: free target, paid exclusion, tap")
    left_shift, right_shift = 42, 42

    cv2.rectangle(
        left,
        (entry_box.x, entry_box.y + left_shift),
        (entry_box.x + entry_box.width, entry_box.y + entry_box.height + left_shift),
        (30, 220, 40),
        3,
    )
    cv2.putText(
        left,
        "VIP entry",
        (entry_box.x, max(left_shift + 18, entry_box.y + left_shift - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (30, 220, 40),
        2,
    )

    cv2.rectangle(
        right,
        (claim_box.x, claim_box.y + right_shift),
        (claim_box.x + claim_box.width, claim_box.y + claim_box.height + right_shift),
        (30, 220, 40),
        3,
    )
    for forbidden in paid_boxes:
        cv2.rectangle(
            right,
            (forbidden.x, forbidden.y + right_shift),
            (forbidden.x + forbidden.width, forbidden.y + forbidden.height + right_shift),
            (30, 30, 240),
            3,
        )
    point = normalized_tap_point[0], normalized_tap_point[1] + right_shift
    cv2.drawMarker(right, point, (0, 230, 255), cv2.MARKER_CROSS, 22, 3)
    cv2.putText(
        right,
        f"ADB tap {adb_tap_point}; inside free bbox; outside paid region",
        (12, right.shape[0] - 14),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (0, 230, 255),
        2,
    )
    canvas = np.hstack((left, right))
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded, payload = cv2.imencode(".png", canvas)
    if not encoded:
        raise OSError(f"Cannot encode VIP geometry overlay: {path}")
    path.write_bytes(payload.tobytes())
    return path

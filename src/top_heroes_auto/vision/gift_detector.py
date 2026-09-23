"""Strict pose-invariant matching for the rocking annotated VIP gift icon."""

from dataclasses import replace

import cv2
import numpy as np

from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, NormalizedRect
from top_heroes_auto.vision.resources import template_folder


def gift_anchor_match(screen, anchor):
    if anchor.id not in {"gift-core", "gift-coins"}:
        return unique_current_anchor(screen, anchor)
    badge_anchor = next(a for a in load_anchors(template_folder().parent / "tasks/phase6/vip-gift")
                        if a.id == "gift-badge")
    badge = unique_current_anchor(screen, badge_anchor)
    if badge.matched and badge.normalized_box is not None:
        # Search around a CURRENT unique badge, never an account's stored location.
        box = badge.normalized_box
        width, height = screen.normalized_size
        radius = max(box.width, box.height) * 5
        cx, cy = box.center
        anchor = replace(anchor, expected_region=NormalizedRect(
            max(0, cx-radius)/width, max(0, cy-radius)/height,
            min(width, cx+radius)/width, min(height, cy+radius)/height))
    return unique_pose_anchor(screen, anchor)


def unique_pose_anchor(screen, anchor):
    """Bounded ±20° / ±5% pose bank; distinct qualified locations fail closed."""
    template = cv2.imdecode(np.frombuffer(anchor.template.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if template is None:
        raise ValueError("Gift template cannot be decoded.")
    height, width = screen.normalized.shape[:2]
    left, top, right, bottom = anchor.expected_region.pixels(width, height)
    region = screen.normalized[top:bottom, left:right]
    th, tw = template.shape[:2]
    if region.shape[0]*region.shape[1] > 60_000:
        # Coarse current-frame proposals bound the costly masked pose search.
        # They NEVER authorize input: every result still needs >=0.96, paired
        # icon/badge/page proof, and uniqueness across all bounded proposals.
        scores = cv2.matchTemplate(region, template, cv2.TM_CCOEFF_NORMED)
        proposals = []
        floor = .8 if anchor.id == "gift-core" else .6
        for _ in range(5):
            _, score, _, (x, y) = cv2.minMaxLoc(scores)
            if score < floor:
                break
            proposals.append((left+x+tw//2, top+y+th//2))
            scores[max(0,y-th):y+th+1, max(0,x-tw):x+tw+1] = -1
        if len(proposals) == 5:
            return AnchorEvidence(anchor.id, anchor.state, 0, anchor.threshold, False)
        radius = max(th, tw)*2
        results = [unique_pose_anchor(screen, replace(anchor, expected_region=NormalizedRect(
            max(0,x-radius)/width, max(0,y-radius)/height,
            min(width,x+radius)/width, min(height,y+radius)/height))) for x, y in proposals]
        qualified = [r for r in results if r.matched]
        if any(not r.matched and r.score >= r.threshold for r in results):
            return AnchorEvidence(anchor.id, anchor.state, 1, anchor.threshold, False)
        if not qualified:
            return AnchorEvidence(anchor.id, anchor.state, max((r.score for r in results), default=0), anchor.threshold, False)
        best = max(qualified, key=lambda r: r.score)
        cx, cy = best.normalized_box.center
        if any(abs(r.normalized_box.center[0]-cx) > best.normalized_box.width/2 or
               abs(r.normalized_box.center[1]-cy) > best.normalized_box.height/2 for r in qualified):
            return replace(best, matched=False, normalized_box=None, device_box=None)
        return best
    size = max(th, tw) * 2
    threshold = max(.96, anchor.threshold)
    candidates = []
    best_score = 0.0
    for scale in (.95, 1.0, 1.05):
        for angle in range(-20, 21, 2):
            matrix = cv2.getRotationMatrix2D((tw/2, th/2), angle, scale)
            matrix[:, 2] += (size/2-tw/2, size/2-th/2)
            patch = cv2.warpAffine(template, matrix, (size, size))
            mask = cv2.warpAffine(np.full((th, tw), 255, np.uint8), matrix, (size, size), flags=cv2.INTER_NEAREST)
            mask = cv2.erode(mask, np.ones((3, 3), np.uint8))
            bx, by, bw, bh = cv2.boundingRect(mask)
            patch, mask = patch[by:by+bh, bx:bx+bw], mask[by:by+bh, bx:bx+bw]
            if bw > region.shape[1] or bh > region.shape[0] or min(bw, bh) < 2:
                continue
            scores = cv2.matchTemplate(region, patch, cv2.TM_CCOEFF_NORMED, mask=mask)
            scores = np.nan_to_num(scores, nan=-1, posinf=-1, neginf=-1)
            # Record at most two spatially distinct peaks per pose.
            for _ in range(2):
                _, score, _, (x, y) = cv2.minMaxLoc(scores)
                best_score = max(best_score, score)
                if score < threshold:
                    break
                candidates.append((score, BoundingBox(left+x, top+y, bw, bh)))
                scores[max(0,y-bh//2):y+bh//2+1, max(0,x-bw//2):x+bw//2+1] = -1
    if not candidates:
        return AnchorEvidence(anchor.id, anchor.state, best_score, threshold, False)
    score, box = max(candidates, key=lambda item: item[0])
    cx, cy = box.center
    if any(abs(other.center[0]-cx) > max(box.width, other.width)/2 or
           abs(other.center[1]-cy) > max(box.height, other.height)/2 for _, other in candidates):
        return AnchorEvidence(anchor.id, anchor.state, score, threshold, False)
    return AnchorEvidence(anchor.id, anchor.state, score, threshold, True, box, screen.to_device_box(box))

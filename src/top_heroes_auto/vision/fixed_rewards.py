"""Current-frame anchors for the three annotated BXH/Tiệm free gifts.

No account names, historical tap coordinates or ordinal shop tabs participate.
Every target needs its own page, unique core and locally associated attention.
"""
from dataclasses import dataclass, replace

import cv2
import numpy as np

from top_heroes_auto.vision.detector import load_anchors
from top_heroes_auto.vision.exploration import unique_current_anchor
from top_heroes_auto.vision.gift_detector import unique_pose_anchor
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, NormalizedRect, ScreenState
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.resources import template_folder

REWARDS = ("ranking-chest", "shop-daily-gift", "shop-weekly-card-gift")
PAGES = dict(zip(REWARDS, ("ranking", "shop-daily", "shop-weekly"), strict=True))


def portrait_region(left, top, right, bottom):
    return NormalizedRect(1-bottom, left, 1-top, right)


@dataclass(frozen=True)
class FixedObservation:
    captured: object
    page: str
    anchors: dict
    overlay: object

    def box(self, role):
        evidence = self.anchors.get(role)
        return evidence.device_box if evidence and evidence.matched else None

    def evidence(self):
        c = self.captured
        return dict(capture=str(c.source_image), timestamp=c.timestamp, index=c.index, name=c.name,
                    adb=c.serial, boot_id=c.boot_id, page=self.page,
                    anchors={k: v.as_dict() for k, v in self.anchors.items()},
                    overlay=self.overlay.as_dict())


class FixedRewardDetector:
    def __init__(self):
        root = template_folder().parent / "tasks/phase6"
        self.anchors = {a.id: a for a in load_anchors(root / "fixed-rewards")}
        self.anchors.update({a.id: a for a in load_anchors(root / "home")
                             if a.id == "home-shop-entry"})
        self.folder = root/'fixed-rewards'
        self.recovery = RecoveryScreenDetector()

    def observe(self, captured):
        anchors = {}
        for name, anchor in self.anchors.items():
            # Semantic surfaces only. These regions never supply tap coordinates.
            if name.startswith("avatar-"):
                region = portrait_region(0, 0, .22, .15)
            elif name in {"profile-bxh", "back", "daily-tab", "weekly-tab"}:
                region = portrait_region(0, .90, 1, 1)
            elif name == "ranking-close":
                region = portrait_region(.3, .86, .7, 1)
            else:
                region = portrait_region(0, 0, 1, .36)
            anchors[name] = unique_current_anchor(captured, replace(anchor, expected_region=region))
            if name == 'shop-gift' and not anchors[name].matched and anchors[name].score < anchor.threshold:
                anchors[name] = unique_pose_anchor(captured, replace(anchor, expected_region=region))
        reference = anchors.get('shop-title-reference')
        title = anchors['shop-title']
        if reference and reference.matched:
            if title.matched and title.device_box and reference.device_box and (
                abs(title.device_box.center[0] - reference.device_box.center[0]) > title.device_box.width/2
                or abs(title.device_box.center[1] - reference.device_box.center[1]) > title.device_box.height/2
            ):
                anchors['shop-title'] = replace(title, matched=False, device_box=None, normalized_box=None)
            elif not title.matched:
                anchors['shop-title'] = reference
        recovery = self.recovery.detect(captured)
        anchors['avatar-frame'] = self.avatar_frame(captured)
        known = []
        def matched(*roles):
            return all(anchors[r].matched for r in roles)
        if matched("profile-title", "profile-bxh"):
            known.append("profile")
        if matched("ranking-title", "ranking-tab"):
            known.append("ranking")
        if matched("shop-title", "daily-title"):
            known.append("shop-daily")
        if matched("shop-title", "weekly-title"):
            known.append("shop-weekly")
        if recovery.state == ScreenState.GAME_HOME:
            known.append("home")
        # Known overlays take precedence. A partial/conflicting recovery signature
        # must never permit an underlying page's gift to receive input.
        conflict = recovery.state not in {ScreenState.UNKNOWN, ScreenState.GAME_HOME}
        conflict |= recovery.state == ScreenState.UNKNOWN and bool(recovery.evidence)
        page = known[0] if len(known) == 1 and not conflict else "UNKNOWN"
        return FixedObservation(captured, page, anchors, recovery)

    def avatar_frame(self, captured):
        template = cv2.imdecode(np.frombuffer((self.folder/'avatar-frame.png').read_bytes(), np.uint8), 1)
        mask = cv2.imdecode(np.frombuffer((self.folder/'avatar-mask.png').read_bytes(), np.uint8), 0)
        region = portrait_region(0, 0, .23, .17)
        height, width = captured.normalized.shape[:2]
        left, top, right, bottom = region.pixels(width, height)
        source = captured.normalized[top:bottom, left:right]
        scores = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED, mask=mask)
        scores = np.nan_to_num(scores, nan=-1, posinf=-1, neginf=-1)
        _, score, _, (x, y) = cv2.minMaxLoc(scores)
        th, tw = template.shape[:2]
        scores[max(0, y-th//2):y+th//2+1, max(0, x-tw//2):x+tw//2+1] = -1
        matched = score >= .98 and float(scores.max()) < .98
        box = BoundingBox(left+x, top+y, tw, th) if matched else None
        return AnchorEvidence('avatar-frame', ScreenState.GAME_HOME, score, .98, matched,
                              box, captured.to_device_box(box) if box else None)

    def availability(self, observation, reward):
        if reward not in PAGES or observation.page != PAGES[reward]:
            return "UNKNOWN", None, None
        ranking = reward == "ranking-chest"
        core_role = "ranking-chest" if ranking else "shop-gift"
        badge_role = "ranking-attention" if ranking else "shop-attention"
        core = observation.anchors[core_role]
        badge = observation.anchors[badge_role]
        if not ranking:
            received = observation.anchors['daily-received' if reward == 'shop-daily-gift' else 'weekly-received']
            if received.matched and received.device_box:
                # Positive open gift + "Đã nhận", not mere badge disappearance.
                b = received.device_box
                width, height = observation.captured.device_size or observation.captured.original_size
                attention = badge.device_box if badge.matched else None
                local_badge = attention and b.x-b.width*.2 < attention.center[0] < b.x+b.width*1.2 and (
                    b.y-b.height*.2 < attention.center[1] < b.y+b.height
                )
                if (not local_badge and not core.matched and received.score >= .98
                        and b.x > width*.75 and b.y+b.height < height*.36):
                    return 'NOT_AVAILABLE', received, badge
        if not core.matched or core.device_box is None:
            return "UNKNOWN", core, badge
        box = core.device_box
        w, h = observation.captured.device_size or observation.captured.original_size
        # Association to the appropriate title, not a generic red dot elsewhere.
        title = observation.box("ranking-title" if ranking else
                                "daily-title" if reward == "shop-daily-gift" else "weekly-title")
        if title is None or box.y < title.y - h*.025 or box.y > title.y + h*.23:
            return "UNKNOWN", core, badge
        if (ranking and box.x >= title.x) or (not ranking and box.x <= title.x+title.width):
            return "UNKNOWN", core, badge
        if badge.matched and badge.device_box:
            b = badge.device_box
            if abs(b.center[0] - (box.x+box.width)) < box.width*.3 and (
                box.y - box.height*.65 <= b.center[1] <= box.y + box.height*.3
            ):
                return "AVAILABLE", core, badge
        if not ranking:
            return 'UNKNOWN', core, badge
        # Strong intact gift + clear attached badge area. Any red/partial badge
        # remains UNKNOWN rather than being mistaken for an inactive gift.
        if core.score < .985:
            return "UNKNOWN", core, badge
        image = observation.captured.normalized
        portrait = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        sx, sy = portrait.shape[1]/w, portrait.shape[0]/h
        x1, x2 = round((box.x+box.width*.87)*sx), round((box.x+box.width*1.28)*sx)
        y1, y2 = round((box.y-box.height*.60)*sy), round((box.y+box.height*.18)*sy)
        if min(x1, y1) < 0 or x2 > portrait.shape[1] or y2 > portrait.shape[0]:
            return "UNKNOWN", core, badge
        patch = portrait[y1:y2, x1:x2]
        if not patch.size or float(patch.mean()) < 25:
            return "UNKNOWN", core, badge
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        red = cv2.inRange(hsv, (0, 130, 140), (10, 255, 255)) | cv2.inRange(hsv, (170, 130, 140), (179, 255, 255))
        if np.count_nonzero(red) > max(2, red.size*.025):
            return "UNKNOWN", core, badge
        return "NOT_AVAILABLE", core, badge


def claim_geometry(observation, reward, core):
    """The whole lower product/list area is forbidden, not just price text."""
    if observation.page != PAGES.get(reward) or core is None or not core.matched or core.device_box is None:
        raise ValueError("Claim needs a uniquely recognized gift on its exact page.")
    box = core.device_box
    width, height = observation.captured.device_size or observation.captured.original_size
    # All annotated targets live in the isolated top panel. Fail if a layout
    # moves into the product/list region; never reinterpret a paid gift icon.
    boundary = round(height * (.15 if reward == "ranking-chest" else .36))
    forbidden = BoundingBox(0, boundary, width, height-boundary)
    if box.y + box.height >= boundary or min(box.x, box.y) < 0 or box.x+box.width > width:
        raise ValueError("Gift intersects forbidden list/product area.")
    return dict(bbox=vars(box), tap=list(box.center), forbidden=vars(forbidden),
                inside_allowed=True, outside_forbidden=True, confidence=core.score)

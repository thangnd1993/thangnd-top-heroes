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
from top_heroes_auto.vision.subpixel import unique_subpixel_anchor

REWARDS = ("ranking-chest", "shop-daily-gift", "shop-weekly-card-gift")
SHOP_REWARDS = (*REWARDS[1:], "shop-permanent-privilege-gift", "shop-monthly-privilege-gift")
MONTHLY_QUICK = 'shop-monthly-quick-collect'
ADS_ROWS = ('energy', 'meat', 'wood', 'stone', 'rune')
ALL_REWARDS = (REWARDS[0], *SHOP_REWARDS, MONTHLY_QUICK)
SHOP_ROUTES = dict(zip(SHOP_REWARDS, ("daily", "weekly", "permanent", "monthly"), strict=True))
PAGES = {REWARDS[0]: "ranking", **{reward: f"shop-{route}" for reward, route in SHOP_ROUTES.items()}}
PAGES[MONTHLY_QUICK] = 'shop-ad-privileges'
SHOP_PAGES = frozenset(f"shop-{route}" for route in SHOP_ROUTES.values())


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
            if name.startswith('ads-completed') or name in {f'ads-{row}' for row in ADS_ROWS}:
                continue  # Repeated completion controls need independent row association.
            # Semantic surfaces only. These regions never supply tap coordinates.
            if name.startswith('ads-'):
                region = portrait_region(0, 0, 1, 1)
            elif name in {'permanent-active-current', 'permanent-tab-current', 'permanent-selected-icon', 'monthly-selected-icon', 'monthly-tab-notice'}:
                region = portrait_region(0, .90, 1, 1)
            elif name.startswith("avatar-"):
                region = portrait_region(0, 0, .22, .15)
            elif name == 'shop-notice-speaker':
                region = portrait_region(0, .16, .15, .25)
            elif name in {"profile-bxh", "back", "daily-tab", "weekly-tab"} or name in {"permanent-tab", "monthly-tab", "permanent-active-tab", "monthly-active-tab"}:
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
            elif not title.matched and title.score < title.threshold:
                anchors['shop-title'] = reference
        if reference and not reference.matched and reference.score >= reference.threshold:
            anchors['shop-title'] = replace(title, matched=False, device_box=None, normalized_box=None)
        recovery = self.recovery.detect(captured)
        for role, variant in [('weekly-title', 'weekly-title-current'), ('permanent-tab', 'permanent-tab-current')]:
            anchors[role] = self._same_target_variant(anchors[role], anchors[variant])
        for route in ('permanent', 'monthly'):
            role = f'{route}-tab'
            anchors[role] = self._same_target_variant(anchors[role], anchors[f'{route}-selected-icon'])
            # A retrieval gate avoids transforming unrelated low-score UI. It
            # never authorizes input; final confidence remains >=.98 and unique.
            seed = max(anchors[role].score,anchors[f'{route}-selected-icon'].score)
            if not anchors[role].matched and anchors[role].score < anchors[role].threshold and seed >= .85:
                for variant in (role, f'{route}-selected-icon'):
                    aligned = unique_subpixel_anchor(captured, replace(self.anchors[variant],
                        expected_region=portrait_region(0, .90, 1, 1)))
                    anchors[role] = self._same_target_variant(anchors[role], aligned)
        anchors['monthly-tab'] = self._same_target_variant(anchors['monthly-tab'], anchors['monthly-tab-notice'])
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
        for route in ('permanent', 'monthly'):
            if matched('shop-title', f'{route}-title'):
                known.append(f'shop-{route}')
        if matched('ads-title', 'ads-banner', 'ads-close'):
            title, banner, close = (anchors[r].device_box for r in ('ads-title', 'ads-banner', 'ads-close'))
            if title.y+title.height < banner.y < close.y and abs(title.center[0]-close.center[0]) < title.width/2:
                known.append('shop-ad-privileges')
        if recovery.state == ScreenState.GAME_HOME:
            known.append("home")
        # Known overlays take precedence. A partial/conflicting recovery signature
        # must never permit an underlying page's gift to receive input.
        conflict = recovery.state not in {ScreenState.UNKNOWN, ScreenState.GAME_HOME}
        conflict |= recovery.state == ScreenState.UNKNOWN and bool(recovery.evidence)
        page = known[0] if len(known) == 1 and not conflict else "UNKNOWN"
        if page == 'shop-ad-privileges':
            for row in ADS_ROWS:
                role = f'ads-{row}'
                label = unique_current_anchor(captured, replace(self.anchors[role],
                    expected_region=portrait_region(.18, .28, .62, .80)))
                anchors[role] = label
                if label.matched and label.device_box:
                    box = label.device_box
                    width, height = captured.device_size or captured.original_size
                    top, bottom = box.y/height, min((box.y+box.height*3)/height, .85)
                    anchors[f'ads-done-{row}'] = unique_current_anchor(captured, replace(
                        self.anchors['ads-completed'], expected_region=portrait_region(.64, top, .93, bottom)))
                    for variant in ('ads-completed-meat', 'ads-completed-stone'):
                        found = unique_current_anchor(captured, replace(self.anchors[variant],
                            expected_region=portrait_region(.64, top, .93, bottom)))
                        anchors[f'ads-done-{row}'] = self._same_target_variant(anchors[f'ads-done-{row}'], found)
        if page == 'ranking':
            core, badge = anchors['ranking-chest'], anchors['ranking-attention']
            if not core.matched and core.score < core.threshold and badge.matched and badge.device_box:
                b = badge.device_box
                w, h = captured.device_size or captured.original_size
                radius = max(b.width,b.height)
                region = portrait_region(max(0,b.center[0]-5*radius)/w,
                    max(0,b.center[1]-2*radius)/h,min(w,b.center[0]+2*radius)/w,
                    min(h,b.center[1]+5*radius)/h)
                posed = unique_pose_anchor(captured,replace(self.anchors['ranking-chest'],expected_region=region))
                anchors['ranking-chest'] = self._same_target_variant(core,posed)
        if page == 'shop-weekly':
            anchors['weekly-received'] = self._same_target_variant(
                anchors['weekly-received'], anchors['weekly-received-current'])
            base, variant = anchors['shop-gift'], anchors['weekly-gift-core']
            if not base.matched and base.score < base.threshold and not variant.matched and variant.score < variant.threshold:
                anchors['weekly-gift-core'] = unique_pose_anchor(captured, replace(
                    self.anchors['weekly-gift-core'], expected_region=portrait_region(0, 0, 1, .36)))
            for role, variant in [('shop-gift', 'weekly-gift-core'), ('shop-attention', 'weekly-gift-attention')]:
                anchors[role] = self._same_target_variant(anchors[role], anchors[variant])
        for expected, pairs in {
            'shop-daily': [('shop-gift', 'daily-core-current'), ('shop-attention', 'daily-badge-current')],
            'shop-permanent': [('permanent-gift', 'permanent-core-current'),
                               ('permanent-attention', 'permanent-badge-current'),
                               ('permanent-active-tab', 'permanent-active-current')],
        }.items():
            if page == expected:
                for role, variant in pairs:
                    anchors[role] = self._same_target_variant(anchors[role], anchors[variant])
        if page in {'shop-permanent', 'shop-monthly'}:
            route = page.removeprefix('shop-')
            if route == 'monthly':
                anchors['monthly-gift'] = self._same_target_variant(anchors['monthly-gift'], anchors['monthly-gift-tilted'])
            core, badge = anchors[f'{route}-gift'], anchors[f'{route}-attention']
            if not core.matched and core.score < core.threshold and badge.matched and badge.device_box:
                # The gift rocks independently of the current attention badge.
                # Same strict threshold, bounded pose bank, no account coordinates.
                b = badge.device_box
                w, h = captured.device_size or captured.original_size
                radius = max(b.width, b.height)
                region = portrait_region(max(0,b.center[0]-5*radius)/w,
                    max(0,b.center[1]-2*radius)/h, min(w,b.center[0]+2*radius)/w,
                    min(h,b.center[1]+5*radius)/h)
                posed = unique_pose_anchor(captured, replace(self.anchors[f'{route}-gift'], expected_region=region))
                anchors[f'{route}-gift'] = self._same_target_variant(core, posed)
        return FixedObservation(captured, page, anchors, recovery)

    @staticmethod
    def _same_target_variant(base, variant):
        strong = [v for v in (base, variant) if v.score >= v.threshold]
        if any(not v.matched for v in strong):
            return replace(base, matched=False, score=max(v.score for v in strong), device_box=None)
        if base.matched and variant.matched:
            a, b = base.device_box, variant.device_box
            if abs(a.center[0]-b.center[0]) > max(a.width, b.width)*.5 or abs(a.center[1]-b.center[1]) > max(a.height, b.height)*.5:
                return replace(base, matched=False, device_box=None)
        return base if base.matched else variant if variant.matched else base

    def avatar_frame(self, captured):
        variants = [self._avatar_variant(captured, style) for style in ('avatar', 'avatar-floral')]
        # A duplicate in either style cannot be rescued by the other style.
        strong = [v for v in variants if v.score >= v.threshold]
        if len(strong) == 1 and strong[0].matched:
            return strong[0]
        return replace(max(variants, key=lambda v: v.score), matched=False,
                       device_box=None, normalized_box=None)

    def _avatar_variant(self, captured, style):
        template = cv2.imdecode(np.frombuffer((self.folder/f'{style}-frame.png').read_bytes(), np.uint8), 1)
        mask = cv2.imdecode(np.frombuffer((self.folder/f'{style}-mask.png').read_bytes(), np.uint8), 0)
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

    @staticmethod
    def selected_tab(observation, route):
        if observation.page != f'shop-{route}':
            return False
        active, tab = observation.box(f'{route}-active-tab'), observation.box(f'{route}-tab')
        if active and tab and active.x <= tab.center[0] <= active.x+active.width:
            return True
        if not tab or observation.page != f'shop-{route}':
            return False
        # A leftmost selected tile can be clipped by the separate Back area.
        # Its gold header is qualified above the CURRENT unique icon. The page
        # title must agree; another selected tab cannot satisfy this local gate.
        captured = observation.captured
        image = cv2.rotate(captured.normalized, cv2.ROTATE_90_COUNTERCLOCKWISE)
        w, h = captured.device_size or captured.original_size
        sx, sy = image.shape[1]/w, image.shape[0]/h
        x1, x2 = round((tab.center[0]-tab.width*.7)*sx), round((tab.center[0]+tab.width*.7)*sx)
        y1, y2 = round((tab.y-tab.height*.6)*sy), round((tab.y-tab.height*.25)*sy)
        if tab.y < h*.92 or min(x1,y1) < 0 or x2 > image.shape[1] or y2 >= image.shape[0]:
            return False
        patch = image[y1:y2,x1:x2]
        if not patch.size:
            return False
        gold = cv2.inRange(cv2.cvtColor(patch,cv2.COLOR_BGR2HSV), (15,100,180), (40,255,255))
        return float(np.count_nonzero(gold))/gold.size >= .98

    def availability(self, observation, reward):
        if reward not in PAGES or observation.page != PAGES[reward]:
            return "UNKNOWN", None, None
        if reward == MONTHLY_QUICK:
            core = observation.anchors['ads-quick']
            completed = [observation.box(f'ads-done-{row}') for row in ADS_ROWS]
            if all(completed):
                # Positive state in every visible reward row plus absent CTA;
                # no receipt-only or missing-button-only acceptance.
                ordered = all(a.y+a.height < b.y for a, b in zip(completed, completed[1:], strict=False))
                if ordered and not core.matched and core.score < core.threshold:
                    return 'NOT_AVAILABLE', observation.anchors['ads-done-energy'], None
                return 'UNKNOWN', core, None
            try:
                claim_geometry(observation, reward, core)
            except ValueError:
                return 'UNKNOWN', core, None
            # Absence/disabled-looking pixels are NOT independent proof of a
            # successful collection. Qualify a positive post-state separately.
            return 'AVAILABLE', core, None
        ranking = reward == "ranking-chest"
        if not ranking and observation.box('shop-notice-speaker'):
            return 'UNKNOWN', None, None  # Broadcast banner can cover the gift/received label.
        route = SHOP_ROUTES.get(reward)
        privilege = route in {"permanent", "monthly"}
        if privilege and not self.selected_tab(observation, route):
            return 'UNKNOWN', None, None
        core_role = f"{route}-gift" if privilege else "ranking-chest" if ranking else "shop-gift"
        badge_role = f"{route}-attention" if privilege else "ranking-attention" if ranking else "shop-attention"
        core = observation.anchors[core_role]
        badge = observation.anchors[badge_role]
        if not core.matched and core.score >= core.threshold:
            return 'UNKNOWN', core, badge
        if ranking:
            empty = observation.anchors['ranking-empty-slot']
            if empty.matched:
                title = observation.box('ranking-title')
                b = empty.device_box
                if (not core.matched and not badge.matched and empty.score >= .98 and b and title
                        and b.x+b.width < title.x and abs(b.center[1]-title.center[1]) < b.height*.5):
                    return 'NOT_AVAILABLE', empty, badge
                return 'UNKNOWN', core, badge
        if not ranking:
            received = observation.anchors['weekly-received' if route == 'weekly' else 'daily-received']
            if route == 'permanent':
                received = self._same_target_variant(received, observation.anchors['permanent-received'])
            if received.matched and received.device_box:
                # Positive open gift + "Đã nhận", not mere badge disappearance.
                b = received.device_box
                width, height = observation.captured.device_size or observation.captured.original_size
                attention = badge.device_box if badge.matched else None
                local_badge = attention and b.x-b.width*.2 < attention.center[0] < b.x+b.width*1.2 and (
                    b.y-b.height*.2 < attention.center[1] < b.y+b.height
                )
                same_core = core.matched and core.device_box and (
                    b.x <= core.device_box.center[0] <= b.x+b.width
                    and b.y <= core.device_box.center[1] <= b.y+b.height)
                if (not local_badge and (not core.matched or (route == 'permanent' and same_core)) and received.score >= .98
                        and b.x > width*.75 and b.y+b.height < height*.36):
                    return 'NOT_AVAILABLE', received, badge
                return 'UNKNOWN', core, badge
            if not received.matched and received.score >= received.threshold:
                return 'UNKNOWN', core, badge
        if not core.matched or core.device_box is None:
            return "UNKNOWN", core, badge
        box = core.device_box
        w, h = observation.captured.device_size or observation.captured.original_size
        # Association to the appropriate title, not a generic red dot elsewhere.
        title = observation.box("ranking-title" if ranking else
                                f"{route}-title")
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
    if reward == MONTHLY_QUICK:
        title, banner, close = (observation.box(r) for r in ('ads-title', 'ads-banner', 'ads-close'))
        if not all((title, banner, close)) or core is not observation.anchors.get('ads-quick'):
            raise ValueError('Quick collect requires its own paired page and exact button.')
        if not (banner.y+banner.height < box.y and box.y > height*.70
                and box.y+box.height < close.y and box.x > width*.15
                and box.x+box.width < width*.85
                and abs(box.center[0]-close.center[0]) < box.width*.25):
            raise ValueError('Quick collect is outside its isolated bottom action area.')
        forbidden = BoundingBox(0, 0, width, box.y)
        return dict(bbox=vars(box), tap=list(box.center), forbidden=vars(forbidden),
                    inside_allowed=True, outside_forbidden=True, confidence=core.score)
    # All annotated targets live in the isolated top panel. Fail if a layout
    # moves into the product/list region; never reinterpret a paid gift icon.
    boundary = round(height * (.15 if reward == "ranking-chest" else .36))
    forbidden = BoundingBox(0, boundary, width, height-boundary)
    if box.y + box.height >= boundary or min(box.x, box.y) < 0 or box.x+box.width > width:
        raise ValueError("Gift intersects forbidden list/product area.")
    return dict(bbox=vars(box), tap=list(box.center), forbidden=vars(forbidden),
                inside_allowed=True, outside_forbidden=True, confidence=core.score)

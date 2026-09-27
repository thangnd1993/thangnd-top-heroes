"""Guild/Mail current-frame evidence; no account or annotation coordinates."""
import json
from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from top_heroes_auto.vision.detail_anchor import unique_detail_anchor
from top_heroes_auto.vision.fixed_rewards import FixedObservation, portrait_region
from top_heroes_auto.vision.local_ocr import counter
from top_heroes_auto.vision.models import AnchorEvidence, BoundingBox, ScreenState, VisualAnchor
from top_heroes_auto.vision.recovery_detector import RecoveryScreenDetector
from top_heroes_auto.vision.resources import template_folder

GUILD_REWARDS = ('guild-relic', 'guild-gifts-loot', 'guild-gifts-member', 'guild-technology')
MAIL_TABS = ('war', 'guild', 'system', 'reports', 'collection')
MAIL_REWARDS = tuple(f'mail-{tab}' for tab in MAIL_TABS)
# These cores are icons/counters, not the outlined text seen in the supplied
# resized references. Keep their original strict pixel qualification.
PIXEL_ROLES = frozenset({'home-guild','home-mail','back','relic-gift','technology-like',
    'donation-wood','donation-diamond','modal-close','donation-count-suffix',
    'badge-digit-3','badge-digit-4','badge-digit-6','gift-received-check'})



def portrait(captured):
    return (cv2.rotate(captured.original, cv2.ROTATE_90_COUNTERCLOCKWISE)
            if captured.rotated_from_portrait else captured.original)


def crop(image, box):
    h, w = image.shape[:2]
    if box is None or box.x < 0 or box.y < 0 or box.x+box.width > w or box.y+box.height > h:
        return None
    return image[box.y:box.y+box.height, box.x:box.x+box.width]


def contains(outer, inner):
    return (outer.x <= inner.x and outer.y <= inner.y and
            inner.x+inner.width <= outer.x+outer.width and inner.y+inner.height <= outer.y+outer.height)


def intersects(a, b):
    return (a.x < b.x+b.width and b.x < a.x+a.width and a.y < b.y+b.height and b.y < a.y+a.height)


def components(image, color):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    limits = {'green': ((32, 70, 90), (85, 255, 255)),
              'blue': ((85, 65, 100), (115, 255, 255)),
              'orange': ((8, 90, 100), (32, 255, 255)),
              'brown': ((6, 70, 65), (24, 210, 205)),
              'gray': ((0, 0, 85), (179, 45, 235))}
    if color == 'red':
        mask = cv2.inRange(hsv, (0, 135, 180), (6, 255, 255)) | cv2.inRange(hsv, (174, 135, 180), (179, 255, 255))
    else:
        mask = cv2.inRange(hsv, *limits[color])
    if color == 'red':
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9,9),np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [BoundingBox(*cv2.boundingRect(c)) for c in contours if cv2.contourArea(c) > 8]


@dataclass(frozen=True)
class GuildObservation(FixedObservation):
    values: dict = field(default_factory=dict)

    def evidence(self):
        return dict(super().evidence(), values=self.values)


class GuildMailDetector:
    def __init__(self, *, number_reader=counter):
        self.folder = template_folder().parent / 'tasks/phase7'
        manifest = json.loads((self.folder/'manifest.json').read_text(encoding='utf-8'))
        self.templates = {item['id']: cv2.imdecode(np.frombuffer(
            (self.folder/f"{item['id']}.png").read_bytes(), np.uint8), cv2.IMREAD_COLOR) for item in manifest}
        self.thresholds = {item['id']: item['threshold'] for item in manifest}
        self.recovery = RecoveryScreenDetector()
        self.number_reader = number_reader

    def anchor(self, captured, role, region=(0, 0, 1, 1), *, grayscale=False):
        """Bounded scale variants share one uniqueness check, never pick a duplicate."""
        image = captured.normalized
        left, top, right, bottom = portrait_region(*region).pixels(*captured.normalized_size)
        search = image[top:bottom, left:right]
        template = self.templates[role]
        threshold = max(.98,self.thresholds[role]) if grayscale else self.thresholds[role]
        if grayscale:
            search = cv2.cvtColor(search,cv2.COLOR_BGR2GRAY)
            template = cv2.cvtColor(template,cv2.COLOR_BGR2GRAY)
        # Outlined text in the supplied resized references has softer edges
        # than the live renderer. Match the same low-frequency letter structure
        # at a fixed scale grid, without reducing the confidence threshold.
        text_core = role not in PIXEL_ROLES
        resampled_entry = role in PIXEL_ROLES and not role.startswith('badge-digit-') and role != 'gift-received-check'
        kernel, sigma = ((5, 5), 1.3) if text_core else ((3, 3), .5)
        if text_core or resampled_entry:
            search = cv2.GaussianBlur(search, kernel, sigma)
        candidates, best = [], 0.0
        scales = [(1,1),(.97,.97),(1.03,1.03)]
        if resampled_entry or text_core:
            scales.append((1.02,1.02))
        if text_core:
            scales.extend([(1,1.02),(1,1.03),(1.02,1.03),(1.03,1.02)])
        for sx, sy in scales:
            t = cv2.resize(template, None, fx=sx, fy=sy, interpolation=cv2.INTER_AREA)
            if text_core or resampled_entry:
                t = cv2.GaussianBlur(t, kernel, sigma)
            h, w = t.shape[:2]
            if h > search.shape[0] or w > search.shape[1]:
                continue
            scores = cv2.matchTemplate(search, t, cv2.TM_CCOEFF_NORMED)
            for _ in range(2):
                _, score, _, (x, y) = cv2.minMaxLoc(scores)
                if not np.isfinite(score):
                    break
                best = max(best, score)
                if score < threshold:
                    break
                candidates.append((score, BoundingBox(left+x, top+y, w, h)))
                scores[max(0,y-h//2):y+h//2+1, max(0,x-w//2):x+w//2+1] = -1
        if candidates:
            score, box = max(candidates, key=lambda item: item[0])
            if all(abs(other.center[0]-box.center[0]) < box.width/2 and
                   abs(other.center[1]-box.center[1]) < box.height/2 for _, other in candidates):
                return AnchorEvidence(role, ScreenState.FREE_REWARD_PAGE, score, threshold, True,
                                      box, captured.to_device_box(box))
        return AnchorEvidence(role, ScreenState.UNKNOWN, best, threshold, False)

    @staticmethod
    def variant(first, second):
        if first.matched and second.matched and not intersects(first.device_box, second.device_box):
            return replace(first, matched=False, device_box=None, normalized_box=None)
        for evidence in (first, second):
            if not evidence.matched and evidence.score >= evidence.threshold:
                return evidence  # A duplicate cannot be rescued by another crop.
        return first if first.matched or not second.matched else second

    def observe(self, captured):
        regions = {
            'home-guild': (.65,.45,1,.9), 'home-mail': (.65,.45,1,.9),
            'back': (0,.88,.23,1), 'technology-like': (0,.20,1,.88),
            'modal-close': (.3,.82,.7,1),
        }
        anchors = {r: AnchorEvidence(r,ScreenState.UNKNOWN,0,self.thresholds[r],False)
                   for r in self.templates}
        searched = set()
        variants = {'gifts-quick':('gifts-quick-member',),'relic-tab':('relic-tab-selected',),
                    'gifts-title':('gifts-title-member',),'territory-title':('territory-title-relic',),
                    'mail-system':('mail-system-alt','mail-system-current','mail-system-selected'),
                    'donation-green':('donation-green-current',),
                    'mail-reports':('mail-reports-selected',),'mail-collection':('mail-collection-alt',)}

        def read_core(role):
            if role in searched:
                return
            searched.add(role)
            if role.endswith('title') or role in {'guild-declaration','territory-fortress','relic-owned-tab',
                    'technology-contribution','mail-empty-label'}:
                region = (0,0,1,.58)
            elif role.startswith('mail-') and role not in {'mail-read','mail-delete-forbidden'}:
                region = (0,.1,1,.25)
            elif role in {'relic-tab','relic-tab-selected','gifts-quick','gifts-quick-member'}:
                region = (0,.88,1,1)
            elif role in {'loot-selected','loot-inactive','member-selected','member-inactive'}:
                region = (0,.20,1,.35)
            else:
                region = (0,0,1,1)
            anchors[role] = self.anchor(captured, role, regions.get(role, region))
            if (role in {'gifts-quick','gifts-quick-member'} and not anchors[role].matched
                    and anchors[role].score < anchors[role].threshold):
                anchors[role] = self.anchor(captured,role,regions.get(role,region),grayscale=True)

        def read(role):
            read_core(role)
            for other in variants.get(role,()):
                read_core(other)
                anchors[role] = self.variant(anchors[role],anchors[other])

        # Search every page title for conflicts, then only the controls relevant
        # to a positively matched title. Unsearched controls never prove absence.
        groups = {
            'guild-title': ('guild-declaration','guild-territory','guild-gifts','guild-technology',
                            'guild-trial-forbidden','back'),
            'territory-title': ('territory-fortress','relic-summary','relic-owned-tab','relic-gift','relic-tab','back'),
            'gifts-title': ('loot-selected','member-selected','loot-inactive','member-inactive',
                            'gifts-quick','gift-claim','loot-row-title','member-row-title','back'),
            'technology-title': ('technology-contribution','technology-like','back'),
            'donation-heading': ('donation-counter-label','donation-count-suffix','donation-green',
                                'donation-paid','donation-wood','donation-diamond','modal-close'),
            'mail-title': ('modal-close','mail-war-selected','mail-war-inactive','mail-guild-selected',
                          'mail-guild-inactive','mail-system','mail-reports','mail-collection',
                          'mail-empty-label','mail-read','mail-delete-forbidden'),
        }
        for title, roles in groups.items():
            read(title)
            if anchors[title].matched:
                for role in roles:
                    read(role)
        overlay = self.recovery.detect(captured)
        if overlay.state == ScreenState.GAME_HOME:
            read('home-guild')
            read('home-mail')
        pages = []
        pairs = {
            'guild': ('guild-title','guild-declaration'),
            'territory': ('territory-title','territory-fortress'),
            'relic': ('territory-title','relic-summary'),
            'gifts-loot': ('gifts-title','loot-selected'),
            'gifts-member': ('gifts-title','member-selected'),
            'technology': ('technology-title','technology-contribution'),
            'donation': ('donation-heading','donation-counter-label'),
            'mail': ('mail-title','modal-close'),
        }
        for page, roles in pairs.items():
            if (all(anchors[r].matched and self.undimmed(captured,anchors[r]) for r in roles) and (page != 'mail' or
                    sum(anchors[r].matched for r in ('mail-system','mail-reports','mail-collection',
                        'mail-war-selected','mail-war-inactive','mail-guild-selected','mail-guild-inactive')) >= 2)):
                pages.append(page)
        if overlay.state == ScreenState.GAME_HOME:
            pages.append('home')
        conflict = (overlay.state not in {ScreenState.UNKNOWN, ScreenState.GAME_HOME} or
                    overlay.state == ScreenState.UNKNOWN and bool(overlay.evidence))
        # Mail is itself a qualified modal over dimmed Home, not a generic popup.
        if pages == ['mail'] and overlay.state == ScreenState.HOME_OVERLAY:
            conflict = False
            overlay = replace(overlay, state=ScreenState.UNKNOWN, confidence=0, evidence=())
        page = pages[0] if len(pages) == 1 and not conflict else 'UNKNOWN'
        frame = GuildObservation(captured, page, anchors, overlay)
        if page == 'technology':
            anchors['technology-node'] = self.tech_node(frame)
        return frame

    def undimmed(self,captured,evidence):
        box = evidence.normalized_box
        if box is None or evidence.anchor_id not in self.templates:
            return False
        current = captured.normalized[box.y:box.y+box.height,box.x:box.x+box.width]
        template = cv2.resize(self.templates[evidence.anchor_id],(box.width,box.height),interpolation=cv2.INTER_AREA)
        if evidence.anchor_id not in PIXEL_ROLES:
            current = cv2.GaussianBlur(current, (5,5), 1.3)
            template = cv2.GaussianBlur(template, (5,5), 1.3)
        # Correlation alone can match a uniformly dimmed parent behind a modal.
        return float(np.mean(np.abs(current.astype(float)-template.astype(float)))) <= 15

    def control(self, frame, role, color):
        label = frame.box(role)
        if label is None or frame.page == 'UNKNOWN':
            return None
        boxes = [b for b in components(portrait(frame.captured), color) if contains(b, label) and
                 1.4 <= b.width/b.height <= 6 and label.width <= b.width <= label.width*3.5
                 and b.height <= label.height*4.5]
        if not boxes and role == 'donation-paid':
            # This orange button can join the modal border in the color mask.
            # Bind its current closed edge rectangle to BOTH text and color;
            # never invent a fixed exclusion rectangle from an old screenshot.
            image = portrait(frame.captured)
            contours,_ = cv2.findContours(cv2.Canny(image,60,140),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                b = BoundingBox(*cv2.boundingRect(contour))
                if not (contains(b,label) and 1.4 <= b.width/b.height <= 6
                        and label.width <= b.width <= label.width*3.5 and b.height <= label.height*4.5
                        and cv2.contourArea(contour) > .7*b.width*b.height):
                    continue
                hsv = cv2.cvtColor(crop(image,b),cv2.COLOR_BGR2HSV)
                if float(np.mean(cv2.inRange(hsv,(8,90,100),(32,255,255)) > 0)) < .6:
                    continue
                near = next((other for other in boxes if
                    abs(other.center[0]-b.center[0]) < b.width*.1 and
                    abs(other.center[1]-b.center[1]) < b.height*.1),None)
                if near:
                    if near.width*near.height >= b.width*b.height:
                        continue
                    boxes.remove(near)
                boxes.append(b)
        return boxes[0] if len(boxes) == 1 else None

    def local_badge(self, frame, box, *, numbered=False):
        """Badge must attach to the control's upper-right, not another red dot."""
        image = portrait(frame.captured)
        candidates = [b for b in components(image, 'red') if
            box.x+box.width*.6 < b.center[0] < box.x+box.width+box.height*.4 and
            box.y-box.height*.4 < b.center[1] < box.y+box.height*.3 and
            .04*box.width < b.width < .65*box.height and .04*box.width < b.height < .65*box.height]
        if len(candidates) != 1:
            return None
        badge = candidates[0]
        if not numbered:
            return badge
        # The badge can touch tab text or the edge of a button. Qualify
        # bounded crops independently at both OCR scales; conflicting numbers
        # reject the badge instead of choosing whichever crop looks convenient.
        readings = set()
        regions = []
        for horizontal, top, bottom in ((.4,.4,.4),(.6,.6,.6),(.5,.45,.2)):
            px, pt, pb = (max(2,round(badge.height*v)) for v in (horizontal,top,bottom))
            region = BoundingBox(badge.x-px,badge.y-pt,badge.width+2*px,badge.height+pt+pb)
            regions.append(region)
            part = crop(image,region)
            number = self.number_reader(part) if part is not None else None
            if number is not None:
                readings.add(number)
        if len(readings) > 1:
            return None
        if readings:
            return next(iter(readings))
        region = regions[1]
        # Windows OCR can omit a single character. Only qualified real glyph
        # anchors may resolve it; no numeric substitutions or guessed counts.
        height,width = image.shape[:2]
        area = (max(0,region.x/width),max(0,region.y/height),
                min(1,(region.x+region.width)/width),min(1,(region.y+region.height)/height))
        matches = []
        for digit in (3,4,6):
            role = f'badge-digit-{digit}'
            evidence = self.anchor(frame.captured,role,area)
            if not evidence.matched and evidence.score < evidence.threshold:
                # Selected/ordinary tabs change the background outside the red
                # badge. Require the entire current badge footprint below.
                anchor = VisualAnchor(role,ScreenState.FREE_REWARD_PAGE,self.folder/f'{role}.png',
                                      portrait_region(*area),.98)
                evidence = unique_detail_anchor(frame.captured,anchor)
            matches.append((digit,evidence))
        matches = [(digit,e) for digit,e in matches if e.matched and
                   .8*badge.height <= e.device_box.height <= 1.4*badge.height and
                   .8*badge.width <= e.device_box.width <= 1.4*badge.width]
        if len(matches) == 1:
            digit,evidence = matches[0]
            frame.anchors[f'counter-{box.x}-{box.y}'] = evidence
            return digit
        return None

    def donation(self, frame):
        if frame.page != 'donation':
            return 'UNKNOWN', None, None
        label = frame.box('donation-counter-label')
        wood = frame.box('donation-wood')
        green = self.control(frame, 'donation-green', 'green')
        paid = self.control(frame, 'donation-paid', 'orange')
        if label is None:
            return 'UNKNOWN', None, None
        image = portrait(frame.captured)
        suffix = frame.box('donation-count-suffix')
        if not suffix or not label.x+label.width <= suffix.x <= label.x+label.width*1.4:
            return 'UNKNOWN', None, None
        region = BoundingBox(label.x+label.width, label.y, suffix.x-label.x-label.width, label.height)
        part = crop(image, region)
        remaining = self.number_reader(part, maximum=20) if part is not None and part.size else None
        if remaining == 0:
            return 'NOT_AVAILABLE', None, 0
        if (remaining is None or green is None or paid is None or wood is None or
                not contains(green,wood) or intersects(green,paid) or not frame.box('donation-diamond')
                or not contains(paid,frame.box('donation-diamond'))):
            return 'UNKNOWN', None, remaining
        return 'AVAILABLE', green, remaining

    def tech_node(self, frame):
        marker = frame.box('technology-like')
        default = AnchorEvidence('technology-node', ScreenState.UNKNOWN, 0, .97, False)
        if not marker:
            return default
        image = portrait(frame.captured)
        contours, _ = cv2.findContours(cv2.Canny(image,60,140),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        candidates = components(image,'brown')+[BoundingBox(*cv2.boundingRect(c)) for c in contours]
        boxes = []
        for b in candidates:
            if not (2.1*marker.width < b.width < 4.5*marker.width and .8 < b.width/b.height < 1.25 and
                    abs(b.x-marker.center[0]) < marker.width and abs(b.y-marker.center[1]) < marker.height):
                continue
            hsv = cv2.cvtColor(crop(image,b),cv2.COLOR_BGR2HSV)
            brown = cv2.inRange(hsv,(6,70,65),(24,210,205))
            if float(np.mean(brown > 0)) < .45:
                continue
            near = next((p for p in boxes if abs(p.center[0]-b.center[0]) < min(p.width,b.width)*.15
                         and abs(p.center[1]-b.center[1]) < min(p.height,b.height)*.15),None)
            if near:
                if b.width*b.height <= near.width*near.height:
                    continue
                boxes.remove(near)
            boxes.append(b)
        if len(boxes) != 1:
            return default
        return AnchorEvidence('technology-node',ScreenState.FREE_REWARD_PAGE,
                              frame.anchors['technology-like'].score,.97,True,device_box=boxes[0])

    def action_geometry(self, frame, role, box, forbidden=()):
        if frame.page == 'UNKNOWN' or box is None:
            raise ValueError('No qualified current-page action.')
        if crop(portrait(frame.captured), box) is None or any(intersects(box, other) for other in forbidden):
            raise ValueError('Action intersects forbidden UI or image boundary.')
        return dict(role=role,bbox=vars(box),tap=list(box.center),
                    forbidden=[vars(b) for b in forbidden],capture=str(frame.captured.source_image))



    def mail_tabs(self, frame):
        """Associate current rounded tab containers with qualified labels/order."""
        if frame.page != 'mail':
            return {}
        image = portrait(frame.captured)
        height, width = image.shape[:2]
        edges = cv2.Canny(image,60,140)
        contours, _ = cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            box = BoundingBox(*cv2.boundingRect(contour))
            if not (.1*height < box.y < .19*height and .12*width < box.width < .20*width
                    and .045*height < box.height < .075*height and box.y+box.height < .24*height):
                continue
            prior = next((b for b in boxes if abs(b.center[0]-box.center[0]) < box.width/3),None)
            if prior:
                if box.width*box.height > prior.width*prior.height:
                    boxes.remove(prior)
                else:
                    continue
            boxes.append(box)
        boxes.sort(key=lambda b:b.x)
        roles = {
            'war': ('mail-war-selected','mail-war-inactive'),
            'guild': ('mail-guild-selected','mail-guild-inactive'),
            'system': ('mail-system',), 'reports': ('mail-reports',), 'collection': ('mail-collection',),
        }
        assigned = {}
        for tab, names in roles.items():
            labels = [frame.box(n) for n in names if frame.box(n)]
            found = [b for b in boxes if any(contains(b,label) for label in labels)]
            if len(found) == 1:
                assigned[tab] = found[0]
        # Only one selected label may change its color. Four named neighbours
        # and five equal, ordered current containers positively bind that fifth.
        if len(boxes) == 5 and len(assigned) == 4 and all(
                assigned[t] == boxes[MAIL_TABS.index(t)] for t in assigned):
            missing = next(t for t in MAIL_TABS if t not in assigned)
            assigned[missing] = boxes[MAIL_TABS.index(missing)]
        result = {}
        for tab, box in assigned.items():
            part = crop(image,box)
            hsv = cv2.cvtColor(part,cv2.COLOR_BGR2HSV)
            cream = float(np.mean((hsv[:,:,1] < 80) & (hsv[:,:,2] > 225)))
            orange = float(np.mean((hsv[:,:,1] > 85) & (hsv[:,:,0] < 30)))
            selected = True if cream > .55 else False if orange > .55 else None
            badge = self.local_badge(frame,box)
            number = self.local_badge(frame,box,numbered=True) if badge else None
            # A missing badge is meaningful only on a complete sharp tab control.
            if not badge and selected is not None:
                near_red = [b for b in components(image,'red') if
                            box.x+box.width*.65 < b.center[0] < box.x+box.width+box.height*.3
                            and box.y-box.height*.3 < b.center[1] < box.y+box.height*.35]
                number = 0 if not near_red else None
            result[tab] = dict(box=box,count=number,selected=selected)
        return result

    def received_rows(self, frame):
        """Positive received-row checks, distinct from absence of a claim button."""
        if frame.page not in {'gifts-loot','gifts-member'}:
            return 0
        template = self.templates['gift-received-check']
        left,top,right,bottom = portrait_region(.68,.40,.97,.86).pixels(*frame.captured.normalized_size)
        search = frame.captured.normalized[top:bottom,left:right]
        h,w = template.shape[:2]
        if h > search.shape[0] or w > search.shape[1]:
            return 0
        scores = cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED)
        count = 0
        for _ in range(6):
            _,score,_,(x,y) = cv2.minMaxLoc(scores)
            if not np.isfinite(score) or score < self.thresholds['gift-received-check']:
                break
            count += 1
            scores[max(0,y-h//2):y+h//2+1,max(0,x-w//2):x+w//2+1] = -1
        return count

    def availability(self, frame, reward):
        from top_heroes_auto.automation.guild_mail_claims import Opportunity

        unknown = Opportunity(reward,'UNKNOWN',context=reward)
        if reward == 'guild-technology':
            state, box, remaining = self.donation(frame)
            paid = self.control(frame,'donation-paid','orange')
            return Opportunity(reward,state,'donation-green',box,remaining,reward,(paid,) if paid else ())
        if reward == 'guild-relic':
            core = frame.box('relic-gift')
            if frame.page != 'relic' or not core:
                return unknown
            badge = self.local_badge(frame,core)
            if badge:
                return Opportunity(reward,'AVAILABLE','relic-gift',core,1,reward)
            # No weak/missing gift inference: the same full unique core must be visible.
            image = portrait(frame.captured)
            nearby = [b for b in components(image,'red') if abs(b.center[0]-(core.x+core.width)) < core.width
                      and abs(b.center[1]-core.y) < core.height*.7]
            return unknown if nearby else Opportunity(reward,'NOT_AVAILABLE',remaining=0,context=reward)
        if reward in {'guild-gifts-loot','guild-gifts-member'}:
            if frame.page != reward.removeprefix('guild-'):
                return unknown
            quick = self.control(frame,'gifts-quick','green')
            if quick:
                count = self.local_badge(frame,quick,numbered=True)
                if count is not None and count > 0:
                    return Opportunity(reward,'AVAILABLE','gifts-quick',quick,count,reward)
            if quick and self.badge_absent(frame,quick) and self.received_rows(frame) >= 2:
                row_claim = frame.anchors.get('gift-claim')
                if row_claim is not None and row_claim.score < row_claim.threshold:
                    return Opportunity(reward,'NOT_AVAILABLE',remaining=0,context=reward)
            inactive = self.control(frame,'gifts-quick','gray')
            row_claim = frame.anchors.get('gift-claim')
            if (inactive and self.badge_absent(frame,inactive) and
                    (row_claim is None or row_claim.score < row_claim.threshold)):
                return Opportunity(reward,'NOT_AVAILABLE',remaining=0,context=reward)
            return unknown
        if reward in MAIL_REWARDS:
            tab = reward.removeprefix('mail-')
            current = self.mail_tabs(frame).get(tab)
            if not current or current['count'] is None:
                return unknown
            if current['count'] == 0:
                return Opportunity(reward,'NOT_AVAILABLE',remaining=0,context=reward)
            if current['selected'] is not True:
                return unknown
            button = self.control(frame,'mail-read','blue')
            delete = self.control(frame,'mail-delete-forbidden','red')
            if button and delete and not intersects(button,delete):
                return Opportunity(reward,'AVAILABLE','mail-read',button,current['count'],reward,(delete,))
        return unknown


    @staticmethod
    def badge_absent(frame,box):
        return not any(box.x+box.width*.55 < b.center[0] < box.x+box.width+box.height*.5
                       and box.y-box.height*.5 < b.center[1] < box.y+box.height*.4
                       for b in components(portrait(frame.captured),'red'))

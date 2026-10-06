"""Qualified achievement modal/card schema; no paid or Go inputs."""
import hashlib

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import folded
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder


def anchor(image, name):
    ref = cv2.imread(str(template_folder().parent/'tasks/phase8/achievements'/f'{name}.png'))
    if ref is None or any(a < b for a, b in zip(image.shape[:2], ref.shape[:2])):
        return None
    scores = cv2.matchTemplate(image, ref, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(scores)
    h, w = ref.shape[:2]
    if not np.isfinite(score) or score < .995:
        return None
    scores[max(0, y-h//2):y+h//2+1, max(0, x-w//2):x+w//2+1] = -1
    return BoundingBox(x, y, w, h) if scores.max() < .995 else None


def achievement_label_glyph(image, row):
    crop = image[row.y+8:row.y+round(row.height*.27), row.x+10:row.x+row.width-10]
    mask = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (0, 90, 70), (25, 255, 220))
    if np.count_nonzero(mask) < 100:
        return None
    return cv2.resize(mask, (480, 40), interpolation=cv2.INTER_NEAREST)


def achievement_shell(image):
    h, w = image.shape[:2]
    title, close = anchor(image, 'title'), anchor(image, 'close')
    if not (title and close and title.y < h*.12 and close.y > h*.85
            and abs(title.center[0]-close.center[0]) < w*.08):
        return None
    rim = image[max(0, close.y-close.height//2):min(h, close.y+close.height*3//2),
                max(0, close.x-close.width//2):min(w, close.x+close.width*3//2)]
    hsv = cv2.cvtColor(rim, cv2.COLOR_BGR2HSV)
    red = cv2.inRange(hsv, (0, 130, 160), (9, 255, 255)) | cv2.inRange(hsv, (170, 130, 160), (179, 255, 255))
    if np.mean(red > 0) < .45:
        return None
    edges = cv2.morphologyEx(cv2.Canny(image, 40, 120), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
    panels, cards = [], []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw > w*.88 and bh > h*.75 and y < title.y and y+bh < close.y and cv2.contourArea(c)/(bw*bh) > .95:
            panels.append(BoundingBox(x, y, bw, bh))
        if (w*.78 < bw < w*.90 and h*.085 < bh < h*.105 and title.y+title.height < y
                and y+bh < h*.84 and cv2.contourArea(c)/(bw*bh) > .97
                and not any(abs(x-b.x) < 8 and abs(y-b.y) < 8 for b in cards)):
            header = round(bh*.39)
            cards.append(BoundingBox(x, y-header, bw, bh+header))
    if not panels or len(cards) < 2:
        return None
    panel = max(panels, key=lambda b: b.width*b.height)
    if any(not (panel.x < b.x < b.x+b.width < panel.x+panel.width
                and panel.y < b.y < b.y+b.height < panel.y+panel.height) for b in cards):
        return None
    cards.sort(key=lambda b: b.y)
    return dict(title='achievements', page='event:achievements:achievement-cards',
                permission='ACHIEVEMENTS', back=close, tabs=[], selected=[], cards=cards)


def achievement_rows(image, shell, *, reader):
    rows = []
    for row in shell['cards']:
        glyph = achievement_label_glyph(image, row)
        if glyph is None:
            continue
        column = BoundingBox(row.x+round(row.width*.685), row.y+round(row.height*.28),
                             round(row.width*.305), round(row.height*.69))
        crop = image[column.y:column.y+column.height, column.x:column.x+column.width]
        green = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (35, 60, 80), (85, 255, 255))
        buttons = []
        for c in cv2.findContours(green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
            x, y, w, h = cv2.boundingRect(c)
            if w > column.width*.85 and row.height*.30 < h < row.height*.55 and cv2.contourArea(c)/(w*h) > .85:
                buttons.append(BoundingBox(x, y, w, h))
        items = image[row.y+round(row.height*.30):row.y+row.height-8, row.x+8:column.x-8]
        contours = cv2.findContours(cv2.Canny(items, 40, 120), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
        tiles = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if (row.width*.10 < w < row.width*.16 and .9 < w/h < 1.1 and cv2.contourArea(c)/(w*h) > .85
                    and not any(abs(x-a) < 8 for a in tiles)):
                tiles.append(x)
        if len(tiles) < 3:
            continue
        claim, claimed, unmet = (anchor(crop, n) for n in ('claim', 'claimed', 'unmet'))
        alternate = anchor(crop, 'claimed-alternate')
        if claimed and alternate and abs(claimed.center[1]-alternate.center[1]) > 5:
            continue  # Conflicting explicit claimed stamps in one action column.
        claimed = claimed or alternate
        state, box = 'UNKNOWN', column
        evidence = ('qualified-achievement-cards', 'complete-reward-card', 'inventory-reward-items')
        if len(buttons) == 1 and claim and not claimed and not unmet:
            b = buttons[0]
            interior = crop[b.y+8:b.y+b.height-8, b.x+8:b.x+b.width-8]
            glyphs = cv2.inRange(cv2.cvtColor(interior, cv2.COLOR_BGR2HSV), (0, 0, 185), (179, 90, 255))
            rendered = cv2.copyMakeBorder(cv2.cvtColor(255-glyphs, cv2.COLOR_GRAY2BGR),
                15, 15, 15, 15, cv2.BORDER_CONSTANT, value=(255, 255, 255))
            labels = [folded(" ".join(q["text"] for q in reader(cv2.resize(rendered, None, fx=k, fy=k)))) for k in (1, 2)]
            hsv = cv2.cvtColor(interior, cv2.COLOR_BGR2HSV)
            foreign = (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 120) & ((hsv[:, :, 0] < 30) | (hsv[:, :, 0] > 85))
            if (b.x <= claim.x and claim.x+claim.width <= b.x+b.width and b.y <= claim.y
                    and claim.y+claim.height <= b.y+b.height and np.mean(foreign) < .015
                    and labels == ["nhan", "nhan"]):
                state = 'AVAILABLE'
                box = BoundingBox(column.x+b.x, column.y+b.y, b.width, b.height)
                evidence += ('sole-no-cost-claim-label', 'qualified-control-color')
        elif not np.count_nonzero(green) and bool(claimed) != bool(unmet) and not claim:
            state = 'NOT_AVAILABLE'
            evidence += (('explicit-claimed-label', 'original-green-control-absent') if claimed else ('unmet-achievement',))
        rows.append(dict(identity=hashlib.sha256(glyph.tobytes()).hexdigest(), row=row, box=box,
                         state=state, evidence=evidence))
    return tuple(rows)

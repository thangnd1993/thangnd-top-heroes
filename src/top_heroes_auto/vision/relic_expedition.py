"""Qualified free expedition dispatch; paid refresh controls are excluded."""
import re

import cv2
import numpy as np

from top_heroes_auto.vision.dynamic_events import task_context_box
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder


def mission_list_surface(image, context_template):
    """Current list rim between the selected tab and qualified send/paid footer.

    Card count is deliberately irrelevant: toast overlays and partially clipped
    rows do not remove the enclosing list. All four boundaries must be visible.
    This is navigation evidence only, never claim or dispatch permission.
    """
    context = task_context_box(image, context_template)
    footer = quick_send(image, context_template, reader=None)
    if context is None or footer is None:
        return None
    h, w = image.shape[:2]
    edges = cv2.Canny(image, 40, 120)
    joined = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours = cv2.findContours(joined, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
    def rim_supported(x, y, bw, bh):
        sides = [np.mean(np.any(edges[y+12:y+bh-12, max(0,s-4):s+5] > 0, axis=1))
                 for s in (x, x+bw-1)]
        ends = [np.mean(np.any(edges[max(0,s-5):s+6, x+12:x+bw-12] > 0, axis=0))
                for s in (y, y+bh-1)]
        return min(*sides, *ends) >= .85

    candidates = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if not (.90*w < bw < .98*w and .35*h < bh < .55*h
                and 0 < y-context.y-context.height < .04*h
                and 0 < footer['box'].y-y-bh < .04*h):
            continue
        # Require continuous enclosing sides, not a box inferred from artwork.
        if not rim_supported(x, y, bw, bh):
            continue
        box = BoundingBox(x, y, bw, bh)
        if not any(abs(x-b.x) < 5 and abs(y-b.y) < 5
                   and abs(bw-b.width) < 8 and abs(bh-b.height) < 8 for b in candidates):
            candidates.append(box)
    if len(candidates) > 1:
        return None
    if not candidates:
        # Full-card viewports have no separate closed rim around the list.
        # Their enclosing feature panel supplies the sides; the current selected
        # tab and separately qualified send/paid footer bound the vertical span.
        # This still requires a unique visible enclosure, never inferred rows.
        panels = []
        for contour in contours:
            x, y, bw, bh = cv2.boundingRect(contour)
            if not (.94*w < bw <= w and .65*h < bh < .95*h
                    and 0 < y < context.y*.75
                    and 0 < y+bh-footer['box'].y-footer['box'].height < .04*h
                    and x <= context.x < context.x+context.width <= x+bw):
                continue
            if not rim_supported(x, y, bw, bh):
                continue
            if not any(abs(x-b.x) < 5 and abs(y-b.y) < 5
                       and abs(bw-b.width) < 8 and abs(bh-b.height) < 8 for b in panels):
                panels.append(BoundingBox(x, y, bw, bh))
        if len(panels) != 1:
            return None
        panel = panels[0]
        inset = round(h*.0125)
        top, bottom = context.y+context.height+inset, footer['box'].y-inset
        if not .35*h < bottom-top < .55*h:
            return None
        return dict(container=panel,
            box=BoundingBox(panel.x+round(panel.width*.20), top, round(panel.width*.40), bottom-top),
            evidence=('qualified-relic-expedition-title', 'selected-task-context',
                      'continuous-feature-panel-rim', 'between-selected-tab-and-qualified-footer',
                      'outside-action-column-and-footer'))
    b = candidates[0]
    # Interior central strip, outside every right-column action and footer.
    return dict(container=b, box=BoundingBox(b.x+round(b.width*.20), b.y+16,
                round(b.width*.40), b.height-32), evidence=(
                'qualified-relic-expedition-title', 'selected-task-context',
                'continuous-list-rim', 'outside-action-column-and-footer'))


def running_timer_shape(ink):
    """Six green numeric cells separated by two paired-dot colon cells.

    This proves timer UI, not an OCR duration or a claim permission. The caller
    additionally requires an owned clock, complete expedition card and context.
    """
    xs = np.flatnonzero(np.any(ink, axis=0))
    if not len(xs):
        return False
    groups = [g for g in np.split(xs, np.flatnonzero(np.diff(xs)>1)+1) if len(g)]
    if len(groups)!=8:
        return False
    tops=[]
    for i,g in enumerate(groups):
        glyph=ink[:,g[0]:g[-1]+1]
        _,y,w,h=cv2.boundingRect(cv2.findNonZero(glyph))
        if i in {2,5}:
            n,_,stats,_=cv2.connectedComponentsWithStats(glyph)
            dots=[s for s in stats[1:] if s[cv2.CC_STAT_AREA]>=3]
            if n!=3 or len(dots)!=2 or not (2<=w<=5 and 8<=h<=16):
                return False
            if any(not 2<=s[cv2.CC_STAT_HEIGHT]<=5 for s in dots):
                return False
        else:
            if not (6<=w<=13 and 12<=h<=20 and .25<np.mean(glyph[y:y+h]>0)<.9):
                return False
            tops.append(y)
    return max(tops)-min(tops)<=3


def mission_rows(image, context_template, *, reader):
    """Read complete expedition cards, including running timers (never inputs).

    A running timer is a positive WAITING state, not an unavailable reward button.
    Card geometry and its stable title/items are retained for same-visit matching.
    No date, display name or position is a mission occurrence identifier.
    """
    context = task_context_box(image, context_template)
    if context is None or quick_send(image, context_template, reader=reader) is None:
        return ()
    h, w = image.shape[:2]
    edges = cv2.morphologyEx(cv2.Canny(image, 40, 120), cv2.MORPH_CLOSE,
                             np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    rows = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if not (.90*w < bw < .97*w and .10*h < bh < .15*h
                and context.y+context.height < y and y+bh < h*.82
                and cv2.contourArea(contour)/(bw*bh) > .97):
            continue
        if any(abs(y-r['row'].y) < 5 for r in rows):
            continue
        row = BoundingBox(x, y, bw, bh)
        column = image[y+round(bh*.30):y+round(bh*.95),
                       x+round(bw*.76):x+round(bw*.99)]
        hsv = cv2.cvtColor(column, cv2.COLOR_BGR2HSV)
        ink = cv2.inRange(hsv, (25, 90, 45), (85, 255, 220))
        shape = running_timer_shape(ink)
        readings = (['', ''] if shape else [' '.join(q['text'] for q in reader(cv2.resize(
            column, None, fx=s, fy=s))).strip() for s in (1, 2)])
        from top_heroes_auto.vision.dynamic_events import folded

        labels = [folded(t) for t in readings]
        if labels == ['', 'den']:
            # Same narrow unavailable Go fallback as task_reward_rows; never
            # rescue a claim label or conflicting OCR with an extra reading.
            enlarged = folded(' '.join(q['text'] for q in reader(cv2.resize(
                column, None, fx=3, fy=3))))
            if enlarged == 'den':
                labels[0] = 'den'
        points = cv2.findNonZero(ink)
        timer_texts = []
        if not shape and points is not None and np.mean(ink > 0) < .15:
            tx, ty, tw, th = cv2.boundingRect(points)
            if tw > 60 and 10 < th < 40:
                # Preserve whitespace around the clock/text. Tight glyph crops
                # are rejected by Windows OCR on these small game numerals.
                glyph = cv2.cvtColor(255-ink, cv2.COLOR_GRAY2BGR)
                timer_texts = [''.join(q['text'] for q in reader(rendered)) for rendered in (
                    cv2.resize(column, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC),
                    cv2.resize(glyph, None, fx=3, fy=3))]
                if sum(bool(re.fullmatch(r'\d{2}:[0-5]\d:[0-5]\d', t)) for t in timer_texts) < 2:
                    timer_texts.append(''.join(q['text'] for q in reader(cv2.resize(
                        column, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC))))
                timer_texts.extend(re.sub(r'\s', '', t) for t in readings)
        timers = [re.fullmatch(r'(\d{2}):([0-5]\d):([0-5]\d)', t)
                  for t in timer_texts]
        recognized = [t for t in timers if t]
        state, seconds = 'UNKNOWN', None
        if shape or (recognized and len({t.group() for t in recognized}) == 1):
            if recognized and len({t.group() for t in recognized}) == 1:
                hours, minutes, secs = map(int, recognized[0].groups())
                seconds = hours*3600+minutes*60+secs
            # A timer also needs its own clock: circular gold rim in the same column.
            mask = cv2.inRange(cv2.cvtColor(column, cv2.COLOR_BGR2HSV),
                               (10, 80, 100), (40, 255, 255))
            rings, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            clocks = [c for c in rings if 15 < cv2.boundingRect(c)[2] < 42
                      and .8 < cv2.boundingRect(c)[2]/max(1, cv2.boundingRect(c)[3]) < 1.2]
            if (shape or (seconds is not None and seconds > 0)) and len(clocks) == 1:
                state = 'WAITING'
        elif labels == ['den', 'den']:
            state = 'DISPATCHABLE'
        elif labels in (['nhan', 'nhan'], ['nhan nhanh', 'nhan nhanh']):
            state = 'COMPLETED'
        rows.append(dict(row=row, state=state, seconds=seconds,
                         timer_confirmed=state=='WAITING' and (shape or len(recognized)>=2)))
    return tuple(sorted(rows, key=lambda r: r['row'].y))


def dispatch_transition(before, after, before_rows, after_rows):
    """Prove at least one particular available card entered running state.

    No scroll is permitted between these captures. Pair unique stable card
    title/item regions; timers must be new, rather than merely present somewhere.
    Partial/hidden cards are not counted as verified missions.
    """
    changed = []
    for old in before_rows:
        if old['state'] != 'DISPATCHABLE':
            continue
        b = old['row']
        reference = before[b.y+6:b.y+b.height-6, b.x+8:b.x+round(b.width*.72)]
        matches = []
        for new in after_rows:
            c = new['row']
            crop = after[c.y+6:c.y+c.height-6, c.x+8:c.x+round(c.width*.72)]
            if crop.shape == reference.shape and abs(c.y-b.y) <= 3:
                score = float(cv2.matchTemplate(crop, reference, cv2.TM_CCOEFF_NORMED)[0, 0])
                if np.isfinite(score) and score >= .995:
                    matches.append(new)
        if (len(matches) == 1 and matches[0]['state'] == 'WAITING'
                and matches[0].get('timer_confirmed')):
            changed.append(dict(before='DISPATCHABLE', after='WAITING',
                                seconds=matches[0]['seconds'], row=b))
    return changed


def quick_send(image, context_template, *, reader):
    if task_context_box(image, context_template) is None:
        return None
    h, w = image.shape[:2]
    template = cv2.imread(str(template_folder().parent/'tasks/phase8/relic-expedition-title.png'))
    if template is None or h < 600 or w < template.shape[1]:
        return None
    scores = cv2.matchTemplate(image[:round(h*.3)], template, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(scores)
    if score < .97:
        return None
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (85, 60, 80), (115, 255, 255))
    mask[:round(h*.81)] = 0
    mask[round(h*.91):] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    root = template_folder().parent/'tasks/phase8'
    send_anchor = cv2.imread(str(root/'relic-quick-send-label.png'))
    paid_anchor = cv2.imread(str(root/'relic-paid-refresh-diamond.png'))
    buttons = []
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if .23*w < bw < .34*w and .04*h < bh < .08*h and cv2.contourArea(c)/(bw*bh) > .90:
            crop = image[y:y+bh, x:x+bw]
            send_score = cv2.minMaxLoc(cv2.matchTemplate(crop,send_anchor,cv2.TM_CCOEFF_NORMED))[1]
            paid_score = cv2.minMaxLoc(cv2.matchTemplate(crop,paid_anchor,cv2.TM_CCOEFF_NORMED))[1]
            buttons.append((BoundingBox(x,y,bw,bh),send_score,paid_score))
    matches = [b for b,s,p in buttons if s >= .98 and p < .90]
    # Positive adjacent paid refresh evidence separates the free send action.
    paid = [b for b,s,p in buttons if p >= .98 and s < .90]
    if len(matches) != 1 or len(paid) != 1 or paid[0].x+paid[0].width >= matches[0].x:
        return None
    return dict(box=matches[0], forbidden=(paid[0],), evidence=(
        'qualified-relic-expedition-title','selected-task-context',
        'exact-clean-quick-send-glyph','separate-paid-refresh','user-authorized-free-mission'))


def confirm_send(image):
    """Pair the expedition modal title, selected tasks, blue confirm and its close."""
    root = template_folder().parent/'tasks/phase8'
    def locate(name, region):
        template = cv2.imread(str(root/(name+'.png')))
        if min(region.shape[:2]) < 90 or template is None:
            return None
        scores=cv2.matchTemplate(region,template,cv2.TM_CCOEFF_NORMED)
        _,score,_,point=cv2.minMaxLoc(scores)
        if score < .98:
            return None
        x,y=point
        h,w=template.shape[:2]
        suppressed=scores.copy()
        suppressed[max(0,y-h):y+h,max(0,x-w):x+w]=0
        if float(suppressed.max()) >= .98:
            return None
        return BoundingBox(x,y,w,h)
    title=locate('relic-send-modal-title',image)
    button=locate('relic-send-confirm',image)
    close=locate('relic-send-close',image)
    if not title or not button or not close or not title.y+title.height < button.y < close.y:
        return None
    h,w=image.shape[:2]
    if not (w*.3<button.center[0]<w*.7 and abs(button.center[0]-close.center[0])<w*.08):
        return None
    crop=image[title.y+title.height:button.y-120,:round(w*.22)]
    marker=cv2.imread(str(root/'relic-send-checked.png'))
    scores=cv2.matchTemplate(crop,marker,cv2.TM_CCOEFF_NORMED)
    count=0
    while float(scores.max()) >= .98 and count < 8:
        _,_,_,(x,y)=cv2.minMaxLoc(scores)
        count+=1
        scores[max(0,y-marker.shape[0]):y+marker.shape[0],max(0,x-marker.shape[1]):x+marker.shape[1]]=0
    if not 1 <= count <= 6:
        return None
    return dict(box=button,close=close,qualified_selected_checks=count,evidence=(
        'paired-expedition-modal-title','selected-mission-checks','exact-no-cost-blue-confirm',
        'user-authorized-free-mission'))

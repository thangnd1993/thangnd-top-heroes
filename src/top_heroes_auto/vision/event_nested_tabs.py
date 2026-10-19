"""Navigation-only paired reward/task strip; artwork grants no claim permission."""
import cv2
import numpy as np

from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.template_cache import read_template


def reward_task_strip(image):
    h, w = image.shape[:2]
    edges = cv2.morphologyEx(cv2.Canny(image, 40, 120), cv2.MORPH_CLOSE,
                             np.ones((3, 3), np.uint8))
    rectangles = []
    for contour in cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        if (.40*w < bw < .98*w and .03*h < bh < .065*h
                and .08*h < y and y+bh < .8*h
                and cv2.contourArea(contour)/(bw*bh) > .94):
            box = BoundingBox(x, y, bw, bh)
            if not any(abs(x-b.x)<5 and abs(y-b.y)<5 and abs(bw-b.width)<5 for b in rectangles):
                rectangles.append(box)
    found = []
    for bar in rectangles:
        if bar.width < w*.9:
            continue
        selected = [b for b in rectangles if .45*bar.width < b.width < .51*bar.width
                    and bar.y <= b.y < bar.y+8
                    and bar.x <= b.x and b.x+b.width < bar.x+bar.width
                    and b.y+b.height <= bar.y+bar.height]
        if len(selected) != 1:
            continue
        active = selected[0]
        side = 0 if active.center[0] < bar.center[0] else 1
        halves = [BoundingBox(bar.x+5+i*(bar.width//2), bar.y+5,
                              bar.width//2-10, bar.height-10) for i in range(2)]
        labels = []
        for i, b in enumerate(halves):
            crop = image[b.y:b.y+b.height, b.x:b.x+b.width]
            limits = ((0,45,25),(30,255,180)) if i == side else ((0,0,205),(179,70,255))
            glyph = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), *limits)
            name = ('reward', 'daily-task')[i]
            ref = read_template(template_folder().parent/'tasks/phase8'/f'nested-{name}-glyph.png')
            if ref is None:
                return None
            ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
            if glyph.shape[0]<ref.shape[0] or glyph.shape[1]<ref.shape[1]:
                return None
            scores = cv2.matchTemplate(glyph, ref, cv2.TM_CCOEFF_NORMED)
            _, score, _, (x,y) = cv2.minMaxLoc(scores)
            scores[max(0,y-ref.shape[0]//2):y+ref.shape[0]//2+1,
                   max(0,x-ref.shape[1]//2):x+ref.shape[1]//2+1] = -1
            labels.append(bool(np.isfinite(score) and score>=.995 and scores.max()<.995))
        if not all(labels):
            continue
        names = ('rewards', 'daily-tasks')
        found.append(dict(selected=names[side], identity='nested:'+names[1-side],
                          box=halves[1-side], bar=bar,
                          evidence=('paired-reward-daily-task-labels', 'closed-two-tab-strip',
                                    'unique-selected-half', 'navigation-only')))
    return found[0] if len(found) == 1 else None

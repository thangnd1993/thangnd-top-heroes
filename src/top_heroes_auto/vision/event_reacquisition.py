"""Navigation-only matching of stable interior patches; never reward permission."""
import cv2
import numpy as np


def stable_entry_match(before, old, current, new, *, require_geometry=True):
    if before.shape != current.shape or min(old.width, old.height, new.width, new.height) < 30:
        return False
    if not (.90 <= new.width/old.width <= 1.10 and .90 <= new.height/old.height <= 1.10):
        return False
    dx, dy = new.center[0]-old.center[0], new.center[1]-old.center[1]
    if require_geometry and (abs(dx) > old.width*.15 or abs(dy) > old.height*.15):
        return False
    # Interior grid excludes the upper-right badge/count and outer glow/background.
    # Matching in a small window avoids rescaling artwork when contour padding changes.
    size = max(8, round(min(old.width, old.height)*.13))
    radius = max(2, round(min(old.width, old.height)*.08))
    hits = []
    for fy in (.30, .45, .60, .75):
        for fx in (.15, .30, .45, .60, .75):
            x, y = old.x+round(old.width*fx), old.y+round(old.height*fy)
            patch = before[y:y+size, x:x+size]
            if patch.shape[:2] != (size,size) or np.std(cv2.cvtColor(patch,cv2.COLOR_BGR2GRAY)) < 12:
                continue
            cx, cy = x+dx, y+dy
            left, top = max(new.x+2,cx-radius), max(new.y+2,cy-radius)
            right, bottom = min(new.x+new.width-2,cx+size+radius), min(new.y+new.height-2,cy+size+radius)
            roi = current[top:bottom,left:right]
            if roi.shape[0] < size or roi.shape[1] < size:
                continue
            _, score, _, point = cv2.minMaxLoc(cv2.matchTemplate(roi,patch,cv2.TM_CCOEFF_NORMED))
            if np.isfinite(score) and score >= .995:
                hits.append((fx,fy,left+point[0]-x,top+point[1]-y))
    # At least seven textured patches, distributed over both axes, must agree on
    # one translation. A shared badge, one glyph or nearest bbox is insufficient.
    for _, _, tx, ty in hits:
        group=[h for h in hits if abs(h[2]-tx)<=1 and abs(h[3]-ty)<=1]
        if (len(group)>=7 and max(h[0] for h in group)-min(h[0] for h in group)>=.45
                and max(h[1] for h in group)-min(h[1] for h in group)>=.29):
            return True
    return False

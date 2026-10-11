"""Qualified free expedition dispatch; paid refresh controls are excluded."""
import cv2

from top_heroes_auto.vision.dynamic_events import task_context_box
from top_heroes_auto.vision.models import BoundingBox
from top_heroes_auto.vision.resources import template_folder


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

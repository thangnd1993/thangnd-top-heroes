"""Only the paired assistance notice's current red close is actionable."""
import math


def assistance_close(screen, evidence):
    expected = {'login-assistance-title', 'login-assistance-banner', 'match-notice-close'}
    if len(evidence) != 3 or {e.anchor_id for e in evidence} != expected:
        return None
    if any(not e.matched or e.device_box is None or not math.isfinite(e.score)
           or e.score < max(.98, e.threshold) for e in evidence):
        return None
    boxes = {e.anchor_id: e.device_box for e in evidence}
    title, banner, close = (boxes[k] for k in (
        'login-assistance-title', 'login-assistance-banner', 'match-notice-close'))
    width, height = screen.device_size or screen.original_size
    if not (width > 0 and height > 0 and title.y < height * .4
            and title.y + title.height < banner.y < close.y
            and close.y > height * .85 and close.y + close.height <= height
            and 0 <= title.x < banner.center[0]
            and title.x + title.width > banner.x
            and all(abs(b.center[0] - width * .5) < width * .15
                    for b in (banner, close))):
        return None
    return close.center

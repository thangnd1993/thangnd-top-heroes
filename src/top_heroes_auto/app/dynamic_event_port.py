"""Current-frame event entry transport. Unknown event contents remain fail-closed."""
import json
import time
from dataclasses import asdict

import cv2

from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import DISMISSIBLE, dismiss_overlay_bottom_left
from top_heroes_auto.vision.dynamic_events import discover_events
from top_heroes_auto.vision.guild_mail import portrait
from top_heroes_auto.vision.models import BoundingBox


class DynamicEventPort:
    def __init__(self, session, folder):
        self.session, self.folder = session, folder
        self.transport = FixedRewardPort(session.manager, session.snapshot, session.index, session.name,
                                         folder, session.check, session.cancelled)
        self.current = None
        self.entered = None
        self.dismissals = 0

    def observe(self):
        observed = self.transport.observe()
        c = observed.captured
        identity = (c.index, c.name, c.serial, c.boot_id)
        image = portrait(c)
        controls, blocked = [], []
        page = observed.page if observed.page == 'home' else 'UNKNOWN'
        candidates = ()
        # The Home detector and current Shop anchor jointly qualify the sidebar.
        # The ROI is a semantic UI surface, not a list of icon/tap coordinates.
        shop = observed.box('home-shop-entry')
        if page == 'home' and shop:
            h, w = image.shape[:2]
            left, top = max(0, round(w*.68)), shop.y+shop.height+2
            bottom = round(h*.40)
            if top < bottom:
                candidates = discover_events(image, BoundingBox(left, top, w-left, bottom-top))
                for candidate in candidates:
                    if candidate.qualified:
                        controls.append(Control(candidate.fingerprint, candidate.icon_box,
                                                ('GAME_HOME', 'current-shop-sidebar', 'rimmed-notification', 'unique-outlined-icon'), 'event'))
                    else:
                        blocked.append('UNQUALIFIED_NOTIFICATION_GEOMETRY')
            else:
                blocked.append('EVENT_REGION_UNQUALIFIED')
        elif page == 'home':
            blocked.append('HOME_SHOP_CONTEXT_MISSING')
        # Do not infer safe navigation or free rewards from arbitrary event art.
        # Event content contracts need clean real evidence, including paid controls.
        if self.entered and page != 'home':
            blocked.append('EVENT_CONTENT_REQUIRES_QUALIFICATION')
        import hashlib

        fingerprint = hashlib.sha256(cv2.resize(image,(90,160)).tobytes()).hexdigest()
        popup = observed.overlay.state in DISMISSIBLE
        self.current = EventFrame(str(c.source_image),identity,page,fingerprint,tuple(controls),
                                  coverage_known=False, popup=popup, blocked=tuple(blocked))
        payload = dict(frame=asdict(self.current), badges=[item.evidence() for item in candidates],
                       observed=observed.evidence(), entered_event=self.entered)
        c.source_image.with_suffix('.event.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        overlay = image.copy()
        for candidate in candidates:
            b = candidate.icon_box or candidate.box
            cv2.rectangle(overlay,(b.x,b.y),(b.x+b.width,b.y+b.height),
                          (0,255,0) if candidate.qualified else (0,165,255),2)
        c.source_image.with_suffix('.event-overlay.png').write_bytes(cv2.imencode('.png',overlay)[1].tobytes())
        return self.current

    def navigate(self, frame, control):
        if (frame is not self.current or frame.page != 'home' or control not in frame.controls or
                control.kind != 'event' or self.entered is not None):
            raise SafetyError('Event navigation lacks a qualified current-frame edge.')
        # Two observations must agree on the icon core and notification box.
        self.current = None
        before = frame
        time.sleep(.35)
        fresh = self.observe()
        matches = [c for c in fresh.controls if c.identity == control.identity]
        if (fresh.page != 'home' or fresh.identity != before.identity or len(matches) != 1 or
                matches[0].box != control.box or fresh.popup):
            raise SafetyError('Moving/ambiguous event notification; no input.')
        self.transport.dispatch(self.transport.last,'tap',matches[0].box.center)
        self.entered = control.identity
        self.current = None
        time.sleep(.5)

    def claim(self, frame, control):
        raise SafetyError('No qualified dynamic event free-action contract for this current page.')

    def dismiss(self, frame):
        if frame is not self.current or not frame.popup or self.dismissals >= 3:
            raise SafetyError('No qualified current popup dismissal.')
        observed = self.transport.last
        point = dismiss_overlay_bottom_left(observed.captured, observed.overlay)
        self.transport.dispatch(observed,'tap',point)
        self.dismissals += 1
        self.current = None
        time.sleep(.5)

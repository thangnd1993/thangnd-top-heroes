"""Guarded Guild/Mail transport; session owns lifecycle, this port owns navigation."""
import json
import time

import cv2

from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import DISMISSIBLE, dismiss_overlay_bottom_left
from top_heroes_auto.vision.guild_mail import GuildMailDetector, portrait
from top_heroes_auto.vision.screenshot import ScreenshotService


class GuildMailPort(FixedRewardPort):
    def __init__(self, session, folder):
        super().__init__(session.manager,session.snapshot,session.index,session.name,folder,
                         session.check,session.cancelled)
        self.detector = GuildMailDetector()
        self.qualified = None
        self.entries = {'guild':0,'mail':0}
        self.dismissals = 0

    def observe(self):
        self.check()
        target, payload = self.manager.capture_verified(self.index,self.snapshot)
        if (target.index,target.name) != (self.index,self.name):
            raise SafetyError('Guild/Mail capture identity changed.')
        if self.target and (target.serial,target.boot_id) != (self.target.serial,self.target.boot_id):
            raise SafetyError('Guild/Mail ADB/boot changed.')
        self.target = target
        captured = ScreenshotService(lambda serial: payload if serial == target.serial else b'').take(
            target,self.folder,'guild-mail')
        self.last = self.detector.observe(captured)
        captured.source_image.with_suffix('.evidence.json').write_text(
            json.dumps(self.last.evidence(), ensure_ascii=False, indent=2), encoding='utf-8')
        self.qualified = None
        return self.last

    def settle(self, frame):
        local = 0
        for _ in range(6):
            if frame.overlay.state in DISMISSIBLE:
                if local >= 2 or self.dismissals >= 40:
                    raise SafetyError('Bounded Guild/Mail popup dismissal exhausted.')
                point = dismiss_overlay_bottom_left(frame.captured,frame.overlay)
                self.dispatch(frame,'tap',point)
                local += 1
                self.dismissals += 1
            elif frame.page != 'UNKNOWN':
                return frame
            time.sleep(.6)
            frame = self.observe()
        return frame

    def navigate(self, frame, role, expected):
        edges = {
            ('home','home-guild'):{'guild'}, ('home','home-mail'):{'mail'},
            ('guild','guild-territory'):{'territory','relic'},
            ('guild','guild-gifts'):{'gifts-loot','gifts-member'},
            ('guild','guild-technology'):{'technology'},
            ('territory','relic-tab'):{'relic'},
            ('gifts-loot','member-inactive'):{'gifts-member'},
            ('gifts-member','loot-inactive'):{'gifts-loot'},
            ('technology','technology-node'):{'donation'},
            ('donation','modal-close'):{'technology'},
            ('mail','modal-close'):{'home'},
            ('guild','back'):{'home'},
            **{(p,'back'):{'guild'} for p in ('territory','relic','gifts-loot','gifts-member','technology')},
        }
        destinations = edges.get((frame.page,role),set())
        if expected not in destinations:
            raise SafetyError(f'No qualified navigation edge: {frame.page}/{role}.')
        origin = frame.page
        # Page title can settle before its tab bar. Reobserve only; never replay
        # the preceding navigation, dismiss UNKNOWN, or switch to another route.
        for _ in range(2):
            if frame.box(role):
                break
            time.sleep(.4)
            frame = self.observe_settled()
            if frame.page != origin:
                raise SafetyError('Page changed while waiting for navigation control.')
        if not frame.box(role):
            raise SafetyError(f'No qualified navigation edge: {frame.page}/{role}.')
        if role in {'home-guild','home-mail'}:
            feature = role.removeprefix('home-')
            if self.entries[feature]:
                raise SafetyError('Feature already entered; no silent re-entry.')
            self.entries[feature] += 1
        self.tap(frame,frame.anchors[role])
        time.sleep(.4)
        after = self.observe_settled()
        if after.page not in destinations:
            raise SafetyError(f'Navigation expected {destinations}; found {after.page}.')
        return after

    def guild(self, frame):
        if frame.page == 'donation':
            frame = self.navigate(frame,'modal-close','technology')
        if frame.page in {'territory','relic','gifts-loot','gifts-member','technology'}:
            frame = self.navigate(frame,'back','guild')
        if frame.page == 'home':
            frame = self.navigate(frame,'home-guild','guild')
        if frame.page != 'guild':
            raise SafetyError('Guild route cannot continue from UNKNOWN.')
        return frame

    def open_reward(self, reward):
        frame = self.observe_settled()
        if reward.startswith('mail-'):
            if frame.page == 'home':
                frame = self.navigate(frame,'home-mail','mail')
            tab = reward.removeprefix('mail-')
            entry = self.detector.mail_tabs(frame).get(tab)
            if not entry or entry['count'] is None:
                raise SafetyError('Mail tab/badge is ambiguous.')
            if entry['count'] == 0:
                return frame  # No tab navigation without a numbered red badge.
            if entry['selected'] is not True:
                self.dispatch(frame,'tap',entry['box'].center)
                time.sleep(.4)
                frame = self.observe_settled()
                current = self.detector.mail_tabs(frame).get(tab)
                if not current or current['selected'] is not True:
                    raise SafetyError('Selected Mail tab was not independently verified.')
            return frame
        if reward in {'guild-gifts-loot','guild-gifts-member'} and frame.page.startswith('gifts-'):
            pass
        else:
            frame = self.guild(frame)
        if reward == 'guild-relic':
            frame = self.navigate(frame,'guild-territory','territory')
            if frame.page != 'relic':
                frame = self.navigate(frame,'relic-tab','relic')
        elif reward.startswith('guild-gifts-'):
            if frame.page == 'guild':
                frame = self.navigate(frame,'guild-gifts','gifts-loot')
            expected = reward.removeprefix('guild-')
            if frame.page != expected:
                role = 'member-inactive' if expected == 'gifts-member' else 'loot-inactive'
                frame = self.navigate(frame,role,expected)
        elif reward == 'guild-technology':
            frame = self.navigate(frame,'guild-technology','technology')
            frame = self.navigate(frame,'technology-node','donation')
        else:
            raise SafetyError('Unsupported Guild route.')
        return frame

    def opportunity(self, reward, initial=None):
        frame = self.settle(initial) if initial is not None else self.observe_settled()
        view = self.detector.availability(frame,reward)
        self.qualified = (frame,view)
        return frame,view

    def geometry(self, frame, view):
        return self.detector.action_geometry(frame,view.role,view.box,view.forbidden)

    def claim(self, frame, view, *, before_input):
        if self.qualified is None or self.qualified[0] is not frame or self.qualified[1] is not view:
            raise SafetyError('Claim is not bound to the current qualified opportunity.')
        if frame is not self.last or view.state != 'AVAILABLE':
            raise SafetyError('Stale or unavailable Guild/Mail opportunity.')
        geometry = self.geometry(frame,view)
        image = portrait(frame.captured).copy()
        for box,color in [(view.box,(0,255,0)),*((b,(0,0,255)) for b in view.forbidden)]:
            cv2.rectangle(image,(box.x,box.y),(box.x+box.width,box.y+box.height),color,2)
        cv2.circle(image,tuple(geometry['tap']),4,(255,0,0),-1)
        stamp = frame.captured.source_image.stem
        (self.folder/f'{stamp}-{view.reward}-geometry.png').write_bytes(cv2.imencode('.png',image)[1].tobytes())
        self.dispatch(frame,'tap',view.box.center,before_input)
        self.qualified = None

    def home(self):
        frame = self.observe_settled()
        if frame.page == 'home':
            return frame
        if frame.page == 'mail':
            return self.navigate(frame,'modal-close','home')
        frame = self.guild(frame)
        return self.navigate(frame,'back','home')

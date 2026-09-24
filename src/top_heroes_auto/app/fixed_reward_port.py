"""Explicit Manager transport for screenshot-bound BXH/shop navigation."""
import json
import time

import cv2

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import DISMISSIBLE, OverlayBudget, dismiss_overlay_bottom_left
from top_heroes_auto.vision.fixed_rewards import FixedRewardDetector
from top_heroes_auto.vision.screenshot import ScreenshotService


class FixedRewardPort:
    def __init__(self, manager, snapshot, index, name, folder, identity_check=lambda: None,
                 cancelled=lambda: False):
        self.manager, self.snapshot, self.index, self.name = manager, snapshot, index, name
        self.folder, self.identity_check, self.cancelled = folder, identity_check, cancelled
        self.detector = FixedRewardDetector()
        self.target = None
        self.last = None
        self.events = []
        self.overlay_budget = OverlayBudget(max_total=6, max_same=3)

    def check(self):
        if self.cancelled():
            raise SafetyError('Fixed reward run cancelled.')
        self.identity_check()
        meta = self.manager.store.metadata(self.manager.namespace, self.index)
        if meta.protected or not meta.selected:
            raise SafetyError('Target must remain selected and non-Protected.')

    def observe(self):
        self.check()
        target, payload = self.manager.capture_verified(self.index, self.snapshot)
        if (target.index, target.name) != (self.index, self.name):
            raise SafetyError('Fixed-flow capture identity changed.')
        if self.target and (target.serial, target.boot_id) != (self.target.serial, self.target.boot_id):
            raise SafetyError('Fixed-flow ADB/boot association changed.')
        self.target = target
        captured = ScreenshotService(lambda serial: payload if serial == target.serial else b'').take(
            target, self.folder, 'bxh-shop')
        self.last = self.detector.observe(captured)
        return self.last

    def dispatch(self, observation, action, values, before_input=None):
        self.check()
        if observation is not self.last or self.target is None:
            raise SafetyError('Stale fixed-flow observation.')
        self.events.append(dict(before=str(observation.captured.source_image), action=action,
                                values=list(values), outcome='POSSIBLE'))
        self.save_events()
        self.manager.execute(self.index, action, values=values, snapshot=self.snapshot,
                             observed_target=self.target, before_input=before_input)
        self.events[-1]['outcome'] = 'DISPATCHED'
        self.last = None
        self.save_events()

    def save_events(self):
        (self.folder / 'actions.json').write_text(json.dumps(self.events, indent=2), encoding='utf-8')

    def tap(self, observation, anchor, *, before_input=None):
        if observation.page == 'UNKNOWN' or not anchor.matched or anchor.device_box is None:
            raise SafetyError('No qualified current-page action bbox.')
        if not any(anchor is a for a in observation.anchors.values()):
            raise SafetyError('Action anchor does not belong to current frame.')
        self.dispatch(observation, 'tap', anchor.device_box.center, before_input)

    def settle(self, observation):
        for attempt in range(4):
            if observation.overlay.state in DISMISSIBLE:
                self.overlay_budget.reserve(observation.overlay)
                point = dismiss_overlay_bottom_left(observation.captured, observation.overlay)
                self.dispatch(observation, 'tap', point)
                time.sleep(.6)
                observation = self.observe()  # Fresh even after the last allowed dismissal.
            elif observation.page != 'UNKNOWN':
                return observation
            elif attempt < 3:
                time.sleep(.6)
                observation = self.observe()
        return observation

    def observe_settled(self):
        return self.settle(self.observe())

    def navigate(self, observation, role, expected):
        permitted = {
            ('home', 'avatar-frame'): 'profile', ('profile', 'profile-bxh'): 'ranking',
            ('ranking', 'ranking-close'): 'profile', ('profile', 'back'): 'home',
            ('home', 'home-shop-entry'): 'shop-daily',
            ('shop-daily', 'weekly-tab'): 'shop-weekly', ('shop-weekly', 'daily-tab'): 'shop-daily',
            ('shop-daily', 'back'): 'home', ('shop-weekly', 'back'): 'home',
        }
        if permitted.get((observation.page, role)) != expected:
            raise SafetyError('Route is not an annotated navigation edge.')
        if not observation.box(role):
            raise SafetyError(f'Current-frame route anchor missing: {role}')
        self.tap(observation, observation.anchors[role])
        time.sleep(.4)
        after = self.observe_settled()
        if role == 'home-shop-entry' and after.page in {'shop-daily', 'shop-weekly'}:
            return after  # Shop may remember its last positively recognized tab.
        if after.page != expected:
            raise SafetyError(f'Expected {expected}; current page {after.page}.')
        return after

    def find_tab(self, observation, role):
        if role not in {'daily-tab', 'weekly-tab'}:
            raise SafetyError('Forbidden shop tab.')
        for attempt in range(3):
            if observation.page not in {'shop-daily', 'shop-weekly'} or not observation.box('back'):
                raise SafetyError('Shop/tab-bar identity unavailable; no scroll.')
            if observation.box(role):
                return observation
            if attempt == 2:
                break
            width, height = observation.captured.device_size or observation.captured.original_size
            # Qualified shop + visible back control identify the bottom tab bar.
            # Swipe stays to its right. No tap uses an ordinal slot.
            y = observation.box('back').center[1]
            start, end = ((.88, .28) if role == 'weekly-tab' else (.28, .88))
            if not .92*height < y < height or observation.box('back').x > width*.2:
                raise SafetyError('Bottom tab bar geometry is not qualified.')
            self.dispatch(observation, 'swipe', (round(width*start), y, round(width*end), y, 400))
            time.sleep(.4)
            observation = self.observe_settled()
        raise SafetyError('Allowed tab not found within two tab-bar swipes.')

    def home(self):
        observation = self.observe_settled()
        for _ in range(2):
            if observation.page == 'home':
                return observation
            if observation.page == 'ranking':
                observation = self.navigate(observation, 'ranking-close', 'profile')
            elif observation.page in {'profile', 'shop-daily', 'shop-weekly'}:
                observation = self.navigate(observation, 'back', 'home')
            else:
                raise SafetyError('UNKNOWN prevents fixed-flow return Home.')
        if observation.page != 'home':
            raise SafetyError('Home not reverified.')
        return observation

    def save_geometry(self, observation, geometry, reward):
        image = observation.captured.original.copy()
        # Draw in device portrait orientation, preserving accepted coordinate mapping.
        if observation.captured.rotated_from_portrait:
            image = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        for key, color in (('bbox', (0, 255, 0)), ('forbidden', (0, 0, 255))):
            b = geometry[key]
            cv2.rectangle(image, (b['x'], b['y']), (b['x']+b['width'], b['y']+b['height']), color, 2)
        cv2.circle(image, tuple(geometry['tap']), 5, (255, 0, 0), -1)
        (self.folder / f'{reward}-geometry.png').write_bytes(cv2.imencode('.png', image)[1].tobytes())

"""Current-frame event entry transport. Unknown event contents remain fail-closed."""
import json
import time
from dataclasses import asdict

import cv2

from top_heroes_auto.app.event_claim_reconciliation import bind_saved_rewards, reconcile_possible
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.automation.event_journal import dispatch_once
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import DISMISSIBLE, dismiss_overlay_bottom_left
from top_heroes_auto.vision.dynamic_events import (
    discover_events,
    discover_menu_tiles,
    event_shell,
    task_context_box,
    task_reward_rows,
)
from top_heroes_auto.vision.guild_mail import portrait
from top_heroes_auto.vision.local_ocr import read_words
from top_heroes_auto.vision.models import BoundingBox, ScreenState
from top_heroes_auto.vision.resources import template_folder


class DynamicEventPort:
    def __init__(self, session, folder):
        self.session, self.folder = session, folder
        self.transport = FixedRewardPort(session.manager, session.snapshot, session.index, session.name,
                                         folder, session.check, session.cancelled)
        self.current = None
        self.entered = None
        self.dismissals = 0
        self.rows = ()
        self.event_title = None
        self.unavailable_observations = {}
        self.pending_claim_ids = {r['id'] for r in session.manager.store.reward_claims(
            session.manager.namespace, session.index)
            if r['status'] == 'RESERVED' and r['dispatch_state'] == 'POSSIBLE'}
        self.task_context = cv2.imread(str(template_folder().parent/'tasks/phase8/personal-task-tab.png'))

    def observe(self):
        observed = self.transport.observe()
        c = observed.captured
        identity = (c.index, c.name, c.serial, c.boot_id)
        image = portrait(c)
        controls, blocked = [], []
        page = observed.page if observed.page == 'home' else 'UNKNOWN'
        candidates = ()
        parent = None
        shell = None
        self.rows = ()
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
            shell = event_shell(image,observed.box('back'),reader=read_words)
            if shell:
                page = shell['page']
                self.event_title = shell['title']
                self.rows = task_reward_rows(image,self.task_context,reader=read_words)
                context=task_context_box(image,self.task_context)
                if context is not None:
                    page = 'event:'+shell['title']+':personal-tasks'
                    self.rows = bind_saved_rewards(image, self.rows,
                        self.session.manager.store.reward_claims(self.session.manager.namespace, self.session.index),
                        persistent_identity=self.session.target['persistent_identity'], index=self.session.index)
                    for row in self.rows:
                        if row['state'] != 'NOT_AVAILABLE':
                            self.unavailable_observations.pop(row['identity'], None)
                            continue
                        proof = dict(identity=list(identity), capture=str(c.source_image),
                            page=page, reward=row['identity'], state='NOT_AVAILABLE',
                            independent_evidence=list(row['evidence']))
                        previous = self.unavailable_observations.get(row['identity'])
                        if previous and previous['page'] == page:
                            reconcile_possible(self.session.manager.store, self.session.manager.namespace,
                                self.session.index, self.session.target['persistent_identity'], [previous, proof],
                                claim_ids=self.pending_claim_ids)
                        self.unavailable_observations[row['identity']] = proof
                    for row in self.rows:
                        if row['state']=='AVAILABLE':
                            b=row['row']
                            h,w=image.shape[:2]
                            forbidden=tuple(q for q in (
                                BoundingBox(0,0,w,b.y),BoundingBox(0,b.y+b.height,w,h-b.y-b.height),
                                BoundingBox(0,b.y,b.x,b.height),BoundingBox(b.x+b.width,b.y,w-b.x-b.width,b.height)
                            ) if q.width>0 and q.height>0)
                            controls.append(Control(row['identity'],row['box'],row['evidence'],
                                'reward',cost='FREE',available=True,forbidden=forbidden))
                    if len(self.rows)>=2:
                        first,last=self.rows[0]['row'],self.rows[-1]['row']
                        # Gesture stays wholly within CURRENT complete reward cards,
                        # left of their action column and above the paid refresh bar.
                        surface=BoundingBox(first.x+round(first.width*.20),first.y+20,
                            round(first.width*.40),last.y+last.height-first.y-40)
                        controls.append(Control('task-list-vertical',surface,
                            ('selected-task-context','complete-card-list','outside-action-column'),'scroll'))
                for tile in discover_menu_tiles(image):
                    controls.append(Control(tile.fingerprint,tile.icon_box,
                        ('event-shell','closed-menu-grid','unique-corner-notification'),'child'))
                parent = Control('current-back',shell['back'],('gold-header','stable-title','back-anchor'),'parent')
                for tab in shell['tabs']:
                    controls.append(Control(tab.fingerprint,tab.icon_box,
                        ('event-shell','tab-strip','unique-outlined-icon','rimmed-notification'),'tab'))
            blocked.append('EVENT_CONTENT_REQUIRES_QUALIFICATION')
        elif page == 'home':
            self.entered = None
        import hashlib

        fingerprint = hashlib.sha256(cv2.resize(image,(90,160)).tobytes()).hexdigest()
        if self.rows:
            # Clocks/background animation cannot pretend the list made progress.
            fingerprint=hashlib.sha256(json.dumps([(r['identity'],r['state'],r['row'].y)
                for r in self.rows]).encode()).hexdigest()
        popup = (observed.overlay.state in DISMISSIBLE and
                 (self.entered is None or observed.overlay.state != ScreenState.HOME_OVERLAY))
        self.current = EventFrame(str(c.source_image),identity,page,fingerprint,tuple(controls),
                                  coverage_known=False, parent=parent, popup=popup, blocked=tuple(blocked))
        payload = dict(frame=asdict(self.current), badges=[item.evidence() for item in candidates],
                       observed=observed.evidence(), entered_event=self.entered,
                       shell=dict(title=shell['title'],selected=shell['selected']) if shell else None,
                       reward_rows=[{**r,'row':asdict(r['row']),'box':asdict(r['box'])} for r in self.rows])
        c.source_image.with_suffix('.event.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        overlay = image.copy()
        for control in controls:
            b=control.box
            cv2.rectangle(overlay,(b.x,b.y),(b.x+b.width,b.y+b.height),(255,255,0),2)
            if control.kind=='reward':
                cv2.circle(overlay,control.box.center,5,(0,255,0),-1)
                for q in control.forbidden:
                    cv2.rectangle(overlay,(q.x,q.y),(q.x+q.width,q.y+q.height),(0,0,255),1)
        for candidate in candidates:
            b = candidate.icon_box or candidate.box
            cv2.rectangle(overlay,(b.x,b.y),(b.x+b.width,b.y+b.height),
                          (0,255,0) if candidate.qualified else (0,165,255),2)
        c.source_image.with_suffix('.event-overlay.png').write_bytes(cv2.imencode('.png',overlay)[1].tobytes())
        return self.current

    def navigate(self, frame, control):
        if frame is not self.current:
            raise SafetyError('Stale event navigation frame.')
        if control.kind=='scroll':
            if not frame.page.endswith(':personal-tasks') or control not in frame.controls:
                raise SafetyError('No qualified current task-list scroll surface.')
            b=control.box
            x=b.x+b.width//2
            start=b.y+round(b.height*.75)
            end=b.y+round(b.height*.25)
            self.transport.dispatch(self.transport.last,'swipe',(x,start,x,end,450))
            self.current=None
            time.sleep(.6)
            return
        if control.kind in {'tab','parent','child'}:
            if not frame.page.startswith('event:') or control not in (*frame.controls,frame.parent):
                raise SafetyError('No qualified event tab/parent edge.')
            self.transport.dispatch(self.transport.last,'tap',control.box.center)
            self.current = None
            time.sleep(.5)
            return
        if (frame.page != 'home' or control not in frame.controls or
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
        if control is None or frame is not getattr(self,'current',None) or control not in frame.controls or control.kind!='reward':
            raise SafetyError('No qualified current event free reward.')
        title = self.event_title
        # Reprove unchanged availability, identity and exact geometry before reservation.
        fresh = self.observe()
        matches = [c for c in fresh.controls if c.kind=='reward' and c.identity==control.identity]
        if (fresh.identity!=frame.identity or fresh.page!=frame.page or fresh.popup
                or self.event_title!=title or len(matches)!=1 or matches[0]!=control):
            raise SafetyError('Free reward changed before dispatch; no input.')
        store = self.session.manager.store
        task = store.create_task_run(self.session.manager.namespace,'dynamic-event-claim',
                                     self.session.index,self.session.name)
        path = self.folder/f'claim-{task}.json'

        def persist(result):
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

        def dispatch(before,target,point,intent):
            if before is not self.current or target not in before.controls:
                raise SafetyError('Claim transport lost frame ownership.')
            self.transport.dispatch(self.transport.last,'tap',point,before_input=intent)
            self.current = None

        def postcondition(before,target):
            observations=[]
            for _ in range(5):
                time.sleep(.5)
                after=self.observe()  # First post-action capture is always retained.
                if after.popup:
                    self.dismiss(after)
                    continue
                if after.identity!=before.identity or after.page!=before.page:
                    return []
                same=[r for r in self.rows if r['identity']==target.identity]
                if len(same)!=1 or same[0]['state']!='NOT_AVAILABLE':
                    return []  # Missing row/receipt alone is never success evidence.
                observations.append(dict(identity=list(after.identity),capture=after.capture,
                    event=title,page=after.page,reward=target.identity,state='NOT_AVAILABLE',
                    independent_evidence=['same-reward-card','claim-control-replaced-by-unavailable-state']))
                if len(observations)==2:
                    return observations
            return []

        try:
            result=dispatch_once(store,task,self.session.manager.namespace,fresh,control,
                event_identity=title,persistent_identity=self.session.target['persistent_identity'],
                dispatch=dispatch,postcondition=postcondition,persist=persist)
            store.finish_task_run(task,result['result'],report_path=str(path))
            return result
        except Exception as exc:
            store.finish_task_run(task,'BLOCKED',error=str(exc),report_path=str(path))
            raise

    def dismiss(self, frame):
        if frame is not self.current or not frame.popup or self.dismissals >= 3:
            raise SafetyError('No qualified current popup dismissal.')
        observed = self.transport.last
        point = dismiss_overlay_bottom_left(observed.captured, observed.overlay)
        self.transport.dispatch(observed,'tap',point)
        self.dismissals += 1
        self.current = None
        time.sleep(.5)

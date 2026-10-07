"""Current-frame event entry transport. Unknown event contents remain fail-closed."""
import json
import time
from dataclasses import asdict

import cv2

from top_heroes_auto.app.event_claim_reconciliation import bind_saved_rewards, reconcile_possible
from top_heroes_auto.app.event_task_effect import removal_effect
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.automation.dynamic_events import Control, EventEntryUnstable, EventFrame, overlaps
from top_heroes_auto.automation.event_journal import dispatch_once
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import (
    DISMISSIBLE,
    OverlayBudget,
    dismiss_overlay_bottom_left,
    overlay_signature,
)
from top_heroes_auto.ldplayer.identity import runtime_key
from top_heroes_auto.vision.dynamic_events import (
    achievement_navigation,
    blank_event_render,
    competitive_navigation_shell,
    competitive_rank_transition,
    contained_signal_on_known_icon,
    decorative_ribbon_on_icon,
    decorative_signal_on_new_icon,
    discover_events,
    discover_menu_tiles,
    event_body_contract,
    event_shell,
    icon_core_image,
    matching_icon_cores,
    menu_art_image,
    menu_card_boxes,
    side_task_navigation,
    task_context_box,
    task_reward_rows,
)
from top_heroes_auto.vision.event_achievements import achievement_rows, achievement_shell
from top_heroes_auto.vision.event_competitive import competitive_indicator_contract
from top_heroes_auto.vision.event_paid_modal import paid_modal_navigation
from top_heroes_auto.vision.event_reacquisition import stable_entry_match
from top_heroes_auto.vision.event_task_grid import task_grid_rows, task_grid_shell, unresolved_grid_actions
from top_heroes_auto.vision.guild_mail import portrait
from top_heroes_auto.vision.local_ocr import read_words
from top_heroes_auto.vision.models import BoundingBox, ScreenState
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.system_dialog import system_dialog


class DynamicEventPort:
    def __init__(self, session, folder):
        self.session, self.folder = session, folder
        self.transport = FixedRewardPort(session.manager, session.snapshot, session.index, session.name,
                                         folder, session.check, session.cancelled)
        self.transport.record_tap_geometry = True
        self.current = None
        self.entered = None
        self.overlay_budget = OverlayBudget()
        self.rows = ()
        self.home_icon_cores = {}
        self.menu_icon_cores = {}
        self.event_title = None
        self.unavailable_observations = {}
        self.pending_claim_ids = {r['id'] for r in session.manager.store.reward_claims(
            session.manager.namespace, session.index)
            if r['status'] == 'RESERVED' and r['dispatch_state'] == 'POSSIBLE'}
        self.task_context = cv2.imread(str(template_folder().parent/'tasks/phase8/personal-task-tab.png'))

    def observe(self):
        if self.current is not None and self.current.render_pending:
            time.sleep(.75)  # Only the explorer's bounded capture-only settling path.
        observed = self.transport.observe()
        c = observed.captured
        identity = (c.index, self.session.target['persistent_identity'], c.serial, c.boot_id)
        image = portrait(c)
        self.navigation_image = image
        dialog = system_dialog(image, reader=read_words)
        controls, blocked = [], []
        page = observed.page if observed.page == 'home' and not dialog else 'UNKNOWN'
        candidates = ()
        parent = None
        shell = None
        contract = None
        ignored_signals = []
        competitive_evidence=None
        coverage_known = False
        event_scan_performed = False
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
                event_scan_performed = True
                for candidate in candidates:
                    if candidate.qualified:
                        core=icon_core_image(image,candidate.icon_box)
                        keys=matching_icon_cores(core,self.home_icon_cores)
                        if len(keys)>1:
                            blocked.append('AMBIGUOUS_ICON_CORE')
                            continue
                        references=getattr(self,'home_navigation_references',{})
                        stable=[key for key,(prior,box) in references.items()
                                if stable_entry_match(prior,box,image,candidate.icon_box)]
                        if len(stable)>1:
                            blocked.append('AMBIGUOUS_ICON_CORE')
                            continue
                        key=stable[0] if stable else (keys[0] if keys else candidate.fingerprint)
                        self.home_navigation_references=references
                        references.setdefault(key,(image,candidate.icon_box))
                        self.home_icon_cores.setdefault(key,core)
                        controls.append(Control(key, candidate.icon_box,
                                                ('GAME_HOME', 'current-shop-sidebar', 'rimmed-notification', 'unique-outlined-icon'), 'event'))
                    elif contained_signal_on_known_icon(candidate,candidates,image=image):
                        ignored_signals.append(candidate.evidence())
                    elif (ribbon := decorative_ribbon_on_icon(image,candidate)):
                        ignored_signals.append(ribbon)
                    elif (decorative := decorative_signal_on_new_icon(image,
                              BoundingBox(left,top,w-left,bottom-top),candidate)):
                        ignored_signals.append(decorative)
                    else:
                        blocked.append('UNQUALIFIED_NOTIFICATION_GEOMETRY')
                coverage_known = not blocked
            else:
                blocked.append('EVENT_REGION_UNQUALIFIED')
        elif page == 'home':
            blocked.append('HOME_SHOP_CONTEXT_MISSING')
        # Do not infer safe navigation or free rewards from arbitrary event art.
        # Event content contracts need clean real evidence, including paid controls.
        if self.entered and page != 'home' and not dialog:
            shell = event_shell(image,observed.box('back'),reader=read_words)
            if shell is None:
                shell=competitive_navigation_shell(image,observed.box('back'))
            if shell is None:
                shell=task_grid_shell(image)
            if shell is None:
                shell=achievement_shell(image)
            if shell:
                page = shell['page']
                self.event_title = shell['title']
                grid=shell.get('permission')=='TASK_GRID'
                achievements=shell.get('permission')=='ACHIEVEMENTS'
                self.rows = (achievement_rows(image,shell,reader=read_words) if achievements else
                             task_grid_rows(image,shell,reader=read_words) if grid else
                             (() if shell.get('permission')=='BACK_ONLY' else
                              task_reward_rows(image,self.task_context,reader=read_words)))
                context=(None if grid or achievements or shell.get('permission')=='BACK_ONLY' else
                         task_context_box(image,self.task_context))
                if context is not None or grid or achievements:
                    if not grid and not achievements:
                        page = 'event:'+shell['title']+':personal-tasks'
                    self.rows = bind_saved_rewards(image, self.rows,
                        self.session.manager.store.reward_claims(self.session.manager.namespace, self.session.index),
                        persistent_identity=self.session.target['persistent_identity'], index=self.session.index,
                        family='achievement-cards' if achievements else 'race-task-grid' if grid else 'personal-tasks')
                    if any(r['state'] == 'UNKNOWN' for r in self.rows):
                        blocked.append('UNRESOLVED_SAVED_REWARD_IDENTITY')
                    for row in self.rows:
                        if row['state'] != 'NOT_AVAILABLE':
                            self.unavailable_observations.pop(row['identity'], None)
                            continue
                        if achievements and 'explicit-claimed-label' not in row['evidence']:
                            continue  # Unmet objective is not proof of a dispatched claim.
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
                    if grid:
                        if unresolved_grid_actions(image,shell,self.rows):
                            blocked.append('UNQUALIFIED_TASK_GRID_ACTION')
                        controls.append(Control('task-grid-vertical',shell['scroll'],
                            ('functional-tasks-word','qualified-task-grid','outside-task-actions'),'scroll'))
                    elif len(self.rows)>=2:
                        first,last=self.rows[0]['row'],self.rows[-1]['row']
                        # Gesture stays wholly within CURRENT complete reward cards,
                        # left of their action column and above the paid refresh bar.
                        surface=BoundingBox(first.x+round(first.width*.20),first.y+20,
                            round(first.width*.40),last.y+last.height-first.y-40)
                        controls.append(Control('task-list-vertical',surface,
                            ('selected-task-context','complete-card-list','outside-action-column'),'scroll'))
                if shell.get('permission')=='BACK_ONLY':
                    competitive_evidence=competitive_indicator_contract(image,shell,reader=read_words)
                contract=('ACHIEVEMENTS' if achievements and len(self.rows)==len(shell['cards']) and all(r['state']!='UNKNOWN' for r in self.rows) else 'UNSUPPORTED' if achievements else 'TASK_GRID' if grid else (
                    'COMPETITIVE_OUT_OF_SCOPE_INDICATORS' if competitive_evidence else
                    ('UNSUPPORTED' if shell.get('permission')=='BACK_ONLY' else
                     event_body_contract(image,self.rows,self.task_context,reader=read_words))))
                coverage_known=contract!='UNSUPPORTED'
                achievement = achievement_navigation(image)
                if achievement and shell.get('permission') != 'BACK_ONLY':
                    controls.append(Control('functional-achievements', achievement['box'],
                        achievement['evidence'], 'child'))
                if contract=='REPUTATION_INFORMATION':
                    nav=side_task_navigation(image)
                    if nav:
                        controls.append(Control('functional-side-tasks',nav['box'],nav['evidence'],'child'))
                if contract=='MENU_GRID':
                    known=self.menu_icon_cores.setdefault((self.entered,page),{})
                    menu_keys={}
                    for card in menu_card_boxes(image):
                        core=menu_art_image(image,card)
                        matches=matching_icon_cores(core,known)
                        if len(matches)>1:
                            blocked.append('AMBIGUOUS_MENU_CORE')
                            continue
                        from top_heroes_auto.vision.dynamic_events import menu_art_key

                        key=matches[0] if matches else menu_art_key(image,card)
                        known.setdefault(key,core)
                        menu_keys[card]=key
                    for tile in discover_menu_tiles(image):
                        key=menu_keys.get(tile.icon_box)
                        if key is None:
                            blocked.append('AMBIGUOUS_MENU_CORE')
                            continue
                        controls.append(Control(key,tile.icon_box,
                            ('event-shell','closed-menu-grid','unique-corner-notification'),'child'))
                    cards=menu_card_boxes(image)
                    first=min(cards,key=lambda b:b.y)
                    bottom=max(b.y+b.height for b in cards)
                    surface=BoundingBox(first.x+round(first.width*.20),first.y+20,
                        round(first.width*.40),bottom-first.y-40)
                    controls.append(Control('menu-list-vertical',surface,
                        ('event-shell','qualified-menu-grid','current-card-list'),'scroll'))
                parent = Control('current-back',shell['back'],
                    ('achievement-title','qualified-achievement-cards','current-modal-close') if achievements else
                    ('functional-tasks-word','qualified-grid','current-modal-close') if grid else
                    (('functional-competition-chrome','paired-glyph-anchors','back-anchor')
                    if shell.get('permission')=='BACK_ONLY' else ('gold-header','stable-title','back-anchor')),'parent')
                for tab in shell['tabs']:
                    controls.append(Control(tab.fingerprint,tab.icon_box,
                        ('event-shell','tab-strip','unique-outlined-icon','rimmed-notification'),'tab'))
            if shell is None and (paid := paid_modal_navigation(image)):
                # Only positively qualified dismissal. An unqualified gift may
                # still be present: do not turn this content into paid-only PASS.
                page = 'event:'+self.entered+':paid-modal'
                contract = 'PAID_MODAL_NAVIGATION_ONLY'
                parent = Control('current-paid-modal-close',paid['close'],
                    ('paid-modal-navigation-only','unique-red-close','purchase-remaining','explicit-vnd'),
                    'parent',forbidden=(paid['paid_region'],))
                blocked.append('UNQUALIFIED_PAID_MODAL_CONTENT')
            if not coverage_known:
                blocked.append('EVENT_CONTENT_REQUIRES_QUALIFICATION')
        elif page == 'home':
            self.entered = None
        import hashlib

        fingerprint = hashlib.sha256(cv2.resize(image,(90,160)).tobytes()).hexdigest()
        if contract=='MENU_GRID':
            fingerprint=hashlib.sha256(repr(sorted((b.x,b.y,b.width,b.height,key)
                for b,key in menu_keys.items())).encode()).hexdigest()
        if self.rows:
            # Clocks/background animation cannot pretend the list made progress.
            fingerprint=hashlib.sha256(json.dumps([(r['identity'],r['state'],r['row'].y)
                for r in self.rows]).encode()).hexdigest()
        popup = (observed.overlay.state in DISMISSIBLE and
                 (self.entered is None or observed.overlay.state != ScreenState.HOME_OVERLAY))
        if dialog:
            popup = False  # Never route Android dialogs through game popup dismissal.
            blocked.append(dialog['reason'])
        transition=(competitive_rank_transition(image) if self.entered and page=='UNKNOWN' and not popup and not dialog else None)
        self.current = EventFrame(str(c.source_image),identity,page,fingerprint,tuple(controls),
                                  coverage_known=coverage_known, parent=parent, popup=popup, blocked=tuple(blocked),
                                  stable_id=self.session.target['persistent_identity'], event_scan_performed=event_scan_performed,
                                  render_pending=bool(self.entered and page=='UNKNOWN' and
                                                      not popup and not dialog and (blank_event_render(image) or transition is not None)))
        if getattr(self,'pending_entry_proof',None) is not None:
            proof=self.pending_entry_proof
            proof.update(post_capture=self.current.capture,post_page=page,
                         event_opened_verified=bool(page.startswith('event:') and not popup))
            if hasattr(self,'folder'):
                with (self.folder/'entry-reacquisition.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(proof)+'\n')
            self.pending_entry_proof=None
        payload = dict(frame=asdict(self.current), badges=[item.evidence() for item in candidates],
                       observed=observed.evidence(), entered_event=self.entered,
                       system_dialog={**dialog,'panels':[asdict(b) for b in dialog['panels']]} if dialog else None,
                       shell=dict(title=shell['title'],selected=shell['selected']) if shell else None,
                       body_contract=contract,competitive_evidence=competitive_evidence,known_transition=transition,ignored_contained_signals=ignored_signals,
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
            if (not frame.page.startswith('event:') or not frame.coverage_known or frame.popup
                    or control not in frame.controls or not (frame.page.endswith(':personal-tasks')
                    or 'qualified-menu-grid' in control.evidence or 'qualified-task-grid' in control.evidence)):
                raise SafetyError('No qualified current Event scroll surface.')
            self.current=None
            fresh=self.observe()
            matches=[c for c in fresh.controls if c.kind=='scroll' and c.identity==control.identity]
            if (runtime_key(fresh.identity)!=runtime_key(frame.identity) or fresh.page!=frame.page or fresh.popup
                    or not fresh.coverage_known or fresh.blocked or len(matches)!=1):
                raise SafetyError('Event scroll changed on fresh capture; no input.')
            control=matches[0]
            b=control.box
            from top_heroes_auto.vision.guild_mail import portrait

            h,w=portrait(self.transport.last.captured).shape[:2]
            navigation=[c.box for c in fresh.controls if c.kind in {'tab','parent','event'}]
            if fresh.parent:
                navigation.append(fresh.parent.box)
            grid_gap = (control.identity == 'task-grid-vertical' and
                        {'functional-tasks-word','qualified-task-grid','outside-task-actions'} <= set(control.evidence))
            # A vertical gesture needs a clear centerline, not a button-width ROI.
            # Only the qualified grid's current, card-disjoint gutter can be narrow.
            minimum_width = 2 if grid_gap else 20
            if (b.x<0 or b.y<h*.08 or b.x+b.width>w or b.y+b.height>h*.90
                    or b.width<minimum_width or b.height<20 or any(overlaps(b,q) for q in navigation)):
                raise SafetyError('Event swipe ROI crosses navigation or image boundary.')
            x=b.x+b.width//2
            start=b.y+round(b.height*.75)
            end=b.y+round(b.height*.25)
            self.transport.dispatch(self.transport.last,'swipe',(x,start,x,end,450))
            self.current=None
            time.sleep(.6)
            return
        if 'paid-modal-navigation-only' in control.evidence:
            if control.kind!='parent' or control is not frame.parent or not frame.page.endswith(':paid-modal'):
                raise SafetyError('Purchase modal permits only its qualified close.')
            self.current = None
            fresh = self.observe()
            if (runtime_key(fresh.identity)!=runtime_key(frame.identity) or fresh.page!=frame.page or fresh.popup
                    or fresh.parent!=control or fresh.coverage_known
                    or fresh.controls or 'UNQUALIFIED_PAID_MODAL_CONTENT' not in fresh.blocked):
                raise SafetyError('Purchase modal changed on fresh capture; no input.')
            self.current = None  # Consume before dispatch; never retry uncertain input.
            self.transport.dispatch(self.transport.last,'tap',fresh.parent.box.center)
            time.sleep(.5)
            return
        if control.kind in {'tab','parent','child'}:
            if not frame.page.startswith('event:') or control not in (*frame.controls,frame.parent):
                raise SafetyError('No qualified event tab/parent edge.')
            self.transport.dispatch(self.transport.last,'tap',control.box.center)
            self.current = None
            time.sleep(.5)
            return
        if (frame.page != 'home' or frame.popup or not frame.event_scan_performed or control not in frame.controls or
                control.kind != 'event' or self.entered is not None):
            raise SafetyError('Event navigation lacks a qualified current-frame edge.')
        reference = self.navigation_image.copy()
        before = frame
        attempts = []
        for _ in range(3):
            self.current = None
            time.sleep(.35)
            fresh = self.observe()
            if (fresh.page != 'home' or fresh.popup or not fresh.event_scan_performed
                    or fresh.stable_id != before.stable_id
                    or runtime_key(fresh.identity) != runtime_key(before.identity)):
                raise SafetyError('Event reacquisition context/runtime changed; no input.')
            if 'AMBIGUOUS_ICON_CORE' in fresh.blocked:
                attempts.append(dict(capture=fresh.capture,blocked='AMBIGUOUS_ICON_CORE'))
                continue
            matches = [c for c in fresh.controls if c.kind=='event'
                       and stable_entry_match(reference,control.box,self.navigation_image,c.box,require_geometry=False)]
            attempts.append(dict(capture=fresh.capture,matches=[asdict(c.box) for c in matches]))
            if len(matches) != 1:
                continue
            target = matches[0]
            if not stable_entry_match(reference,control.box,self.navigation_image,target.box):
                continue
            # A duplicate candidate near this one invalidates uniqueness even if
            # only one cropped patch happens to reach the pixel threshold.
            if any(c is not target and c.kind=='event' and overlaps(c.box,target.box) for c in fresh.controls):
                continue
            point = target.box.center
            if not (target.box.x < point[0] < target.box.x+target.box.width
                    and target.box.y < point[1] < target.box.y+target.box.height):
                raise SafetyError('Event tap is outside current interior.')
            proof=dict(previous_capture=before.capture,previous_box=asdict(control.box),
                       capture=fresh.capture,current_box=asdict(target.box),tap=point,
                       runtime=fresh.identity,attempts=attempts,kind='NAVIGATION_ONLY')
            if hasattr(self,'folder'):
                with (self.folder/'entry-reacquisition.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(proof)+'\n')
            self.current = None
            self.transport.dispatch(self.transport.last,'tap',point)
            self.entered = control.identity
            self.pending_entry_proof=proof
            time.sleep(.5)
            # The shared explorer captures afresh and verifies event: context
            # before any nested navigation or independent reward evaluation.
            return
        raise EventEntryUnstable('Event entry could not be uniquely reacquired in 3 fresh frames; no input.')

    def claim(self, frame, control):
        if control is None or frame is not getattr(self,'current',None) or control not in frame.controls or control.kind!='reward':
            raise SafetyError('No qualified current event free reward.')
        title = self.event_title
        # Reprove unchanged availability, identity and exact geometry before reservation.
        fresh = self.observe()
        matches = [c for c in fresh.controls if c.kind=='reward' and c.identity==control.identity]
        if (runtime_key(fresh.identity)!=runtime_key(frame.identity) or fresh.page!=frame.page or fresh.popup
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
            return self._claim_postcondition(before,target,title)

        try:
            result=dispatch_once(store,task,self.session.manager.namespace,fresh,control,
                event_identity=title,persistent_identity=self.session.target['persistent_identity'],
                dispatch=dispatch,postcondition=postcondition,persist=persist)
            store.finish_task_run(task,result['result'],report_path=str(path))
            return result
        except Exception as exc:
            store.finish_task_run(task,'BLOCKED',error=str(exc),report_path=str(path))
            raise

    def _claim_postcondition(self,before,target,title):
        """Five settling captures; a qualified receipt reserves two underlying captures."""
        observations=[]
        underlying=[]
        receipt=None
        capture_limit=5
        for number in range(7):
            if number>=capture_limit:
                return []
            time.sleep(.5)
            after=self.observe()  # First post-action capture is always retained.
            if runtime_key(after.identity) != runtime_key(before.identity):
                return []
            if after.popup:
                if self.transport.last.overlay.state == ScreenState.REWARD_RECEIPT:
                    receipt = after.capture
                    # A late qualified receipt needs two subsequent proof frames.
                    # Unknown-only settling and early receipts keep the old budget.
                    capture_limit=max(capture_limit,number+3)
                self.dismiss(after)
                continue
            if after.page == 'UNKNOWN':
                continue  # Bounded capture-only settling; never input on UNKNOWN.
            if after.page != before.page:
                return []
            same=[r for r in self.rows if r['identity']==target.identity]
            if len(same)!=1 or same[0]['state']!='NOT_AVAILABLE':
                # A supported task control may remove a whole free prefix.
                # Verify actual body change AND exact counter decrement,
                # never a missing row or receipt alone.
                underlying.append(after.capture)
                if receipt and len(underlying)>=2:
                    proof=dict(identity=before.identity,capture=before.capture,page=before.page,
                               reward=target.identity,event=title)
                    effect=removal_effect(proof,[underlying[0],underlying[-1]],receipt)
                    if effect:
                        return effect
                if same and same[0]['state']=='AVAILABLE':
                    return []
                continue
            if ('qualified-achievement-cards' in target.evidence
                    and not {'explicit-claimed-label','original-green-control-absent'}.issubset(same[0].get('evidence',()))):
                continue
            if ('qualified-task-grid' in target.evidence and not receipt
                    and not {'explicit-claimed-label','original-green-control-absent'}.issubset(same[0].get('evidence',()))):
                continue  # No receipt: require the independently qualified explicit claimed state.
            observations.append(dict(identity=list(after.identity),capture=after.capture,
                event=title,page=after.page,reward=target.identity,state='NOT_AVAILABLE',
                independent_evidence=['same-reward-card','claim-control-replaced-by-unavailable-state',*same[0].get('evidence',())]))
            if len(observations)==2:
                return observations
        return []


    def recover_home(self):
        result, path, _ = self.session.recover()
        self.current = None
        self.entered = None
        self.event_title = None
        return dict(status=result.status.value, report=str(path))

    def dismiss(self, frame):
        if frame is not self.current or not frame.popup:
            raise SafetyError('No qualified current popup dismissal.')
        observed = self.transport.last
        point = dismiss_overlay_bottom_left(observed.captured, observed.overlay)
        self.overlay_budget.reserve(observed.overlay)
        signature=overlay_signature(observed.overlay)
        if (observed.overlay.state == ScreenState.HOME_OVERLAY
                and self.overlay_budget.counts[signature] == 2):
            # Same qualified underlying-Home fallback already used by recovery.
            # No generic UNKNOWN Back or paid-close coordinate is introduced.
            self.transport.dispatch(observed,'keyevent',(4,))
        else:
            self.transport.dispatch(observed,'tap',point)
        self.current = None
        time.sleep(.5)

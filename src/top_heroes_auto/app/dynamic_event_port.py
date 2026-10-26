"""Current-frame event entry transport. Unknown event contents remain fail-closed."""
import json
import time
from dataclasses import asdict, replace

import cv2

from top_heroes_auto.app.event_claim_reconciliation import bind_saved_rewards, reconcile_possible
from top_heroes_auto.app.event_task_effect import removal_effect
from top_heroes_auto.app.fixed_reward_port import FixedRewardPort
from top_heroes_auto.automation.dynamic_events import (
    Control,
    EventEntryUnstable,
    EventFrame,
    EventNavigationRejected,
    overlaps,
)
from top_heroes_auto.automation.event_journal import dispatch_once
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.automation.overlays import (
    DISMISSIBLE,
    OverlayBudget,
    dismiss_overlay_bottom_left,
    overlay_signature,
)
from top_heroes_auto.automation.timing import measured, pause, poll
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
from top_heroes_auto.vision.event_book_objectives import book_context, book_rows
from top_heroes_auto.vision.event_collaboration_hub import collaboration_hub, collaboration_training
from top_heroes_auto.vision.event_competitive import competitive_indicator_contract
from top_heroes_auto.vision.event_inline_objectives import inline_objective_rows
from top_heroes_auto.vision.event_paid_modal import paid_modal_navigation
from top_heroes_auto.vision.event_reacquisition import stable_entry_match
from top_heroes_auto.vision.event_task_grid import task_grid_rows, task_grid_shell, unresolved_grid_actions
from top_heroes_auto.vision.fixed_rewards import EventNavigationDetector
from top_heroes_auto.vision.guild_mail import portrait
from top_heroes_auto.vision.local_ocr import read_words
from top_heroes_auto.vision.models import BoundingBox, ScreenState
from top_heroes_auto.vision.resources import template_folder
from top_heroes_auto.vision.system_dialog import system_dialog

UNQUALIFIED_CHILD_PAGE = 'UNQUALIFIED_CHILD_PAGE'


def unqualified_child_exit(previous, back, *, page, entered, popup, dialog, rendering, tolerance=4):
    """Back-only exit from an UNKNOWN page entered from a qualified event page (user decision 2026-10-26).

    Run22: one unsupported seasonal child page ended the whole Event traversal because
    UNKNOWN allowed no input. This grants exactly one navigation control: the standard
    Back anchor, matched now at the same place as the qualified parent's own Back.
    It never grants claim, tab, child or scroll permission; the caller records the
    page as BLOCKED and the explorer accepts it only right after a child edge.
    """
    if (page != 'UNKNOWN' or not entered or popup or dialog or rendering or back is None
            or previous is None or previous.popup or not previous.page.startswith('event:')
            or previous.page.endswith(':unqualified-child')
            or previous.parent is None or previous.parent.identity != 'current-back'):
        return None
    old = previous.parent.box
    if any(abs(a-b) > tolerance for a, b in ((back.x, old.x), (back.y, old.y),
                                              (back.width, old.width), (back.height, old.height))):
        return None
    return Control('current-back', back, ('qualified-parent-same-visit', 'same-standard-back-anchor',
                                          'unqualified-child-exit-only'), 'parent')


class DynamicEventPort:
    def __init__(self, session, folder):
        self.session, self.folder = session, folder
        self.transport = FixedRewardPort(session.manager, session.snapshot, session.index, session.name,
                                         folder, session.check, session.cancelled)
        self.transport.detector = EventNavigationDetector()
        self.transport.record_tap_geometry = True
        self.current = None
        self.entered = None
        self.overlay_budget = OverlayBudget()
        self.rows = ()
        self.mission_rows = ()
        self.home_icon_cores = {}
        self.menu_icon_cores = {}
        self.event_title = None
        self.child_origin = None
        self.unavailable_observations = {}
        # A later daily/seasonal unavailable screen cannot prove an old action.
        # Automatic reconciliation is limited to actions from THIS live visit.
        # Historical POSSIBLE locks require their own original action evidence.
        self.pending_claim_ids = set()
        self.task_context = cv2.imread(str(template_folder().parent/'tasks/phase8/personal-task-tab.png'))

    @measured('event_observation')
    def observe(self):
        if self.current is not None and self.current.render_pending:
            pause(time.sleep, .75)  # Only the explorer's bounded capture-only settling path.
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
        self.mission_rows = ()
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
                                if stable_entry_match(prior,box,image,candidate.icon_box,require_geometry=False)]
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
            from top_heroes_auto.vision.relic_expedition import confirm_send

            mission_modal = confirm_send(image)
            shell = (dict(page='event:relic-expedition:confirm',title='relic-expedition-confirm',
                          back=mission_modal['close'],tabs=[],selected=[],permission='MISSION_CONFIRM')
                     if mission_modal else event_shell(image,observed.box('back'),reader=read_words))
            if shell is None:
                shell=competitive_navigation_shell(image,observed.box('back'))
            if shell is None:
                shell=task_grid_shell(image)
            if shell is None:
                shell=achievement_shell(image)
            if shell is None:
                shell=collaboration_hub(image)
            if shell is None:
                shell=collaboration_training(image)
            if shell is None:
                from top_heroes_auto.vision.event_chapter import chapter_navigation

                shell=chapter_navigation(image, observed.box('back'))
            if shell:
                page = shell['page']
                from top_heroes_auto.vision.event_nested_tabs import reward_task_strip

                nested = reward_task_strip(image) if not shell.get('permission') else None
                if nested:
                    page += ':nested-'+nested['selected']
                    controls.append(Control(nested['identity'], nested['box'], nested['evidence'], 'tab'))
                self.event_title = shell['title']
                grid=shell.get('permission')=='TASK_GRID'
                achievements=shell.get('permission')=='ACHIEVEMENTS'
                self.rows = (achievement_rows(image,shell,reader=read_words) if achievements else
                             task_grid_rows(image,shell,reader=read_words) if grid else
                             (() if shell.get('permission') in {'BACK_ONLY', 'KNOWN_BLOCKER_EXIT'} else
                              task_reward_rows(image,self.task_context,reader=read_words)))
                context=(None if grid or achievements or shell.get('permission') in {'BACK_ONLY', 'KNOWN_BLOCKER_EXIT'} else
                         task_context_box(image,self.task_context))
                inline = (inline_objective_rows(image,reader=read_words)
                          if context is None and not grid and not achievements and not shell.get('permission') else ())
                if inline:
                    self.rows = inline
                    page = 'event:'+shell['title']+':inline-objectives'
                book = book_context(image) if not shell.get('permission') and context is None and not inline else None
                if book:
                    self.rows=book_rows(image,reader=read_words)
                    page='event:'+shell['title']+':book-objectives'
                    if self.rows:
                        blocked.append('BOOK_FREE_ENTITLEMENT_UNPROVEN')
                if context is not None or grid or achievements or inline or book:
                    if not grid and not achievements and not inline and not book:
                        page = 'event:'+shell['title']+':personal-tasks'
                    self.rows = bind_saved_rewards(image, self.rows,
                        self.session.manager.store.reward_claims(self.session.manager.namespace, self.session.index),
                        persistent_identity=self.session.target['persistent_identity'], index=self.session.index,
                        family='book-objectives' if book else 'inline-objectives' if inline else 'achievement-cards' if achievements else 'race-task-grid' if grid else 'personal-tasks')
                    if any(r['state'] == 'UNKNOWN' and 'free-entitlement-unproven' not in r['evidence']
                           for r in self.rows):
                        blocked.append('UNRESOLVED_SAVED_REWARD_IDENTITY')
                    for row in self.rows:
                        if row['state'] != 'NOT_AVAILABLE':
                            self.unavailable_observations.pop(row['identity'], None)
                            continue
                        if (achievements or inline or book) and 'explicit-claimed-label' not in row['evidence']:
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
                            period='unknown-period'
                            from top_heroes_auto.vision.relic_expedition import quick_send

                            if quick_send(image,self.task_context,reader=None):
                                from top_heroes_auto.automation.expedition_journal import collection_period

                                period=collection_period(self.session.manager.store.reward_claims(
                                    self.session.manager.namespace,self.session.index),
                                    self.session.target['persistent_identity'],image,row)
                            controls.append(Control(row['identity'],row['box'],row['evidence'],
                                'reward',cost='FREE',available=True,forbidden=forbidden,period=period))
                    if grid:
                        if unresolved_grid_actions(image,shell,self.rows):
                            blocked.append('UNQUALIFIED_TASK_GRID_ACTION')
                        controls.append(Control('task-grid-vertical',shell['scroll'],
                            ('functional-tasks-word','qualified-task-grid','outside-task-actions'),'scroll'))
                    elif book:
                        controls.append(Control('book-objective-list',book['scroll'],
                            ('qualified-book-objectives','paired-functional-book-chrome','outside-action-column'),'scroll'))
                    elif inline and len(self.rows)>=2 and all(
                            'qualified-group-buy-objectives' in r['evidence'] for r in self.rows):
                        first,last=self.rows[0]['row'],self.rows[-1]['row']
                        surface=BoundingBox(first.x+round(first.width*.20),first.y+20,
                            round(first.width*.30),last.y+last.height-first.y-40)
                        controls.append(Control('public-objective-list',surface,
                            ('paired-group-buy-functional-titles','complete-reward-card','outside-action-column'),'scroll'))
                    elif len(self.rows)>=2 and not inline:
                        first,last=self.rows[0]['row'],self.rows[-1]['row']
                        # Gesture stays wholly within CURRENT complete reward cards,
                        # left of their action column and above the paid refresh bar.
                        surface=BoundingBox(first.x+round(first.width*.20),first.y+20,
                            round(first.width*.40),last.y+last.height-first.y-40)
                        controls.append(Control('task-list-vertical',surface,
                            ('selected-task-context','complete-card-list','outside-action-column'),'scroll'))
                if context is not None:
                    from top_heroes_auto.vision.relic_expedition import (
                        mission_list_surface,
                        mission_rows,
                        quick_send,
                    )

                    send = quick_send(image,self.task_context,reader=read_words)
                    self.mission_rows = mission_rows(image,self.task_context,reader=read_words) if send else ()
                    if send:
                        # Never fall back to card-count geometry on this page.
                        controls = [c for c in controls if c.identity != 'task-list-vertical']
                        surface = mission_list_surface(image, self.task_context)
                        if surface:
                            controls.append(Control('task-list-vertical', surface['box'],
                                                    surface['evidence'], 'scroll'))
                    if send and any(r['state']=='DISPATCHABLE' for r in self.mission_rows) and not any(
                            r['state'] in {'COMPLETED','UNKNOWN'} for r in self.mission_rows):
                        controls.append(Control('relic-expedition-quick-send',send['box'],
                            send['evidence'],'mission',cost='FREE',available=True,forbidden=send['forbidden']))
                if shell.get('permission')=='BACK_ONLY':
                    competitive_evidence=competitive_indicator_contract(image,shell,reader=read_words)
                contract=('ACHIEVEMENTS' if achievements and len(self.rows)==len(shell['cards']) and all(r['state']!='UNKNOWN' for r in self.rows) else 'UNSUPPORTED' if achievements else 'TASK_GRID' if grid else (
                    'COMPETITIVE_OUT_OF_SCOPE_INDICATORS' if competitive_evidence else
                    ('UNSUPPORTED' if shell.get('permission')=='BACK_ONLY' else
                     event_body_contract(image,self.rows,self.task_context,reader=read_words))))
                if mission_modal:
                    contract='MISSION_CONFIRM'
                    controls.append(Control('relic-expedition-confirm-send',mission_modal['box'],
                        mission_modal['evidence'],'mission',cost='FREE',available=True))
                if self.mission_rows:
                    contract='RELIC_MISSIONS'
                    if any(r['state']=='UNKNOWN' for r in self.mission_rows):
                        blocked.append('UNQUALIFIED_MISSION_STATE')
                if book:
                    contract='BOOK_OBJECTIVES'
                    blocked.append('BOOK_MILESTONES_AND_UNQUALIFIED_CONTROLS')
                if shell.get('permission')=='NAVIGATION_HUB':
                    contract='NAVIGATION_HUB'
                    for key,box in shell['children']:
                        controls.append(Control(key,box,shell['evidence'],'child'))
                if shell.get('permission')=='KNOWN_BLOCKER_EXIT':
                    contract='UNSUPPORTED'
                    blocked.append(shell.get('blocking_reason','TRAINING_MAP_REWARDS_UNQUALIFIED'))
                coverage_known=contract!='UNSUPPORTED'
                achievement = achievement_navigation(image)
                if achievement and shell.get('permission') not in {'BACK_ONLY', 'KNOWN_BLOCKER_EXIT'}:
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
                    (*shell['evidence'],'current-exit-control') if shell.get('permission') in {'NAVIGATION_HUB', 'KNOWN_BLOCKER_EXIT'} else
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
                    ('paid-modal-navigation-only','unique-red-close','qualified-paid-offer-context','explicit-vnd'),
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
        if self.mission_rows:
            # View comparison only, never a durable mission/occurrence key.
            # Exclude timers, ticker and animated artwork from scroll progress.
            parts=[]
            for r in self.mission_rows:
                b=r['row']
                patch=image[b.y+6:b.y+b.height-6,b.x+8:b.x+round(b.width*.72)]
                parts.append((r['state'],b.y,hashlib.sha256(patch.tobytes()).hexdigest()))
            fingerprint=hashlib.sha256(repr(parts).encode()).hexdigest()
        popup = (observed.overlay.state in DISMISSIBLE and
                 (self.entered is None or observed.overlay.state != ScreenState.HOME_OVERLAY))
        if dialog:
            popup = False  # Never route Android dialogs through game popup dismissal.
            blocked.append(dialog['reason'])
        transition=(competitive_rank_transition(image) if self.entered and page=='UNKNOWN' and not popup and not dialog else None)
        rendering=bool(self.entered and page=='UNKNOWN' and not popup and not dialog
                       and (blank_event_render(image) or transition is not None))
        exit_control=unqualified_child_exit(getattr(self, 'child_origin', None), observed.box('back'), page=page,
                                            entered=self.entered, popup=popup, dialog=dialog, rendering=rendering)
        if not rendering:
            self.child_origin = None
        if exit_control is not None:
            page = 'event:'+self.entered+':unqualified-child'
            parent = exit_control
            controls = []  # Back only: no reward, tab, child or scroll permission here.
            coverage_known = False
            blocked.append(UNQUALIFIED_CHILD_PAGE)
        self.current = EventFrame(str(c.source_image),identity,page,fingerprint,tuple(controls),
                                  coverage_known=coverage_known, parent=parent, popup=popup, blocked=tuple(blocked),
                                  stable_id=self.session.target['persistent_identity'], event_scan_performed=event_scan_performed,
                                  selected_tabs=tuple(BoundingBox(**b) for b in shell['selected']) if shell else (),
                                  mission_states=tuple({**r,'row':asdict(r['row'])} for r in self.mission_rows),
                                  mission_at_top=bool(self.mission_rows and context is not None and
                                      self.mission_rows[0]['row'].y-context.y-context.height < image.shape[0]*.04),
                                  render_pending=rendering)
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

    def finish_expedition(self, frame):
        from top_heroes_auto.automation.expedition import finish_expedition

        def persist(report):
            (self.folder/'expedition-session.json').write_text(
                json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return finish_expedition(self,frame,persist=persist)

    def check_cancelled(self):
        self.session.manager.check_cancelled()

    def scroll_missions(self, frame, *, reverse):
        """Current qualified container surface, no historical coordinates."""
        if frame is not self.current or frame.popup:
            raise SafetyError('No current expedition list to scroll.')
        fresh=self.observe()
        if (runtime_key(fresh.identity)!=runtime_key(frame.identity) or fresh.page!=frame.page
                or fresh.popup):
            raise SafetyError('Expedition list changed before scroll.')
        controls=[c for c in fresh.controls if c.kind=='scroll' and c.identity=='task-list-vertical']
        if len(controls)!=1:
            raise SafetyError('Mission scroll surface unqualified.')
        b=controls[0].box
        if any(overlaps(b,c.box) for c in fresh.controls if c.kind in {'mission','tab','parent'}):
            raise SafetyError('Mission scroll intersects navigation or dispatch.')
        x=b.center[0]
        start,end=b.y+round(b.height*.75),b.y+round(b.height*.25)
        if reverse:
            start,end=end,start
        self.transport.dispatch(self.transport.last,'swipe',(x,start,x,end,350))
        self.current=None

    def _scroll_blockers_safe(self, frame, control):
        """A journal lock denies its reward, not a proven card-disjoint swipe.

        This does not remove blockers, alter rows, expose reward controls or
        change a journal. Unknown visual controls still deny navigation. Run20
        rejected a current task-grid gutter because a known free card was held
        by an old POSSIBLE action, then spent a full recovery leaving the grid.
        """
        blocked = set(frame.blocked)
        if 'qualified-book-objectives' in control.evidence:
            return not (blocked-{'BOOK_MILESTONES_AND_UNQUALIFIED_CONTROLS'})
        if not blocked:
            return True
        held_markers = {'unresolved-saved-reward-identity', 'ambiguous-saved-reward-identity'}
        rows = getattr(self, 'rows', ())
        if (not frame.page.endswith((':personal-tasks', ':race-task-grid'))
                or not rows or not blocked <= {
                    'UNRESOLVED_SAVED_REWARD_IDENTITY', 'UNQUALIFIED_TASK_GRID_ACTION'}):
            return False
        held = [r for r in rows if r['state'] == 'UNKNOWN']
        required = {'complete-reward-card', 'qualified-control-color'}
        required.add('completed-fraction-full-bar-and-free-label' if frame.page.endswith(':race-task-grid')
                     else 'sole-no-cost-action-label')
        if not held or any(not held_markers.intersection(r['evidence'])
                           or not required <= set(r['evidence'])
                           or 'ambiguous-task-caption' in r['evidence'] for r in held):
            return False
        if frame.page.endswith(':race-task-grid'):
            shell = task_grid_shell(self.navigation_image)
            # Only for checking that EVERY green control is geometrically
            # accounted for. The actual held rows remain UNKNOWN throughout.
            accounted = tuple(dict(r, state='AVAILABLE') if r in held else r for r in rows)
            return shell is not None and not unresolved_grid_actions(self.navigation_image, shell, accounted)
        return blocked == {'UNRESOLVED_SAVED_REWARD_IDENTITY'}

    def navigate(self, frame, control):
        if frame is not self.current:
            raise SafetyError('Stale event navigation frame.')
        if control.kind=='scroll':
            if (not frame.page.startswith('event:') or not frame.coverage_known or frame.popup
                    or control not in frame.controls or not (frame.page.endswith(':personal-tasks')
                    or 'qualified-menu-grid' in control.evidence or 'qualified-task-grid' in control.evidence
                    or 'qualified-book-objectives' in control.evidence)):
                raise SafetyError('No qualified current Event scroll surface.')
            self.current=None
            fresh=self.observe()
            matches=[c for c in fresh.controls if c.kind=='scroll' and c.identity==control.identity]
            if runtime_key(fresh.identity)!=runtime_key(frame.identity) or fresh.stable_id!=frame.stable_id:
                raise SafetyError('Event scroll runtime changed on fresh capture; no input or recovery.')
            if (fresh.page!=frame.page or fresh.popup
                    or not fresh.coverage_known or not self._scroll_blockers_safe(fresh, control)
                    or len(matches)!=1):
                raise EventNavigationRejected('Event scroll changed on fresh capture; no input.')
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
            pause(time.sleep, .6)
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
            pause(time.sleep, .5)
            return
        if control.kind in {'tab','parent','child'}:
            if not frame.page.startswith('event:') or control not in (*frame.controls,frame.parent):
                raise SafetyError('No qualified event tab/parent edge.')
            # One-shot origin for the Back-only exit; consumed by the next settled observation.
            self.child_origin = frame if control.kind == 'child' else None
            self.transport.dispatch(self.transport.last,'tap',control.box.center)
            self.current = None
            pause(time.sleep, .5)
            return
        if (frame.page != 'home' or frame.popup or not frame.event_scan_performed or control not in frame.controls or
                control.kind != 'event' or self.entered is not None):
            raise SafetyError('Event navigation lacks a qualified current-frame edge.')
        reference = self.navigation_image.copy()
        before = frame
        attempts = []
        for _ in range(3):
            self.current = None
            pause(time.sleep, .35)
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
            pause(time.sleep, .5)
            # The shared explorer captures afresh and verifies event: context
            # before any nested navigation or independent reward evaluation.
            return
        raise EventEntryUnstable('Event entry could not be uniquely reacquired in 3 fresh frames; no input.')

    def send_mission(self, frame, control):
        """One durable dispatch of the qualified free expedition action, never a reward receipt."""
        if (frame is not self.current or frame.popup or control not in frame.controls
                or control.kind != 'mission' or control.identity not in {
                    'relic-expedition-quick-send','relic-expedition-confirm-send'}):
            raise SafetyError('Unqualified expedition send.')
        fresh = self.observe()
        matches = [c for c in fresh.controls if c.kind == 'mission' and c.identity == control.identity]
        if (runtime_key(fresh.identity) != runtime_key(frame.identity) or fresh.page != frame.page
                or fresh.popup or len(matches) != 1 or matches[0] != control):
            raise SafetyError('Expedition send changed; no input.')
        # Reuse the durable one-shot boundary; report separately from reward claims.
        action = replace(control,kind='reward')
        if control.identity=='relic-expedition-confirm-send':
            from top_heroes_auto.automation.expedition_journal import dispatch_period

            action=replace(action,period=dispatch_period(self.session.manager.store.reward_claims(
                self.session.manager.namespace,self.session.index),self.session.target['persistent_identity']))
        proof = replace(fresh,controls=(action,))
        if control.identity == 'relic-expedition-quick-send':
            # This opens the qualified selection modal; it sends no expedition.
            # Historical journal rows stay locked and are never rewritten.
            from top_heroes_auto.automation.dynamic_events import free_geometry

            point = free_geometry(action)
            if hasattr(self, 'navigation_image') and getattr(self, 'mission_rows', ()):
                self.dispatch_origin = (fresh, self.navigation_image.copy(), tuple(self.mission_rows))
            self.current = None
            self.transport.dispatch(self.transport.last,'tap',point)
            after = poll(self.observe, lambda f: f.page=='event:relic-expedition:confirm',
                         cancelled=getattr(self.session,'cancelled',lambda:False))
            opened = (runtime_key(after.identity) == runtime_key(frame.identity)
                      and after.page == 'event:relic-expedition:confirm' and not after.popup
                      and any(c.identity == 'relic-expedition-confirm-send' for c in after.controls))
            return dict(result='NAVIGATION_SUCCESS' if opened else 'NAVIGATION_UNVERIFIED',
                        mission_dispatched=False, navigation_dispatched=True, journal='NONE',
                        action_type='OPEN_MISSION_SELECTION', first_post_capture=after.capture,
                        first_post_page=after.page)
        store = self.session.manager.store
        task = store.create_task_run(self.session.manager.namespace,'event-mission-send',
                                    self.session.index,self.session.name)
        path = self.folder/f'mission-{task}.json'
        def persist(result):
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        def dispatch(before,target,point,intent):
            if self.current is not fresh or before is not proof or target is not action:
                raise SafetyError('Mission frame ownership changed.')
            self.transport.dispatch(self.transport.last,'tap',point,before_input=intent)
            self.current = None
        result = dispatch_once(store,task,self.session.manager.namespace,proof,action,
            event_identity='relic-expedition-mission',persistent_identity=self.session.target['persistent_identity'],
            dispatch=dispatch,postcondition=self._mission_postcondition,persist=persist,action_type='DISPATCH')
        if result.get('claim_dispatched'):
            after = self.current or self.observe()
            result['first_post_capture'] = after.capture
            result['first_post_page'] = after.page
        result['mission_dispatched'] = result.pop('claim_dispatched',False)
        result['action_type'] = 'MISSION_SEND_NOT_REWARD'
        persist(result)
        store.finish_task_run(task,result['result'],report_path=str(path))
        return result

    @measured('postcondition_verification')
    def _mission_postcondition(self, before, target):
        """Fresh same-visit available-card -> timer proof; no receipt required."""
        from top_heroes_auto.vision.relic_expedition import dispatch_transition

        origin = getattr(self, 'dispatch_origin', None)
        if not origin or runtime_key(origin[0].identity) != runtime_key(before.identity):
            return []
        observations = []
        matched = None
        inspected = set()
        scrolls = 0
        for _ in range(6):
            self.check_cancelled()
            after = self.observe()
            if runtime_key(after.identity) != runtime_key(before.identity) or after.popup:
                return []
            if after.page != origin[0].page:
                if after.page in {'UNKNOWN', before.page}:
                    continue
                return []
            changes = dispatch_transition(origin[1], self.navigation_image,
                                           origin[2], self.mission_rows)
            keys = {(r['row'].x,r['row'].y,r['row'].width,r['row'].height) for r in changes}
            if not keys:
                if (matched is not None or scrolls >= 3 or after.fingerprint in inspected
                        or not after.mission_states or not after.coverage_known
                        or not any(c.kind=='scroll' and c.identity=='task-list-vertical' for c in after.controls)):
                    return []
                # A dispatched card may sort below remaining available cards.
                # Search only the current qualified mission list, never resend.
                inspected.add(after.fingerprint)
                self.scroll_missions(after, reverse=False)
                scrolls += 1
                continue
            if matched is not None and keys != matched:
                return []
            matched = keys
            observations.append(dict(identity=list(after.identity), capture=after.capture,
                event='relic-expedition-mission',page=before.page,reward=target.identity,
                state='RUNNING',actual_page=after.page,origin_capture=origin[0].capture,
                visible_missions_started=len(changes), transitions=[{**r,'row':asdict(r['row'])} for r in changes],
                independent_evidence=['same-mission-card-title-and-items',
                                      'available-control-replaced-by-positive-running-timer']))
            if len(observations)==2:
                return observations
        return []

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
            if result.get('claim_dispatched') and result.get('journal')=='RESERVED':
                self.pending_claim_ids=getattr(self,'pending_claim_ids',set()) | {result['claim_id']}
            store.finish_task_run(task,result['result'],report_path=str(path))
            return result
        except Exception as exc:
            store.finish_task_run(task,'BLOCKED',error=str(exc),report_path=str(path))
            raise

    @measured('postcondition_verification')
    def _claim_postcondition(self,before,target,title):
        """Five settling captures; a qualified receipt reserves two underlying captures."""
        observations=[]
        underlying=[]
        receipt=None
        capture_limit=5
        for number in range(7):
            if number>=capture_limit:
                return []
            if number:
                pause(time.sleep, .3)
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
            body_proven = ('selected-task-context' not in target.evidence or
                           (len(same)==1 and 'unique-saved-card-body-agreement' in same[0].get('evidence',())))
            if len(same)!=1 or same[0]['state']!='NOT_AVAILABLE' or not body_proven:
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
            if ({'qualified-achievement-cards','qualified-inline-objectives','qualified-book-objectives'} & set(target.evidence)
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
        # An entered Event may have positively qualified parent edges which the
        # generic Home detector does not model. Consume only those current edges;
        # this grants no claim permission and never invents Back on UNKNOWN.
        edges=[]
        original=None
        seen=set()
        try:
            for _ in range(4):
                if not self.entered:
                    break
                frame=self.observe()
                binding=(frame.stable_id,runtime_key(frame.identity))
                if original is None:
                    original=binding
                if binding!=original:
                    raise SafetyError('Event parent recovery identity changed.')
                parent=frame.parent
                if (frame.popup or not frame.page.startswith('event:') or parent is None
                        or parent.kind!='parent'):
                    break
                key=(frame.page,parent.identity,parent.box)
                if key in seen:
                    break
                seen.add(key)
                edges.append(dict(capture=frame.capture,page=frame.page,
                                  parent=asdict(parent),identity=list(frame.identity)))
                self.navigate(frame,parent)
        finally:
            if edges:
                with (self.folder/'parent-recovery.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(edges)+'\n')
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
        pause(time.sleep, .5)

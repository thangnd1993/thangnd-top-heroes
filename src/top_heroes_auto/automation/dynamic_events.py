"""Bounded instance-local event traversal. Visual adapters own action qualification.

Names and coordinates are never traversal or durable journal identities. A badge
is navigation evidence only. Unknown content is recorded, never counted exhausted.
"""
from dataclasses import asdict, dataclass, field
from typing import Protocol

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.models import BoundingBox


@dataclass(frozen=True)
class Control:
    identity: str
    box: BoundingBox
    evidence: tuple[str, ...]
    kind: str = 'child'
    cost: str = 'UNKNOWN'
    available: bool = False
    diamond_reward: bool = False
    period: str = 'unknown-period'
    forbidden: tuple[BoundingBox, ...] = ()


@dataclass(frozen=True)
class EventFrame:
    capture: str
    identity: tuple[int, str, str, str]
    page: str
    fingerprint: str
    controls: tuple[Control, ...] = ()
    coverage_known: bool = False
    parent: Control | None = None
    popup: bool = False
    blocked: tuple[str, ...] = ()
    render_pending: bool = False


@dataclass(frozen=True)
class Limits:
    actions: int = 100
    transitions: int = 50
    depth: int = 4
    observations: int = 160
    scrolls: int = 4

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in asdict(self).values()):
            raise ValueError('Positive integer traversal limits required.')


@dataclass
class Exploration:
    result: str = 'BLOCKED'
    actions: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    events: dict = field(default_factory=dict)
    rewards: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    paid_rejected: list = field(default_factory=list)
    recoveries: list = field(default_factory=list)
    return_home: str = 'NOT_STARTED'


class EventPort(Protocol):
    def observe(self) -> EventFrame: ...
    def navigate(self, frame: EventFrame, control: Control): ...
    def claim(self, frame: EventFrame, control: Control) -> dict: ...
    def dismiss(self, frame: EventFrame): ...


def overlaps(a, b):
    return (a.x < b.x+b.width and b.x < a.x+a.width and
            a.y < b.y+b.height and b.y < a.y+a.height)


def free_geometry(control):
    """A word/badge alone cannot grant claim permission; cost must be positive proof."""
    if (control.kind != 'reward' or control.cost != 'FREE' or not control.available or
            len(set(control.evidence)) < 3 or not control.identity or not control.period or
            control.box.width <= 0 or control.box.height <= 0 or
            any(overlaps(control.box, region) for region in control.forbidden)):
        raise SafetyError('Free target, availability, context or paid exclusion is unqualified.')
    return control.box.center


class DynamicEventExplorer:
    def __init__(self, limits=None):
        self.limits = limits or Limits()

    def run(self, port, *, persist=lambda report: None):
        report = Exploration()
        transport = None
        captures, edges, attempted, exhausted_scrolls = set(), set(), set(), set()
        scroll_counts, scroll_views = {}, {}
        visited_tabs = set()
        stack = []
        active = None
        active_seen = False
        pending = None
        transitions = 0
        empty_home_passes = 0
        render_waits = 0
        path = []
        resume = []
        seek = None
        reentries = set()

        def block(reason, frame):
            report.blocked.append(dict(reason=reason, event=active, page=frame.page, capture=frame.capture))
            if active:
                report.events[active]['result'] = 'BLOCKED'

        try:
            for _ in range(self.limits.observations):
                frame = port.observe()
                if not frame.capture or frame.capture in captures or not frame.fingerprint:
                    raise SafetyError('Fresh evidence required after every action.')
                captures.add(frame.capture)
                if transport is None:
                    transport = frame.identity
                if frame.identity != transport:
                    raise SafetyError('Event session identity/ADB changed.')
                report.observations.append(asdict(frame))
                persist(asdict(report))
                if len(report.actions) >= self.limits.actions or transitions >= self.limits.transitions:
                    block('LIMIT_REACHED', frame)
                    break
                if frame.popup:
                    report.actions.append(dict(kind='dismiss', capture=frame.capture))
                    persist(asdict(report))
                    port.dismiss(frame)
                    continue  # Preserve event/parent stack through qualified receipts.
                if frame.page == 'UNKNOWN':
                    if (frame.render_pending and pending and pending[0] in {'event','tab','child'}
                            and render_waits < 3):
                        render_waits += 1
                        continue  # Capture only; retain the exact pending navigation edge.
                    block('UNKNOWN_SCREEN', frame)
                    break
                render_waits = 0
                if active and frame.page == 'home':
                    if not active_seen:
                        block('NO_PROGRESS',frame)
                        break
                    report.recoveries.append(dict(reason='UNEXPECTED_EVENT_EXIT',event=active,
                                                  capture=frame.capture,pending=pending))
                    candidates=[c for c in frame.controls if c.kind=='event' and c.identity==active]
                    if (active in reentries or not frame.coverage_known or frame.blocked
                            or len(candidates)!=1):
                        block('UNEXPECTED_EVENT_EXIT_UNRESOLVED',frame)
                        break
                    # Restore only the unfinished navigation route using freshly
                    # rediscovered controls. Reward attempts/journals stay intact.
                    reentries.add(active)
                    resume=[(kind,key) for _,kind,key in path]
                    seek=pending[1:] if pending and pending[0]=='scroll' else None
                    stack=['home']
                    pending=('event','home',frame.fingerprint,None)
                    control=candidates[0]
                    report.events[active]['visits']+=1
                    report.actions.append(dict(kind='event',capture=frame.capture,
                                               identity=control.identity,box=asdict(control.box),
                                               recovery='UNEXPECTED_EVENT_EXIT'))
                    persist(asdict(report))
                    port.navigate(frame,control)
                    transitions+=1
                    continue
                if pending:
                    kind, origin, signature, key = pending
                    pending = None
                    if kind == 'scroll':
                        if frame.page != origin:
                            block('SCROLL_LEFT_PAGE', frame)
                            break
                        seen = scroll_views.setdefault(key, {signature})
                        if frame.fingerprint in seen and seek is None:
                            exhausted_scrolls.add(key)
                        seen.add(frame.fingerprint)
                    elif kind == 'parent':
                        if frame.page != origin:
                            block('PARENT_NOT_VERIFIED', frame)
                            break
                    elif frame.page == origin:
                        block('NO_PROGRESS', frame)
                        break
                if resume:
                    kind,key=resume.pop(0)
                    matches=[c for c in frame.controls if c.kind==kind and c.identity==key]
                    if not frame.coverage_known or frame.blocked or len(matches)!=1:
                        block('EVENT_RESUME_ROUTE_UNQUALIFIED',frame)
                        break
                    control=matches[0]
                    if kind=='child':
                        stack.append(frame.page)
                    pending=(kind,frame.page,frame.fingerprint,(active,frame.page,key))
                    report.actions.append(dict(kind=kind,capture=frame.capture,identity=key,
                                               box=asdict(control.box),recovery='UNEXPECTED_EVENT_EXIT'))
                    persist(asdict(report))
                    port.navigate(frame,control)
                    transitions+=1
                    continue
                if seek:
                    origin,signature,key=seek
                    if frame.page!=origin:
                        block('EVENT_RESUME_PAGE_CHANGED',frame)
                        break
                    if frame.fingerprint==signature:
                        seek=None
                    else:
                        matches=[c for c in frame.controls if c.kind=='scroll' and c.identity==key[2]]
                        if (not frame.coverage_known or frame.blocked or len(matches)!=1
                                or scroll_counts.get(key,0)>=self.limits.scrolls):
                            block('EVENT_RESUME_VIEW_UNQUALIFIED',frame)
                            break
                        scroll_counts[key]=scroll_counts.get(key,0)+1
                        control=matches[0]
                        pending=('scroll',origin,frame.fingerprint,key)
                        report.actions.append(dict(kind='scroll',capture=frame.capture,identity=control.identity,
                                                   box=asdict(control.box),recovery='UNEXPECTED_EVENT_EXIT'))
                        persist(asdict(report))
                        port.navigate(frame,control)
                        transitions+=1
                        continue
                for reason in frame.blocked:
                    block(reason, frame)
                if frame.page == 'home':
                    report.return_home = 'SUCCESS'
                    candidates = [c for c in frame.controls if c.kind == 'event']
                    identities = [c.identity for c in candidates]
                    if len(set(identities)) != len(identities):
                        block('AMBIGUOUS_EVENT_IDENTITY', frame)
                        break
                    for c in candidates:
                        report.events.setdefault(c.identity, dict(result='DISCOVERED', visits=0))
                    candidate = next((c for c in candidates if report.events[c.identity]['visits'] == 0), None)
                    if candidate is None:
                        if any(report.events[c.identity]['result'] != 'EXHAUSTED' for c in candidates):
                            block('UNPROCESSED_EVENT', frame)
                        empty_home_passes += 1
                        if empty_home_passes < 2:
                            continue
                        report.result = 'SUCCESS' if frame.coverage_known and not report.blocked else 'BLOCKED'
                        break
                    empty_home_passes = 0
                    path=[]
                    active = candidate.identity
                    active_seen = False
                    report.events[active].update(result='ENTERED', visits=1)
                    stack = ['home']
                    control = candidate
                else:
                    active_seen = True
                    report.return_home = 'NOT_STARTED'
                    if not active:
                        block('EVENT_WITHOUT_ENTRY', frame)
                        break
                    if not frame.coverage_known:
                        block('UNQUALIFIED_CONTENT', frame)
                    control = None
                    for reward in (c for c in frame.controls if c.kind == 'reward'):
                        key = active, frame.page, reward.identity, reward.period
                        if key in attempted:
                            continue
                        attempted.add(key)
                        if reward.cost not in {'FREE', 'UNKNOWN'}:
                            report.paid_rejected.append(dict(event=active, page=frame.page, reward=reward.identity,
                                                             cost=reward.cost))
                            continue
                        try:
                            free_geometry(reward)
                        except SafetyError:
                            block('AMBIGUOUS_FREE_TARGET', frame)
                            continue
                        report.actions.append(dict(kind='reward', capture=frame.capture, identity=reward.identity))
                        persist(asdict(report))
                        result = port.claim(frame, reward)
                        report.rewards.append(result)
                        if result.get('journal') not in {'VERIFIED'}:
                            block(result.get('result', 'POSSIBLE'), frame)
                        persist(asdict(report))
                        control = reward
                        break
                    if control:
                        continue  # Claims consume the frame; never navigate on it.
                    for c in frame.controls:
                        key = active, frame.page, c.identity
                        if c.kind == 'tab' and (active,tuple(stack),c.identity) not in visited_tabs:
                            visited_tabs.add((active,tuple(stack),c.identity))
                            path=[edge for edge in path if not (edge[0]==len(stack) and edge[1]=='tab')]
                            path.append((len(stack),'tab',c.identity))
                            control = c
                            break
                        if c.kind == 'child' and key not in edges:
                            if len(stack) >= self.limits.depth:
                                block('DEPTH_LIMIT', frame)
                                edges.add(key)
                                continue
                            edges.add(key)
                            path.append((len(stack),'child',c.identity))
                            stack.append(frame.page)
                            control = c
                            break
                        if c.kind == 'scroll' and key not in exhausted_scrolls:
                            if scroll_counts.get(key, 0) >= self.limits.scrolls:
                                block('SCROLL_LIMIT', frame)
                                exhausted_scrolls.add(key)
                                continue
                            scroll_counts[key] = scroll_counts.get(key, 0)+1
                            scroll_views.setdefault(key, set()).add(frame.fingerprint)
                            control = c
                            break
                    if control is None:
                        if not frame.parent or not stack:
                            block('NO_QUALIFIED_PARENT', frame)
                            break
                        control = frame.parent
                        destination = stack.pop()
                        children=[i for i,edge in enumerate(path) if edge[1]=='child']
                        path=path[:children[-1]] if children else []
                        if destination == 'home':
                            if report.events[active]['result'] != 'BLOCKED':
                                report.events[active]['result'] = 'EXHAUSTED'
                            active = None
                        pending = ('parent', destination, frame.fingerprint, None)
                if control.kind != 'parent':
                    key = active, frame.page, control.identity
                    pending = (control.kind, frame.page, frame.fingerprint, key)
                if not control.evidence or control not in (*frame.controls, frame.parent):
                    raise SafetyError('Navigation lacks current-frame ownership.')
                report.actions.append(dict(kind=control.kind, capture=frame.capture, identity=control.identity,
                                           box=asdict(control.box)))
                persist(asdict(report))
                report.return_home = 'NOT_STARTED'
                port.navigate(frame, control)
                transitions += 1
            else:
                report.blocked.append(dict(reason='OBSERVATION_LIMIT', event=active))
        except Exception as exc:  # noqa: BLE001 - caller retains target-owned cleanup
            report.blocked.append(dict(reason='ERROR', error=f'{type(exc).__name__}: {exc}', event=active))
        persist(asdict(report))
        return report

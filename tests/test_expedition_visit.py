from dataclasses import replace

from top_heroes_auto.automation.dynamic_events import Control, EventFrame
from top_heroes_auto.automation.expedition import finish_expedition
from top_heroes_auto.vision.models import BoundingBox


def frame(key, state, *, rewards=(), top=True, mission=False):
    controls=tuple(Control(r,BoundingBox(1,1,20,20),('free','card','current'),
                           'reward',cost='FREE',available=True) for r in rewards)
    if mission:
        controls+=(Control('relic-expedition-quick-send',BoundingBox(50,50,20,20),
                           ('free','current','send'),'mission',cost='FREE',available=True),)
    return EventFrame(key,(7,'disk','adb','boot'),'event:relic:personal-tasks',key,controls,
        coverage_known=True,mission_states=({'state':state},),mission_at_top=top)


class Port:
    def __init__(self, frames, *, uncertain=False):
        self.frames=iter(frames)
        self.calls=[]
        self.current=None
        self.uncertain=uncertain
    def observe(self):
        self.current=next(self.frames)
        return self.current
    def claim(self,f,c):
        self.calls.append(('collect',c.identity))
        return dict(journal='VERIFIED',result='SUCCESS')
    def scroll_missions(self,f,*,reverse):
        self.calls.append(('scroll-top' if reverse else 'scroll',f.capture))
    def send_mission(self,f,c):
        if c.identity=='relic-expedition-quick-send':
            self.calls.append(('open',f.capture))
            self.current=replace(f,page='event:relic-expedition:confirm',controls=(replace(
                c,identity='relic-expedition-confirm-send'),))
            return dict(result='NAVIGATION_SUCCESS')
        self.calls.append(('dispatch',f.capture))
        self.current=frame('running','WAITING')
        return dict(journal='RESERVED' if self.uncertain else 'VERIFIED',
                    result='ACTION_DISPATCHED_UNVERIFIED' if self.uncertain else 'SUCCESS')


def test_collect_prior_day_and_hidden_rewards_before_sending_in_same_visit():
    initial=frame('prior-day-completed','COMPLETED',rewards=('a','b'))
    bottom=frame('bottom','DISPATCHABLE',top=False,mission=True)
    port=Port([frame('one-left','COMPLETED',rewards=('b',)),
               frame('top-available','DISPATCHABLE',mission=True),
               frame('hidden','COMPLETED',rewards=('c',),top=False),
               bottom,bottom,frame('top-restored','DISPATCHABLE',mission=True),frame('running','WAITING')])
    result=finish_expedition(port,initial)
    assert result['result']=='WAITING' and not result['blocked']
    assert result['collection_scan']=='COMPLETE'
    kinds=[k for k,_ in port.calls]
    assert kinds==['collect','collect','scroll','collect','scroll','scroll-top','open','dispatch','scroll']
    assert len(result['rewards'])==3 and len(result['dispatches'])==1


def test_running_missions_never_dispatch_or_wait_for_completion():
    current=frame('running','WAITING')
    port=Port([current])
    result=finish_expedition(port,current)
    assert result['result']=='WAITING' and not result['dispatches']
    assert port.calls==[('scroll','running')]


def test_ambiguous_dispatch_does_not_retry():
    current=frame('available','DISPATCHABLE',mission=True)
    port=Port([current],uncertain=True)
    result=finish_expedition(port,current)
    assert len(result['dispatches'])==1
    assert result['blocked'][0]['reason']=='ACTION_DISPATCHED_UNVERIFIED'
    assert sum(k=='dispatch' for k,_ in port.calls)==1


def test_unqualified_completed_reward_prevents_send_but_is_not_unavailable():
    current=frame('completed','COMPLETED',mission=True)
    port=Port([current])
    result=finish_expedition(port,current)
    assert result['result']=='BLOCKED' and not result['dispatches']
    assert any(b['reason']=='COMPLETED_MISSION_NOT_COLLECTED' for b in result['blocked'])


def test_scroll_limit_does_not_claim_exhaustion_or_send():
    initial=frame('a','DISPATCHABLE',mission=True)
    port=Port([frame(str(n),'DISPATCHABLE',mission=True,top=False) for n in range(4)])
    result=finish_expedition(port,initial)
    assert result['collection_scan']!='COMPLETE' and not result['dispatches']
    assert result['blocked'][-1]['reason']=='MISSION_COLLECTION_SCROLL_LIMIT'

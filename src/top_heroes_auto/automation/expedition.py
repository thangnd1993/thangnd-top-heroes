"""One bounded expedition visit: collect every inspected page, then dispatch.

The adapter owns visual qualification, journals and transport. This policy never
uses coordinates, dates or a red badge as claim/dispatch permission.
"""
from dataclasses import asdict

from top_heroes_auto.ldplayer.identity import runtime_key


def finish_expedition(port, initial, *, persist=lambda report: None, scroll_limit=4):
    report = dict(result='BLOCKED', actions=[], rewards=[], dispatches=[], blocked=[],
                  inspected=[], collection_scan='NOT_STARTED', final_states=[])
    identity, page = runtime_key(initial.identity), initial.page
    current = initial
    attempted, seen = set(), set()
    scrolls = returns = final_scrolls = 0
    phase = 'COLLECT'
    def block(reason):
        report['blocked'].append(dict(reason=reason,capture=current.capture,page=current.page))
    try:
        for _ in range(32):
            persist(report)
            if runtime_key(current.identity)!=identity:
                block('MISSION_RUNTIME_CHANGED')
                break
            if current.popup:
                report['actions'].append(dict(kind='dismiss',capture=current.capture))
                port.dismiss(current)
                current=port.observe()
                continue
            if current.page!=page or not current.mission_states:
                block('MISSION_PAGE_LOST')
                break
            report['inspected'].append(dict(capture=current.capture,states=current.mission_states,
                                            viewport=current.fingerprint,phase=phase))
            rewards=[c for c in current.controls if c.kind=='reward']
            candidate=next((c for c in rewards if (c.identity,c.period) not in attempted),None)
            if candidate is not None:
                attempted.add((candidate.identity,candidate.period))
                result=port.claim(current,candidate)
                report['rewards'].append(result)
                report['actions'].append(dict(kind='reward',capture=current.capture,
                                              identity=candidate.identity,result=result))
                if result.get('journal')!='VERIFIED':
                    block(result.get('result','COLLECT_UNVERIFIED'))
                current=port.observe()
                continue
            if any(r['state']=='COMPLETED' for r in current.mission_states):
                block('COMPLETED_MISSION_NOT_COLLECTED')
                # Do not dispatch while an unresolved completed reward remains.
            if any(r['state']=='UNKNOWN' for r in current.mission_states):
                block('UNQUALIFIED_MISSION_STATE')
            if phase=='FINAL':
                if any(r['state']=='DISPATCHABLE' for r in current.mission_states):
                    block('REMAINING_MISSION_BATCH_OCCURRENCE_UNQUALIFIED')
                if current.fingerprint in seen:
                    if not report['blocked']:
                        report['result']='WAITING'
                    break
                seen.add(current.fingerprint)
                if final_scrolls>=scroll_limit:
                    block('MISSION_FINAL_INSPECTION_LIMIT')
                    break
                final_scrolls+=1
                port.scroll_missions(current,reverse=False)
                report['actions'].append(dict(kind='final-scroll',capture=current.capture))
                current=port.observe()
                continue
            if phase=='COLLECT':
                if current.fingerprint in seen:
                    report['collection_scan']='COMPLETE'
                    phase='RETURN'
                else:
                    seen.add(current.fingerprint)
                    if scrolls>=scroll_limit:
                        block('MISSION_COLLECTION_SCROLL_LIMIT')
                        break
                    scrolls+=1
                    port.scroll_missions(current,reverse=False)
                    report['actions'].append(dict(kind='scroll',capture=current.capture))
                    current=port.observe()
                    continue
            if phase=='RETURN':
                if not current.mission_at_top:
                    if returns>=scroll_limit:
                        block('MISSION_RETURN_TOP_LIMIT')
                        break
                    returns+=1
                    port.scroll_missions(current,reverse=True)
                    report['actions'].append(dict(kind='scroll-top',capture=current.capture))
                    current=port.observe()
                    continue
                if report['blocked']:
                    break
                phase='DISPATCH'
            if phase=='DISPATCH':
                send=[c for c in current.controls if c.kind=='mission']
                if not send:
                    if any(r['state']=='DISPATCHABLE' for r in current.mission_states):
                        block('DISPATCHABLE_MISSION_WITHOUT_QUALIFIED_SEND')
                    else:
                        report['result']='WAITING' if any(r['state']=='WAITING' for r in current.mission_states) else 'UNAVAILABLE'
                    break
                if len(send)!=1:
                    block('AMBIGUOUS_MISSION_SEND')
                    break
                opened=port.send_mission(current,send[0])
                report['actions'].append(dict(kind='mission-navigation',capture=current.capture,result=opened))
                if opened.get('result')!='NAVIGATION_SUCCESS':
                    block(opened.get('result','MISSION_MODAL_UNVERIFIED'))
                    break
                modal=port.current
                confirms=[c for c in modal.controls if c.identity=='relic-expedition-confirm-send']
                if runtime_key(modal.identity)!=identity or len(confirms)!=1:
                    block('MISSION_SELECTION_UNQUALIFIED')
                    break
                sent=port.send_mission(modal,confirms[0])
                report['dispatches'].append(sent)
                report['actions'].append(dict(kind='mission',capture=modal.capture,result=sent))
                current=port.current or port.observe()
                if sent.get('journal')!='VERIFIED':
                    block(sent.get('result','DISPATCH_UNVERIFIED'))
                    break
                # Inspect hidden rows again, without resending the same batch or
                # waiting for newly running missions to finish.
                phase='FINAL'
                seen.clear()
                continue
        else:
            block('MISSION_OBSERVATION_LIMIT')
    except Exception as exc:  # noqa: BLE001 - retain the blocker and continue only on fresh evidence
        block(f'MISSION_VISIT_FAILED: {type(exc).__name__}: {exc}')
    report['final_capture']=current.capture
    report['final_states']=current.mission_states
    report['scrolls']=scrolls
    report['return_scrolls']=returns
    report['final_scrolls']=final_scrolls
    report['final_frame']=asdict(current)
    persist(report)
    return report

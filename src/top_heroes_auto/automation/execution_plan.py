"""Terminal feature evidence is required before stopping a run-owned instance."""


def terminal_plan(plan, details, rewards):
    checks = {}
    for flow in plan:
        detail = details.get(flow.id, {})
        explicit = detail.get('result') in {'COMPLETE', 'BLOCKED', 'DISABLED', 'NOT_APPLICABLE', 'ALREADY_COMPLETED'} and not detail.get('omitted_rewards')
        explicit = explicit and all(rewards.get(r, {}).get('result') not in {None, '', 'NOT_STARTED', 'RUNNING', 'PENDING', 'QUEUED', 'DISCOVERED'} for r in flow.rewards)
        skipped = detail.get('result') in {'DISABLED', 'NOT_APPLICABLE', 'ALREADY_COMPLETED'}
        # Explicit pre-feature failures are genuine blockers. A returned feature
        # must supply its own terminal evidence; no placeholder can stand for scan.
        qualified = skipped or flow.terminal_evidence(detail)
        checks[flow.id] = dict(terminal=bool(explicit and qualified), evidence=detail)
    return dict(terminal=bool(plan) and all(c['terminal'] for c in checks.values()), flows=checks)


def event_terminal(detail):
    if detail.get('blocking_stage') == 'before_home':
        return bool(detail.get('recovery_report')) and detail.get('recovery') in {'UNKNOWN_SCREEN', 'LOADING_TIMEOUT', 'PROMO_BLOCKING', 'ACTION_FAILED', 'ADB_ERROR', 'SCREEN_NOT_READY', 'CANCELLED', 'LIMIT_REACHED'}
    exploration = detail.get('exploration', {})
    observations = exploration.get('observations', [])
    homes = [o for o in observations if o.get('page') == 'home' and o.get('event_scan_performed')]
    if (detail.get('recovery') not in {'SUCCESS', 'ALREADY_HOME'} or not homes
            or exploration.get('event_scan') != 'COMPLETE'):
        return False
    events = exploration.get('events', {})
    if (exploration.get('candidate_count') != len(events) or any(
            e.get('result') not in {'EXHAUSTED', 'BLOCKED'} or
            not {'nested_traversal', 'reward_results', 'blockers', 'discovery_capture'} <= e.keys()
            for e in events.values())):
        return False
    # Candidate keys must be accounted for even if traversal hit a bounded limit.
    discovered = {c['identity'] for o in homes for c in o.get('controls', []) if c.get('kind') == 'event'}
    return (discovered <= events.keys() and bool(exploration.get('result'))
            and (exploration.get('return_home') == 'SUCCESS' or bool(exploration.get('blocked'))))

"""One Monthly visit; upper quick batch never completes the lower daily reward."""
from top_heroes_auto.automation.fixed_reward_claims import process_reward
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.fixed_rewards import ADS_ROWS, MONTHLY_DAILY, MONTHLY_QUICK


def process_monthly(port, store, namespace, task_id, identity, report, persist):
    try:
        _process_monthly(port, store, namespace, task_id, identity, report, persist)
    finally:
        children = report.get('children', {})
        report['claim_dispatched'] = any(c.get('claim_dispatched') for c in children.values())
        report['claim_count'] = sum(bool(c.get('claim_dispatched')) for c in children.values())
        persist()  # Cancellation/transport failure cannot erase an earlier child dispatch.


def _process_monthly(port, store, namespace, task_id, identity, report, persist):
    report.update(result='BLOCKED', children={}, coverage=[], claim_dispatched=False)
    children = report['children']
    frame = port.observe_settled()
    if frame.page != 'shop-monthly' or not port.detector.selected_tab(frame, 'monthly'):
        raise SafetyError('Monthly selected page is not verified.')
    # Entry is navigation only. Its absence/old journal does not hide the main row.
    upper = children.setdefault(MONTHLY_QUICK, dict(result='BLOCKED', claim_dispatched=False))
    try:
        if frame.box('monthly-gift'):
            port.navigate(frame, 'monthly-gift', 'shop-ad-privileges')
            process_reward(port, store, namespace, task_id, MONTHLY_QUICK, identity, upper, persist)
            frame = port.observe_settled()
            if frame.page == 'shop-ad-privileges':
                rows = {row: 'RECEIVED' if frame.box(f'ads-done-{row}') else 'UNRESOLVED'
                        for row in ADS_ROWS}
                upper['row_coverage'] = rows
                upper['coverage_evidence'] = frame.evidence()
                upper['individual_ad_controls'] = 'FORBIDDEN_NO_INPUT'
                upper['scroll_result'] = ('NOT_REQUIRED_ALL_KNOWN_ROWS_PROVEN' if
                    all(value == 'RECEIVED' for value in rows.values()) else 'UNQUALIFIED_REMAINING_ROWS')
                if (upper['result'] in {'SUCCESS','NOT_AVAILABLE','ALREADY_VERIFIED'}
                        and 'UNRESOLVED' in rows.values()):
                    upper['action_result'] = upper['result']
                    upper['result'] = 'BLOCKED'  # Coverage never downgrades the durable claim.
                frame = port.navigate(frame, 'ads-close', 'shop-monthly')
        else:
            upper['error'] = 'Upper navigation control unqualified; lower row remains independent.'
    except Exception as exc:  # noqa: BLE001 - only a freshly safe page permits the sibling
        getattr(port, 'check_cancelled', lambda: None)()
        upper['error'] = str(exc)
        frame = port.observe_settled()
        if frame.page == 'shop-ad-privileges':
            frame = port.navigate(frame, 'ads-close', 'shop-monthly')
    report['coverage'].append(dict(page=frame.page, action=MONTHLY_QUICK, result=upper['result']))
    daily = children.setdefault(MONTHLY_DAILY, dict(result='BLOCKED', claim_dispatched=False))
    if frame.page == 'shop-monthly':
        process_reward(port, store, namespace, task_id, MONTHLY_DAILY, identity, daily, persist)
        final = port.observe_settled()
        state, _, _ = port.detector.availability(final, MONTHLY_DAILY)
        report['final_daily_state'] = state
        report['coverage'].append(dict(page=final.page, action=MONTHLY_DAILY, result=state,
                                       evidence=final.evidence()))
        if state == 'AVAILABLE':
            daily['result'] = 'PENDING_LOCKED' if daily.get('claim_id') else 'BLOCKED'
    else:
        daily['error'] = 'Safe Monthly parent could not be recovered; no sibling input.'
    # Coverage remains partial when any independent panel is unknown or locked.
    report['result'] = 'SUCCESS' if all(c['result'] in {'SUCCESS','NOT_AVAILABLE','ALREADY_VERIFIED'}
                                      for c in children.values()) else 'BLOCKED'
    persist()

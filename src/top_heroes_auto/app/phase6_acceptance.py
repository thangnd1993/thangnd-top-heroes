"""Explicit seven-reward Phase 6 acceptance; one immutable live fleet snapshot."""
import json
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.bxh_shop_acceptance import (
    candidates,
    choose_random,
    inventory,
    persistent_identity,
    progress,
    run_account,
    write,
)
from top_heroes_auto.app.vip_fleet import run_vip_account
from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.fixed_rewards import SHOP_REWARDS

VIP = ('vip-upper-gift', 'vip-daily')
FIXED = ('ranking-chest', *SHOP_REWARDS)
REQUIRED = (*VIP, *FIXED)
COMPLETE = frozenset({'SUCCESS', 'NOT_AVAILABLE', 'ALREADY_VERIFIED', 'SUCCESS_WITH_RECOVERY_WARNING'})


def vip_outcomes(row):
    upper = row.get('upper_gift', {})
    return {
        'vip-upper-gift': dict(result=upper.get('result', 'BLOCKED'),
            availability=upper.get('availability'), journal=upper.get('journal_state', 'NONE'),
            claim_id=upper.get('claim_id', upper.get('previous_claim_id')),
            claim_dispatched=upper.get('claim_dispatched', False), error=upper.get('error', row.get('error'))),
        'vip-daily': dict(result=row.get('daily_result', row.get('final_result', 'BLOCKED')),
            availability=row.get('free_reward_state'), journal=row.get('journal_state', 'NONE'),
            claim_id=row.get('claim_id'), claim_dispatched=row.get('claim_dispatched', False),
            error=row.get('error')),
    }


def run(manager, data, *, random_test=False, resume_report=None,
        identity_reader=persistent_identity, vip_runner=run_vip_account, fixed_runner=run_account):
    before = inventory(manager)
    previous = json.loads(Path(resume_report).read_text(encoding='utf-8')) if resume_report else None
    if previous and (previous.get('required_rewards') != list(REQUIRED) or previous.get('max_concurrency') != 1):
        raise SafetyError('Resume requires the original seven-reward Phase 6 snapshot.')
    eligible = candidates(before)
    chosen = None
    if previous:
        targets = previous['targets']
    elif random_test:
        chosen, eligible = choose_random(before)
        targets = [chosen]
    else:
        targets = eligible
    if len({t['index'] for t in targets}) != len(targets):
        raise SafetyError('Ambiguous acceptance snapshot.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%fZ')
    folder = data/'diagnostics/tasks/phase6-final'/stamp
    folder.mkdir(parents=True, exist_ok=False)
    report = dict(mode='resume' if previous else 'random-test' if random_test else 'fleet',
        required_rewards=list(REQUIRED), max_concurrency=1, before_instances=before,
        targets=targets, eligible_candidates=eligible, random_target=chosen,
        random_method='secrets.choice' if random_test else None,
        resumed_from=str(resume_report) if previous else None, accounts=[])
    path = folder/'fleet-report.json'
    # Bind ALL target identities before any account mutation.
    for target in targets:
        try:
            live = [r for r in before if r['index'] == target['index']]
            if len(live) != 1 or live[0]['name'] != target['name'] or live[0]['protected']:
                raise SafetyError('Original target is missing, changed or Protected.')
            identity = identity_reader(manager, target['index'])
            if previous and target.get('persistent_identity') != identity:
                raise SafetyError('Original persistent identity changed.')
            target['persistent_identity'] = identity
            target.pop('identity_error', None)
        except (SafetyError, OSError, ValueError) as exc:
            target['identity_error'] = str(exc)
    write(path, report)
    old = {r['index']: r for r in previous['accounts']} if previous else {}
    for target in targets:
        index, name = target['index'], target['name']
        prior = old.get(index, {})
        row = dict(index=index, name=name, rewards=dict(prior.get('rewards', {})),
                   cleanup='NOT_REQUIRED', selection_restored=True, result='PARTIAL', flows={})
        if prior:
            row['previous_report'] = str(resume_report)
            row['previous_flows'] = prior.get('flows', {})
            row['shop_traversal'] = prior.get('shop_traversal', {})
        account = folder/str(index)
        account.mkdir()
        progress(f'PHASE6 START #{index} / {name}')
        def persist():
            write(account/'account-report.json', row)
        try:
            if target.get('identity_error'):
                raise SafetyError(target['identity_error'])
            missing = [r for r in REQUIRED if row['rewards'].get(r, {}).get('result') not in COMPLETE]
            if any(r in missing for r in VIP):
                vip_folder = account/'vip'
                vip_folder.mkdir()
                if identity_reader(manager, index) != target['persistent_identity']:
                    raise SafetyError('Target identity changed before VIP.')
                result = vip_runner(manager, data, index, name, vip_folder,
                    include_upper_gift=VIP[0] in missing, include_daily=VIP[1] in missing)
                row['flows']['vip'] = result
                outcomes = vip_outcomes(result)
                row['rewards'].update({r: outcomes[r] for r in VIP if r in missing})
                persist()
            needed_fixed = tuple(r for r in FIXED if r in missing)
            recovery_only = not needed_fixed and not missing and prior and not prior.get('recovery_ok')
            if needed_fixed or recovery_only:
                if identity_reader(manager, index) != target['persistent_identity']:
                    raise SafetyError('Target identity changed before BXH/Shop.')
                result = fixed_runner(manager, data, target, account/'fixed', rewards=needed_fixed)
                row['flows']['fixed'] = result
                row['rewards'].update(result.get('rewards', {}))
                if needed_fixed:
                    row['shop_traversal'] = result.get('shop_traversal', {})
                persist()
        except Exception as exc:  # noqa: BLE001 - finish unaffected snapshot members
            row['error'] = f'{type(exc).__name__}: {exc}'
        for reward in REQUIRED:
            row['rewards'].setdefault(reward, dict(result='BLOCKED', claim_dispatched=False,
                journal='NONE', error=row.get('error', 'Required route not completed.')))
        flows = list(row['flows'].values())
        row['cleanup'] = 'SUCCESS' if all(f.get('cleanup') in {'SUCCESS', 'NOT_REQUIRED'} for f in flows) else 'FAILED'
        row['selection_restored'] = all(f.get('selection_restored') for f in flows)
        row['recovery_ok'] = all(f.get('return_home') == 'SUCCESS' for f in flows)
        if not flows and prior:
            row.update(cleanup=prior.get('cleanup', 'UNKNOWN'),
                selection_restored=prior.get('selection_restored', False), recovery_ok=prior.get('recovery_ok', False))
        row['new_claims'] = sum(bool(v.get('claim_dispatched')) for f in row['flows'].values()
            for v in ([f, f.get('upper_gift', {})] if 'final_result' in f else f.get('rewards', {}).values()))
        row['result'] = 'COMPLETE' if (not row.get('error') and row['recovery_ok']
            and row['cleanup'] == 'SUCCESS' and row['selection_restored']
            and all(r['result'] in COMPLETE for r in row['rewards'].values())) else 'PARTIAL'
        persist()
        report['accounts'].append(row)
        write(path, report)
        progress(f"PHASE6 END #{index}: {row['result']}")
    report['after_instances'] = inventory(manager)
    report['all_selection_states_restored'] = {r['index']: r['selected'] for r in before} == {
        r['index']: r['selected'] for r in report['after_instances']}
    report['protected_state_unchanged'] = all(r in report['after_instances'] for r in before if r['protected'])
    report['instance_names_unchanged'] = {r['index']: r['name'] for r in before} == {
        r['index']: r['name'] for r in report['after_instances']}
    report['result'] = 'PASS' if (targets and len(report['accounts']) == len(targets)
        and all(r['result'] == 'COMPLETE' for r in report['accounts'])
        and report['all_selection_states_restored'] and report['protected_state_unchanged']
        and report['instance_names_unchanged']) else 'PARTIAL'
    write(path, report)
    progress(f'PHASE6 REPORT: {path}')
    return report

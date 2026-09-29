"""Explicit acceptance exceptions preserve uncertain journals; never reconcile/input."""
import hashlib
import json

from top_heroes_auto.automation.guard import SafetyError


def preserved_claims(manager, previous, targets, claim_ids):
    if not claim_ids:
        return {}
    if not previous or any(type(cid) is not int or cid <= 0 for cid in claim_ids):
        raise SafetyError('Preserving a POSSIBLE claim requires an explicit resumed claim ID.')
    if len(set(claim_ids)) != len(claim_ids):
        raise SafetyError('Duplicate preserved claim ID.')
    found = {}
    accounts = {a['index']: a for a in previous['accounts']}
    for target in targets:
        idx = target['index']
        for raw in manager.store.reward_claims(manager.namespace, idx):
            row = dict(raw)
            cid = row['id']
            if cid not in claim_ids:
                continue
            reward = row['reward_id']
            prior = accounts.get(idx, {}).get('rewards', {}).get(reward, {})
            prior_ids = {prior.get('claim_id')} | {a.get('claim_id') for a in prior.get('actions', [])}
            before = json.loads(row['before_evidence'])
            if (cid not in prior_ids or row['status'] != 'RESERVED'
                    or row['dispatch_state'] != 'POSSIBLE'
                    or row['namespace'] != manager.namespace or row['instance_index'] != idx
                    or row['instance_name'] not in {target['name'], *target.get('historical_names', [])}
                    or not target.get('persistent_identity') or target.get('identity_error')
                    or before.get('persistent_identity') != target['persistent_identity']
                    or manager.store.metadata(manager.namespace, idx).protected):
                raise SafetyError('Preserved POSSIBLE claim does not match the original target/evidence.')
            digest = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
            found[cid] = dict(index=idx, reward=reward, claim_id=cid, journal_sha256=digest,
                result='PRESERVED_POSSIBLE', journal='RESERVED', dispatch_state='POSSIBLE',
                claim_dispatched=False, authorized_exception=True,
                reason='Explicitly accepted historical uncertainty; reward remains locked.')
    if set(found) != set(claim_ids):
        raise SafetyError('Preserved claim ID not found in original target journals.')
    return found

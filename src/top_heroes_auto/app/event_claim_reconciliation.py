"""Read saved claim evidence to preserve locks across caption raster changes."""
import json
from pathlib import Path

import cv2

from top_heroes_auto.automation.guard import SafetyError
from top_heroes_auto.vision.dynamic_events import task_label_glyph
from top_heroes_auto.vision.models import BoundingBox


def bind_saved_rewards(image, rows, claims, *, persistent_identity, index):
    """Alias only unique, strict caption agreement; uncertain aliases block input.

    This never opens eligibility or changes a journal. Coordinates in saved
    evidence extract reference glyphs only, never provide a runtime tap point.
    """
    rows = [dict(row) for row in rows]
    for claim in claims:
        if not claim['reward_id'].startswith('event:'):
            continue
        proof = json.loads(claim['before_evidence'])
        if not proof.get('page', '').endswith(':personal-tasks'):
            raise SafetyError('Unsupported saved Event claim identity; no new claim.')
        if proof.get('persistent_identity') != persistent_identity or proof['identity'][0] != index:
            raise SafetyError('Saved Event claim target identity changed.')
        source = Path(proof['capture'])
        try:
            saved = json.loads(source.with_suffix('.event.json').read_text(encoding='utf-8'))
            old = [r for r in saved['reward_rows'] if r['identity'] == proof['reward']]
            reference = cv2.imread(str(source))
            if reference is None or len(old) != 1:
                raise ValueError('Missing unique saved reward')
            if reference.shape[1] > reference.shape[0]:
                reference = cv2.rotate(reference, cv2.ROTATE_90_COUNTERCLOCKWISE)
            known = [task_label_glyph(reference, BoundingBox(**r['row']))
                     for r in saved['reward_rows']]
            glyph = task_label_glyph(reference, BoundingBox(**old[0]['row']))
            if glyph is None:
                raise ValueError('Missing saved caption')
        except (OSError, ValueError, KeyError) as exc:
            raise SafetyError('Saved claim evidence unavailable; no new claim.') from exc
        scored = []
        for row in rows:
            current = task_label_glyph(image, row['row'])
            if current is None:
                raise SafetyError('Current reward caption unavailable.')
            score = float(cv2.matchTemplate(current, glyph, cv2.TM_CCOEFF_NORMED)[0,0])
            scored.append((score, row))
            if score < .75 and claim['dispatch_state'] == 'POSSIBLE':
                # A new raster hash must not silently become a new eligible
                # reward while an action is unresolved. Previously seen,
                # visually distinct siblings retain their own eligibility.
                sibling_scores = [float(cv2.matchTemplate(current, g, cv2.TM_CCOEFF_NORMED)[0,0])
                                  for g in known if g is not None]
                if sum(v >= .98 for v in sibling_scores) != 1:
                    row['state'] = 'UNKNOWN'
                    row['evidence'] = (*row['evidence'], 'unresolved-saved-reward-identity')
        matches = [r for score,r in scored if score >= .98]
        if len(matches) > 1:
            for score, row in scored:
                if score >= .75:
                    if row['state'] == 'AVAILABLE':
                        row['state'] = 'UNKNOWN'
                    row['evidence'] = (*row['evidence'], 'ambiguous-saved-reward-identity')
            continue
        for score, row in scored:
            if .75 <= score < .98:
                if row['state'] == 'AVAILABLE':
                    row['state'] = 'UNKNOWN'
                row['evidence'] = (*row['evidence'], 'ambiguous-saved-reward-identity')
        if matches:
            matches[0]['identity'] = proof['reward']
            matches[0]['evidence'] = (*matches[0]['evidence'], 'unique-saved-caption-agreement')
    return tuple(rows)


def reconcile_possible(store, namespace, index, persistent_identity, observations, *, claim_ids=None):
    """Verify existing POSSIBLE only from two fresh same-card unavailable proofs.

    A new boot is permitted only after the live session independently verifies
    target identity. This function sends no input and never creates a reservation.
    """
    verified = []
    if len(observations) != 2:
        return verified
    a,b = observations
    if (not a.get('capture') or not b.get('capture') or a['capture'] == b['capture']
            or a.get('identity') != b.get('identity') or a['identity'][0] != index):
        return verified
    for row in store.reward_claims(namespace, index):
        if not row['reward_id'].startswith('event:'):
            continue
        if claim_ids is not None and row['id'] not in claim_ids:
            continue
        if row['status'] != 'RESERVED' or row['dispatch_state'] != 'POSSIBLE':
            continue
        proof = json.loads(row['before_evidence'])
        if proof.get('persistent_identity') != persistent_identity:
            raise SafetyError('Reconciliation persistent identity changed.')
        if any(o.get('state') != 'NOT_AVAILABLE' or o.get('reward') != proof['reward']
               or o.get('page') != proof['page'] or o.get('identity', [])[:2] != proof['identity'][:2]
               or o['capture'] == proof['capture']
               or not {'unique-saved-caption-agreement', 'qualified-control-color',
                       'selected-task-context', 'complete-reward-card'}.issubset(o.get('independent_evidence', []))
               for o in observations):
            continue
        store.verify_reward_claim(row['id'], row['task_run_id'], json.dumps(observations))
        verified.append(row['id'])
    return verified

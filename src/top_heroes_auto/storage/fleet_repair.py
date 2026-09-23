"""One-shot, evidence-checked archival of the 2026-09-23 outer fleet locks.

No device access. Not an automatic startup migration or general lock reset.
The caller must back up the SQLite database before applying this operation.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

TRIAL = ((1, 17, 18, 2, '5-Emmmmm'), (2, 19, 20, 4, '3-Chíp'), (3, 21, 22, 5, '4-Em Pé'))


def release_trial_locks(database: Path, fleet_path: Path, *, apply: bool = False) -> list[dict]:
    evidence = {}

    def read(path):
        path = Path(path)
        raw = path.read_bytes()
        evidence[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    fleet = read(fleet_path)
    if fleet.get('commit') != 'af5464c' or fleet.get('max_concurrency') != 1 or not fleet.get('finished_at'):
        raise ValueError('Unexpected or unfinished fleet trial.')
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    results = []
    try:
        db.execute('BEGIN IMMEDIATE')
        for claim_id, outer_id, inner_id, index, name in TRIAL:
            row = db.execute('SELECT * FROM reward_claims WHERE id=?', (claim_id,)).fetchone()
            if row is None:
                audit = db.execute("SELECT 1 FROM sqlite_master WHERE name='reward_release_audit'").fetchone()
                archived = db.execute('SELECT original_row FROM reward_release_audit WHERE claim_id=?',
                                      (claim_id,)).fetchone() if audit else None
                if not archived or json.loads(archived[0]).get('task_run_id') != outer_id:
                    raise ValueError('Missing reservation without matching archive.')
                results.append({'claim_id': claim_id, 'status': 'ALREADY_RELEASED'})
                continue
            row = dict(row)
            if (row['task_run_id'], row['instance_index'], row['instance_name'], row['status'],
                row['reward_id'], row['cycle_key']) != (
                    outer_id, index, name, 'RESERVED', 'idle-reward', 'fleet-current-implementation-once'):
                raise ValueError('Reservation identity/status mismatch.')
            if row.get('dispatch_state', 'UNKNOWN') != 'UNKNOWN' or row['after_evidence'] is not None:
                raise ValueError('Reservation has new dispatch/receipt evidence; manual review required.')
            outer = db.execute('SELECT * FROM task_runs WHERE id=?', (outer_id,)).fetchone()
            inner = db.execute('SELECT * FROM task_runs WHERE id=?', (inner_id,)).fetchone()
            for run, task in ((outer, 'fleet-idle-once'), (inner, 'idle-reward')):
                if not run or (run['namespace'], run['instance_index'], run['instance_name'], run['task']) != (
                    row['namespace'], index, name, task) or not run['finished_at']:
                    raise ValueError('Task identity/completion mismatch.')
            accounts = [a for a in fleet['accounts'] if a['index'] == index]
            if len(accounts) != 1:
                raise ValueError('Ambiguous fleet account.')
            account = accounts[0]
            if (account.get('journal_id'), account.get('task_run_id'), account.get('account'),
                account.get('claims_performed')) != (claim_id, inner_id, name, 0):
                raise ValueError('Fleet/production linkage mismatch.')
            if Path(inner['report_path']) != Path(account['task_report']) or Path(outer['report_path']) != fleet_path:
                raise ValueError('Task report path mismatch.')
            report = read(inner['report_path'])
            if report.get('instance') != {'index': index, 'name': name} or report.get('task_run_id') != inner_id:
                raise ValueError('Production report identity mismatch.')
            if report.get('claim_dispatched') is not False or report.get('actions') != []:
                raise ValueError('No-dispatch proof missing.')
            steps = report.get('steps')
            recovery = read(report['recovery_report'])
            if recovery.get('instance') != report['instance'] or any(
                action not in {'launch_game', 'wait'} for action in recovery.get('actions', [])
            ):
                raise ValueError('Recovery contains unknown input or identity.')
            if index == 2:
                if (report.get('result') != 'UNKNOWN_SCREEN' or not isinstance(steps, list) or len(steps) != 1
                        or steps[0].get('state') != 'UNKNOWN' or steps[0].get('action') is not None
                        or report.get('error') != 'GAME_HOME portal anchor was not verified.'):
                    raise ValueError('Incomplete pre-entry exit proof.')
            elif (report.get('result') != 'ACTION_FAILED' or steps != []
                  or recovery.get('result') != 'LOADING_TIMEOUT'
                  or not report.get('error', '').startswith('GAME_HOME precondition failed: LOADING_TIMEOUT:')):
                raise ValueError('Incomplete pre-task timeout proof.')
            if inner['status'] != report['result'] or outer['status'] != 'BLOCKED':
                raise ValueError('Database/report result mismatch.')
            for screenshot in report.get('screenshots', []) + recovery.get('screenshots', []):
                path = Path(screenshot)
                evidence[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            results.append({'claim_id': claim_id, 'status': 'RELEASED' if apply else 'PROVEN_NOT_DISPATCHED',
                            'original_row': row})
        if apply:
            db.execute('''CREATE TABLE IF NOT EXISTS reward_release_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL UNIQUE,
                released_at TEXT NOT NULL, original_row TEXT NOT NULL, evidence TEXT NOT NULL)''')
            for result in results:
                if result['status'] != 'RELEASED':
                    continue
                db.execute('INSERT INTO reward_release_audit(claim_id,released_at,original_row,evidence) VALUES (?,?,?,?)',
                           (result['claim_id'], datetime.now(timezone.utc).isoformat(),
                            json.dumps(result['original_row']), json.dumps({'reason': 'audited pre-claim exit', 'sha256': evidence})))
                db.execute('DELETE FROM reward_claims WHERE id=?', (result['claim_id'],))
            db.commit()
        else:
            db.rollback()
        return results
    finally:
        db.close()

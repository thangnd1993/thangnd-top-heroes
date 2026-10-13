"""Bind a legacy VIP journal to its original fleet disk proof; no gameplay input."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from top_heroes_auto.app.automation_ownership import mutation_ownership
from top_heroes_auto.app.bxh_shop_acceptance import persistent_identity


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def qualify(store, claim_id):
    with store.connect() as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM reward_claims WHERE id=?", (claim_id,)).fetchone()
        task = (
            db.execute("SELECT * FROM task_runs WHERE id=?", (row["task_run_id"],)).fetchone()
            if row
            else None
        )
    if not row or row["reward_id"] not in {"vip-upper-gift", "vip-daily"} or not task:
        raise ValueError("No supported original VIP journal/task.")
    row, task = dict(row), dict(task)
    if (task["namespace"], task["instance_index"], task["task"]) != (
        row["namespace"],
        row["instance_index"],
        "vip-reward",
    ):
        raise ValueError("Original task association is not proven.")
    index = row["instance_index"]
    path = Path(task["report_path"]).resolve()
    roots = store.path.parent.resolve() / "diagnostics" / "tasks"
    root = path.parents[3]
    if (
        root not in {roots / "automation", roots / "phase6-final"}
        or path.name != "account-report.json"
        or path.parent.name != "vip"
        or path.parents[1].name != str(index)
        or path.parents[3] != root
    ):
        raise ValueError("Missing original identity-bearing automation report.")
    fleet_path = path.parents[2] / "fleet-report.json"
    contents = {p: p.read_bytes() for p in (path, fleet_path)}
    report = json.loads(contents[path])
    fleet = json.loads(contents[fleet_path])
    legacy_phase6 = (
        root.name == "phase6-final"
        and "schema" not in fleet
        and fleet.get("mode") in {"random-test", "fleet"}
        and fleet.get("max_concurrency") == 1
        and set(fleet.get("required_rewards", []))
        == {
            "vip-upper-gift",
            "vip-daily",
            "ranking-chest",
            "shop-daily-gift",
            "shop-weekly-card-gift",
            "shop-permanent-privilege-gift",
            "shop-monthly-privilege-gift",
        }
    )
    if not (root.name == "automation" and fleet.get("schema") == "instance-first-v1") and not legacy_phase6:
        raise ValueError("Unsupported original fleet proof.")
    targets = [t for t in fleet["targets"] if t["index"] == index]
    accounts = [a for a in fleet["accounts"] if a["index"] == index]
    if len(targets) != 1 or len(accounts) != 1 or targets[0].get("protected") is not False:
        raise ValueError("Ambiguous original target.")
    stable_id = targets[0].get("persistent_identity")
    if not isinstance(stable_id, str) or not stable_id:
        raise ValueError("Original backing-file identity is missing.")
    flow = accounts[0]["flows"].get("vip", {})
    if (
        report.get("index") != index
        or report.get("task_run_id") != row["task_run_id"]
        or any(flow.get(k) != v for k, v in report.items())
    ):
        raise ValueError("Fleet does not contain this exact original task report.")
    action = report.get("upper_gift", {}) if row["reward_id"] == "vip-upper-gift" else report
    before = action.get("before" if row["reward_id"] == "vip-upper-gift" else "before_evidence")
    if (
        action.get("claim_id") != claim_id
        or before != json.loads(row["before_evidence"])
        or not isinstance(before, dict)
        or before.get("index") != index
        or not before.get("adb_target")
        or not before.get("boot_id")
    ):
        raise ValueError("Original claim/capture association is not proven.")
    # Names are display-only; the source report links claim -> task -> index/disk.
    return dict(
        claim_id=claim_id,
        index=index,
        namespace=row["namespace"],
        stable_id=stable_id,
        method="original_fleet_target_and_exact_vip_task",
        original_row_digest=digest(row),
        original_task_digest=digest(task),
        sources=[
            dict(path=str(p), sha256=hashlib.sha256(contents[p]).hexdigest()) for p in (path, fleet_path)
        ],
    )


def reconcile(manager, claim_id):
    with mutation_ownership(manager):
        store = manager.store
        proof = qualify(store, claim_id)
        if proof["namespace"] != manager.namespace:
            raise ValueError("Installation namespace differs.")
        index, stable_id = proof["index"], proof["stable_id"]
        if manager.store.metadata(manager.namespace, index).protected:
            raise ValueError("Protected journal excluded.")
        if persistent_identity(manager, index) != stable_id:
            raise ValueError("Original backing-file identity differs from live target.")
        for source in proof["sources"]:
            if hashlib.sha256(Path(source["path"]).read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("Original proof changed during reconciliation.")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM reward_claims WHERE id=?", (claim_id,)).fetchone()
            task = (
                db.execute("SELECT * FROM task_runs WHERE id=?", (row["task_run_id"],)).fetchone()
                if row
                else None
            )
            if (
                not row
                or not task
                or digest(dict(row)) != proof["original_row_digest"]
                or digest(dict(task)) != proof["original_task_digest"]
            ):
                raise ValueError("Original journal/task changed during reconciliation.")
            identity = db.execute(
                "SELECT stable_id,observed_id,state FROM instance_identities WHERE namespace=? AND idx=?",
                (manager.namespace, index),
            ).fetchone()
            flags = db.execute(
                "SELECT protected,present FROM instances WHERE namespace=? AND idx=?",
                (manager.namespace, index),
            ).fetchone()
            old = db.execute(
                "SELECT stable_id,state FROM journal_identities WHERE claim_id=?", (claim_id,)
            ).fetchone()
            if (
                not identity
                or tuple(identity) != (stable_id, stable_id, "VERIFIED")
                or not flags
                or tuple(flags) != (0, 1)
            ):
                raise ValueError("Live protection/identity changed; no reconciliation.")
            if old and tuple(old) == (stable_id, "VERIFIED"):
                return dict(
                    claim_id=claim_id,
                    result="ALREADY_BOUND",
                    claim_status=row["status"],
                    claim_redispatched=False,
                )
            if old and tuple(old) != ("", "AMBIGUOUS"):
                raise ValueError("Conflicting existing identity binding stays locked.")
            proof["reconciled_at"] = datetime.now(timezone.utc).isoformat()
            proof["previous_binding"] = tuple(old) if old else None
            db.execute(
                "INSERT OR REPLACE INTO journal_identities VALUES (?,?,?)", (claim_id, stable_id, "VERIFIED")
            )
            db.execute(
                "INSERT INTO settings VALUES (?,?)",
                (f"journal_identity_reconciliation:{claim_id}", json.dumps(proof, ensure_ascii=False)),
            )
        return dict(
            claim_id=claim_id, result="IDENTITY_BOUND", claim_status=row["status"], claim_redispatched=False
        )

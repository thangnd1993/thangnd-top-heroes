import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from top_heroes_auto.ldplayer.client import Instance


@dataclass(frozen=True)
class Metadata:
    selected: bool = False
    protected: bool = False


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


class AccountStatus(StrEnum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Open short-lived connections so UI and worker threads never share a connection."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS instances (
                    namespace TEXT NOT NULL, idx INTEGER NOT NULL, name TEXT NOT NULL,
                    selected INTEGER NOT NULL DEFAULT 0, protected INTEGER NOT NULL DEFAULT 0,
                    present INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(namespace, idx), CHECK (NOT (selected AND protected)));
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, namespace TEXT NOT NULL,
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    status TEXT NOT NULL, max_concurrency INTEGER NOT NULL,
                    requested_account_count INTEGER NOT NULL,
                    completed_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER NOT NULL DEFAULT 0,
                    cancelled_count INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS run_accounts (
                    run_id INTEGER NOT NULL, instance_index INTEGER NOT NULL,
                    instance_name TEXT NOT NULL, status TEXT NOT NULL,
                    started_at TEXT, finished_at TEXT, error TEXT NOT NULL DEFAULT '',
                    retry_count INTEGER NOT NULL DEFAULT 0, started_by_run INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(run_id, instance_index),
                    FOREIGN KEY(run_id) REFERENCES runs(id));
                CREATE TABLE IF NOT EXISTS task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL, task TEXT NOT NULL,
                    instance_index INTEGER NOT NULL, instance_name TEXT NOT NULL,
                    status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                    error TEXT NOT NULL DEFAULT '', report_path TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS reward_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL, instance_index INTEGER NOT NULL,
                    instance_name TEXT NOT NULL, reward_id TEXT NOT NULL,
                    cycle_key TEXT NOT NULL, task_run_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('RESERVED','VERIFIED')),
                    reserved_at TEXT NOT NULL, verified_at TEXT,
                    before_evidence TEXT NOT NULL, after_evidence TEXT,
                    UNIQUE(namespace,instance_index,reward_id,cycle_key),
                    FOREIGN KEY(task_run_id) REFERENCES task_runs(id));
            """)
            columns = {row[1] for row in db.execute('PRAGMA table_info(reward_claims)')}
            if 'dispatch_state' not in columns:
                db.execute("ALTER TABLE reward_claims ADD COLUMN dispatch_state TEXT NOT NULL DEFAULT 'UNKNOWN'")
            db.execute('''CREATE TABLE IF NOT EXISTS reward_release_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL UNIQUE,
                released_at TEXT NOT NULL, original_row TEXT NOT NULL, evidence TEXT NOT NULL)''')
            db.execute(
                "UPDATE runs SET status=?, finished_at=COALESCE(finished_at, ?) WHERE status IN (?, ?)",
                (RunStatus.INTERRUPTED, _stamp(), RunStatus.QUEUED, RunStatus.RUNNING),
            )
            db.execute(
                """UPDATE task_runs SET status='INTERRUPTED',finished_at=COALESCE(finished_at,?)
                   WHERE status='RUNNING'""",
                (_stamp(),),
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key: str, default: str = "") -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set(self, key: str, value: str):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))

    def merge(self, namespace: str, instances: tuple[Instance, ...]):
        with self.connect() as db:
            old = {
                row[0]: row[1:]
                for row in db.execute(
                    "SELECT idx,name,present FROM instances WHERE namespace=?", (namespace,)
                )
            }
            db.execute("UPDATE instances SET present=0 WHERE namespace=?", (namespace,))
            for instance in instances:
                previous = old.get(instance.index)
                if previous is None:
                    db.execute(
                        "INSERT INTO instances VALUES (?,?,?,0,0,1)",
                        (namespace, instance.index, instance.name),
                    )
                else:
                    # Rename/reappearance invalidates opt-in, but NEVER clears protection.
                    changed = previous != (instance.name, 1)
                    db.execute(
                        """UPDATE instances SET name=?,present=1,
                               selected=CASE WHEN ? THEN 0 ELSE selected END
                               WHERE namespace=? AND idx=?""",
                        (instance.name, changed, namespace, instance.index),
                    )
            db.execute("UPDATE instances SET selected=0 WHERE namespace=? AND present=0", (namespace,))

    def metadata(self, namespace: str, index: int) -> Metadata:
        with self.connect() as db:
            row = db.execute(
                "SELECT selected,protected FROM instances WHERE namespace=? AND idx=? AND present=1",
                (namespace, index),
            ).fetchone()
        return Metadata(bool(row[0]), bool(row[1])) if row else Metadata()

    def select(self, namespace: str, index: int, selected: bool):
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE instances SET selected=?
                WHERE namespace=? AND idx=? AND present=1 AND (protected=0 OR ?=0)""",
                (selected, namespace, index, selected),
            )
            if cursor.rowcount != 1:
                raise ValueError("Giả lập được bảo vệ hoặc không còn tồn tại.")

    def protect(self, namespace: str, index: int, protected: bool):
        with self.connect() as db:
            db.execute(
                """UPDATE instances SET protected=?, selected=CASE WHEN ? THEN 0 ELSE selected END
                       WHERE namespace=? AND idx=? AND present=1""",
                (protected, protected, namespace, index),
            )

    def create_run(self, namespace: str, members: tuple[tuple[int, str], ...], max_concurrency: int) -> int:
        if max_concurrency not in (1, 2, 3, 4):
            raise ValueError("Concurrency phải từ 1 đến 4.")
        if not members:
            raise ValueError("Không có giả lập hợp lệ trong hàng đợi.")
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO runs(namespace,created_at,status,max_concurrency,requested_account_count)
                   VALUES (?,?,?,?,?)""",
                (namespace, _stamp(), RunStatus.QUEUED, max_concurrency, len(members)),
            )
            run_id = cursor.lastrowid
            db.executemany(
                """INSERT INTO run_accounts(run_id,instance_index,instance_name,status)
                   VALUES (?,?,?,?)""",
                [(run_id, index, name, AccountStatus.QUEUED) for index, name in members],
            )
        return int(run_id)

    def set_run_status(self, run_id: int, status: RunStatus):
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET status=?, started_at=COALESCE(started_at,?), finished_at=? WHERE id=?",
                (status, _stamp(), _stamp() if status not in (RunStatus.QUEUED, RunStatus.RUNNING) else None, run_id),
            )

    def set_account_status(
        self, run_id: int, index: int, status: AccountStatus, error: str = "", started_by_run: bool | None = None
    ):
        with self.connect() as db:
            final = status in (AccountStatus.SUCCESS, AccountStatus.FAILED, AccountStatus.CANCELLED, AccountStatus.SKIPPED)
            fields = "status=?, error=?, started_at=COALESCE(started_at,?), finished_at=?"
            values = [status, error[:1000], _stamp(), _stamp() if final else None]
            if started_by_run is not None:
                fields += ", started_by_run=?"
                values.append(started_by_run)
            values.extend((run_id, index))
            db.execute(f"UPDATE run_accounts SET {fields} WHERE run_id=? AND instance_index=?", values)

    def finish_run(self, run_id: int, status: RunStatus):
        with self.connect() as db:
            counts = dict(
                db.execute(
                    "SELECT status,COUNT(*) FROM run_accounts WHERE run_id=? GROUP BY status", (run_id,)
                ).fetchall()
            )
            db.execute(
                """UPDATE runs SET status=?,finished_at=?,completed_count=?,failed_count=?,cancelled_count=? WHERE id=?""",
                (
                    status,
                    _stamp(),
                    counts.get(AccountStatus.SUCCESS, 0),
                    counts.get(AccountStatus.FAILED, 0),
                    counts.get(AccountStatus.CANCELLED, 0),
                    run_id,
                ),
            )

    def run_accounts(self, run_id: int):
        with self.connect() as db:
            return db.execute(
                """SELECT instance_index,instance_name,status,error,retry_count,started_by_run
                   FROM run_accounts WHERE run_id=? ORDER BY instance_index""", (run_id,)
            ).fetchall()

    def retry_members(self, run_id: int) -> tuple[tuple[int, str], ...]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT instance_index,instance_name FROM run_accounts
                   WHERE run_id=? AND status=? ORDER BY instance_index""", (run_id, AccountStatus.FAILED)
            ).fetchall()
        return tuple((int(index), str(name)) for index, name in rows)

    def create_task_run(self, namespace: str, task: str, index: int, name: str) -> int:
        with self.connect() as db:
            cursor = db.execute(
                """INSERT INTO task_runs(
                       namespace,task,instance_index,instance_name,status,started_at
                   ) VALUES (?,?,?,?,?,?)""",
                (namespace, task, index, name, "RUNNING", _stamp()),
            )
        return int(cursor.lastrowid)

    def finish_task_run(
        self,
        task_run_id: int,
        status: str,
        *,
        error: str = "",
        report_path: str = "",
    ):
        with self.connect() as db:
            db.execute(
                """UPDATE task_runs SET status=?,finished_at=?,error=?,report_path=?
                   WHERE id=?""",
                (status, _stamp(), error[:1000], report_path, task_run_id),
            )

    def latest_task_run(self, namespace: str, task: str, index: int):
        with self.connect() as db:
            return db.execute(
                """SELECT id,instance_name,status,started_at,finished_at,error,report_path
                   FROM task_runs
                   WHERE namespace=? AND task=? AND instance_index=?
                   ORDER BY id DESC LIMIT 1""",
                (namespace, task, index),
            ).fetchone()

    def reserve_reward_claim(
        self, task_run_id: int, reward_id: str, cycle_key: str, before_evidence: str,
        *, expected_instance: tuple[int, str] | None = None,
        not_dispatched: bool = False,
        vip_daily_period: bool = False,
    ) -> int:
        """Commit intent BEFORE input; interruption must never make it retryable.

        cycle_key must identify a visually proven reward opportunity, not a
        screenshot hash, process/boot ID, or an assumed local-midnight reset.
        By default an unresolved attempt blocks all cycles. The explicit fixed
        VIP policy permits a new proven daily period, preserving old rows.
        """
        if not all(isinstance(v, str) and v.strip() for v in (reward_id, cycle_key, before_evidence)):
            raise ValueError("Reward identity, proven cycle and before evidence are required.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute(
                "SELECT namespace,instance_index,instance_name,status FROM task_runs WHERE id=?",
                (task_run_id,),
            ).fetchone()
            if run is None or run[3] != "RUNNING":
                raise ValueError("Claim reservation requires an active task run.")
            namespace, index, name, _ = run
            if expected_instance is not None and expected_instance != (index, name):
                raise ValueError("Claim evidence does not belong to the task run's account.")
            if vip_daily_period:
                from top_heroes_auto.automation.vip_period import current_attempts
                from top_heroes_auto.automation.vip_period import cycle_key as vip_cycle_key

                if cycle_key != vip_cycle_key(reward_id):
                    raise ValueError('VIP period changed; take fresh evidence before reserving.')
                db.row_factory = sqlite3.Row
                rows = db.execute('SELECT * FROM reward_claims WHERE namespace=? AND instance_index=? AND reward_id=?',
                                  (namespace, index, reward_id)).fetchall()
                existing = current_attempts(rows, reward_id)
            else:
                existing = db.execute(
                    """SELECT id FROM reward_claims WHERE namespace=? AND instance_index=?
                       AND reward_id=? AND (cycle_key=? OR status='RESERVED')""",
                    (namespace, index, reward_id, cycle_key),
                ).fetchone()
            if existing:
                raise ValueError("Reward already attempted or unresolved; automatic retry forbidden.")
            cursor = db.execute(
                """INSERT INTO reward_claims(namespace,instance_index,instance_name,reward_id,
                   cycle_key,task_run_id,status,reserved_at,before_evidence)
                   VALUES (?,?,?,?,?,?,'RESERVED',?,?)""",
                (namespace, index, name, reward_id, cycle_key, task_run_id, _stamp(), before_evidence),
            )
            if not_dispatched:
                db.execute("UPDATE reward_claims SET dispatch_state='NOT_DISPATCHED' WHERE id=?", (cursor.lastrowid,))
            return int(cursor.lastrowid)

    def mark_reward_dispatch(self, claim_id: int, task_run_id: int):
        """Commit uncertainty BEFORE entering claim-capable transport, never after."""
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE reward_claims SET dispatch_state='POSSIBLE'
                   WHERE id=? AND task_run_id=? AND status='RESERVED' AND dispatch_state='NOT_DISPATCHED'""",
                (claim_id, task_run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError('Claim reservation missing or already final.')

    def release_undispatched_reward(self, claim_id: int, task_run_id: int, evidence: str):
        """Archive only a positively undispatched reservation; legacy UNKNOWN stays locked."""
        import json

        if not evidence.strip():
            raise ValueError('Release requires evidence.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM reward_claims WHERE id=? AND task_run_id=?',
                             (claim_id, task_run_id)).fetchone()
            if row is None or row['status'] != 'RESERVED' or row['dispatch_state'] != 'NOT_DISPATCHED':
                raise ValueError('Only proven NOT_DISPATCHED reservations can be released.')
            db.execute('INSERT INTO reward_release_audit(claim_id,released_at,original_row,evidence) VALUES (?,?,?,?)',
                       (claim_id, _stamp(), json.dumps(dict(row), ensure_ascii=False), evidence))
            db.execute('DELETE FROM reward_claims WHERE id=? AND task_run_id=?', (claim_id, task_run_id))

    def verify_reward_claim(self, claim_id: int, task_run_id: int, after_evidence: str):
        """A receipt is permanent and belongs only to its reserving task run."""
        if not isinstance(after_evidence, str) or not after_evidence.strip():
            raise ValueError("Verified postcondition evidence is required.")
        with self.connect() as db:
            cursor = db.execute(
                """UPDATE reward_claims SET status='VERIFIED',verified_at=?,after_evidence=?
                   WHERE id=? AND task_run_id=? AND status='RESERVED'""",
                (_stamp(), after_evidence, claim_id, task_run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Claim is missing, belongs to another run, or is already final.")

    def reward_claims(self, namespace: str, index: int):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(
                """SELECT * FROM reward_claims WHERE namespace=? AND instance_index=? ORDER BY id""",
                (namespace, index),
            )]

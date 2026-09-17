import sqlite3
from dataclasses import dataclass
from pathlib import Path

from top_heroes_auto.ldplayer.client import Instance


@dataclass(frozen=True)
class Metadata:
    selected: bool = False
    protected: bool = False


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
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

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

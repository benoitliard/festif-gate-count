from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from .events import GateEvent


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_events (
  event_id    TEXT PRIMARY KEY,
  payload     TEXT NOT NULL,
  epoch       INTEGER NOT NULL,
  created_at  INTEGER NOT NULL,
  sent        INTEGER NOT NULL DEFAULT 0,
  attempts    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pending_unsent
  ON pending_events(sent, created_at);
CREATE INDEX IF NOT EXISTS idx_pending_epoch
  ON pending_events(epoch);
"""


class EventBuffer:
    """SQLite-backed append-only buffer with replay."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)

    @contextmanager
    def _cursor(self):
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    def append(self, evt: GateEvent, created_at_ms: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO pending_events (event_id, payload, epoch, created_at) VALUES (?, ?, ?, ?)",
                (evt.event_id, evt.to_json(), evt.epoch, created_at_ms),
            )

    def fetch_unsent(self, limit: int = 100) -> list[tuple[str, str, int]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT event_id, payload, attempts FROM pending_events WHERE sent = 0 ORDER BY created_at ASC LIMIT ?",
                (limit,),
            )
            return list(cur.fetchall())

    def mark_sent(self, event_ids: Iterable[str]) -> int:
        ids = list(event_ids)
        if not ids:
            return 0
        with self._cursor() as cur:
            cur.executemany("UPDATE pending_events SET sent = 1 WHERE event_id = ?", [(eid,) for eid in ids])
            return cur.rowcount

    def increment_attempt(self, event_id: str) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE pending_events SET attempts = attempts + 1 WHERE event_id = ?", (event_id,))

    def flush_below_epoch(self, epoch: int) -> int:
        """Mark all unsent events with epoch < given epoch as sent (silently dropped after a reset)."""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE pending_events SET sent = 1 WHERE sent = 0 AND epoch < ?",
                (epoch,),
            )
            return cur.rowcount

    def unsent_count(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pending_events WHERE sent = 0")
            (n,) = cur.fetchone()
            return int(n)

    def purge_sent_older_than(self, ms_age: int, now_ms: int) -> int:
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM pending_events WHERE sent = 1 AND created_at < ?",
                (now_ms - ms_age,),
            )
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()

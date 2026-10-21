"""SQLite storage (stdlib ``sqlite3``, WAL mode) for sessions, attempts, help requests, reports, model calls,
the Tavily part cache and the hub outbox. Thread-safe through one connection guarded by a lock.

Schema = BUILD_PROMPT.md 9.10 plus ``model_calls.session_id`` (per-session budget guard) and ``hub_outbox``
(bench → hub retry queue). Schema version lives in ``PRAGMA user_version``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from polarity.models.session import Attempt, HelpRequest, Report, Session

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, student_alias TEXT, bench_id TEXT, lab_id TEXT,
  started_at TEXT, completed_at TEXT, is_simulated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, session_id TEXT, step_id TEXT, kind TEXT,
  status TEXT, reason TEXT, confidence REAL, hint_level INTEGER, verdict_json TEXT, led_json TEXT,
  raw_image_path TEXT, warped_image_path TEXT, audio_path TEXT, model_id TEXT, latency_ms INTEGER,
  cost_usd REAL, created_at TEXT, is_simulated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS help_requests(id TEXT PRIMARY KEY, session_id TEXT, step_id TEXT, trigger TEXT,
  summary_json TEXT, status TEXT, created_at TEXT, resolved_at TEXT, is_simulated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, lab_id TEXT, created_at TEXT, model_id TEXT,
  markdown TEXT, input_stats_json TEXT, cost_usd REAL);
CREATE TABLE IF NOT EXISTS model_calls(id TEXT PRIMARY KEY, role TEXT, model_id TEXT, ok INTEGER, latency_ms INTEGER,
  prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL, error TEXT, created_at TEXT, session_id TEXT);
CREATE TABLE IF NOT EXISTS part_cache(part TEXT PRIMARY KEY, summary_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS hub_outbox(id TEXT PRIMARY KEY, kind TEXT, payload_json TEXT, created_at TEXT,
  attempts INTEGER DEFAULT 0, last_error TEXT);
CREATE INDEX IF NOT EXISTS idx_attempts_session ON attempts(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_help_status ON help_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_calls_created ON model_calls(created_at);
"""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=10)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version < SCHEMA_VERSION:
                self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── low level ────────────────────────────────────────────────────────────────────────────

    def _exec(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    def _all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]

    def _one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def transaction(self) -> _Txn:
        return _Txn(self)

    # ── sessions ─────────────────────────────────────────────────────────────────────────────

    def create_session(self, alias: str, lab_id: str, bench_id: str | None = None, *, session_id: str | None = None,
                       started_at: str | None = None, is_simulated: bool = False) -> Session:
        s = Session(id=session_id or new_id(), student_alias=alias, bench_id=bench_id, lab_id=lab_id,
                    started_at=started_at or now_iso(), is_simulated=is_simulated)
        self._exec("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?)",
                   (s.id, s.student_alias, s.bench_id, s.lab_id, s.started_at, s.completed_at, int(s.is_simulated)))
        return s

    def get_session(self, session_id: str) -> Session | None:
        row = self._one("SELECT * FROM sessions WHERE id=?", (session_id,))
        return Session(**row) if row else None

    def complete_session(self, session_id: str, at: str | None = None) -> None:
        self._exec("UPDATE sessions SET completed_at=? WHERE id=?", (at or now_iso(), session_id))

    def list_sessions(self, lab_id: str | None = None) -> list[Session]:
        if lab_id:
            rows = self._all("SELECT * FROM sessions WHERE lab_id=? ORDER BY started_at", (lab_id,))
        else:
            rows = self._all("SELECT * FROM sessions ORDER BY started_at")
        return [Session(**r) for r in rows]

    # ── attempts ─────────────────────────────────────────────────────────────────────────────

    def add_attempt(self, a: Attempt) -> Attempt:
        self._exec("INSERT OR REPLACE INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (a.id, a.session_id, a.step_id, a.kind, a.status, a.reason, a.confidence, a.hint_level,
                    a.verdict_json, a.led_json, a.raw_image_path, a.warped_image_path, a.audio_path, a.model_id,
                    a.latency_ms, a.cost_usd, a.created_at, int(a.is_simulated)))
        return a

    def list_attempts(self, session_id: str | None = None, step_id: str | None = None,
                      kind: str | None = None) -> list[Attempt]:
        sql, params = "SELECT * FROM attempts WHERE 1=1", []
        for col, val in (("session_id", session_id), ("step_id", step_id), ("kind", kind)):
            if val is not None:
                sql += f" AND {col}=?"
                params.append(val)
        return [Attempt(**r) for r in self._all(sql + " ORDER BY created_at, rowid", params)]

    def get_attempt(self, attempt_id: str) -> Attempt | None:
        row = self._one("SELECT * FROM attempts WHERE id=?", (attempt_id,))
        return Attempt(**row) if row else None

    def last_attempt(self) -> Attempt | None:
        row = self._one("SELECT * FROM attempts ORDER BY created_at DESC, rowid DESC LIMIT 1")
        return Attempt(**row) if row else None

    # ── help requests ────────────────────────────────────────────────────────────────────────

    def add_help(self, session_id: str, step_id: str, trigger: str, *, summary: dict[str, Any] | None = None,
                 help_id: str | None = None, created_at: str | None = None, is_simulated: bool = False,
                 status: str = "open", resolved_at: str | None = None) -> HelpRequest:
        h = HelpRequest(id=help_id or new_id(), session_id=session_id, step_id=step_id, trigger=trigger,
                        summary_json=json.dumps(summary) if summary is not None else None, status=status,  # type: ignore[arg-type]
                        created_at=created_at or now_iso(), resolved_at=resolved_at, is_simulated=is_simulated)
        self._exec("INSERT OR REPLACE INTO help_requests VALUES (?,?,?,?,?,?,?,?,?)",
                   (h.id, h.session_id, h.step_id, h.trigger, h.summary_json, h.status, h.created_at, h.resolved_at,
                    int(h.is_simulated)))
        return h

    def update_help_summary(self, help_id: str, summary: dict[str, Any]) -> None:
        self._exec("UPDATE help_requests SET summary_json=? WHERE id=?", (json.dumps(summary), help_id))

    def resolve_help(self, help_id: str) -> bool:
        cur = self._exec("UPDATE help_requests SET status='resolved', resolved_at=? WHERE id=? AND status='open'",
                         (now_iso(), help_id))
        return cur.rowcount > 0

    def get_help(self, help_id: str) -> HelpRequest | None:
        row = self._one("SELECT * FROM help_requests WHERE id=?", (help_id,))
        return HelpRequest(**row) if row else None

    def list_help(self, status: str | None = "open", session_id: str | None = None) -> list[HelpRequest]:
        sql, params = "SELECT * FROM help_requests WHERE 1=1", []
        if status:
            sql += " AND status=?"
            params.append(status)
        if session_id:
            sql += " AND session_id=?"
            params.append(session_id)
        return [HelpRequest(**r) for r in self._all(sql + " ORDER BY created_at", params)]

    # ── reports ──────────────────────────────────────────────────────────────────────────────

    def add_report(self, r: Report) -> Report:
        self._exec("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?)",
                   (r.id, r.lab_id, r.created_at, r.model_id, r.markdown, r.input_stats_json, r.cost_usd))
        return r

    def get_report(self, report_id: str) -> Report | None:
        row = self._one("SELECT * FROM reports WHERE id=?", (report_id,))
        return Report(**row) if row else None

    def list_reports(self) -> list[Report]:
        return [Report(**r) for r in self._all("SELECT * FROM reports ORDER BY created_at DESC")]

    # ── model calls (router recorder) ────────────────────────────────────────────────────────

    def record_model_call(self, *, role: str, model_id: str, ok: bool, latency_ms: int, prompt_tokens: int,
                          completion_tokens: int, cost_usd: float | None, error: str | None,
                          session_id: str | None) -> None:
        self._exec("INSERT INTO model_calls VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (new_id(), role, model_id, int(ok), latency_ms, prompt_tokens, completion_tokens, cost_usd, error,
                    now_iso(), session_id))

    def spend(self, session_id: str | None) -> tuple[float, float]:
        """(session_usd, day_usd) from recorded calls with a known cost."""
        today = datetime.now().astimezone().date().isoformat()
        day = self._one("SELECT COALESCE(SUM(cost_usd),0) AS s FROM model_calls WHERE substr(created_at,1,10)=?",
                        (today,))
        sess = {"s": 0.0}
        if session_id:
            sess = self._one("SELECT COALESCE(SUM(cost_usd),0) AS s FROM model_calls WHERE session_id=?",
                             (session_id,)) or sess
        return float(sess["s"]), float(day["s"] if day else 0.0)

    def recent_model_calls(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM model_calls ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))

    def token_totals(self) -> dict[str, Any]:
        return self._one("SELECT COUNT(*) AS calls, COALESCE(SUM(prompt_tokens),0) AS prompt_tokens, "
                         "COALESCE(SUM(completion_tokens),0) AS completion_tokens FROM model_calls") or {}

    # ── part cache ───────────────────────────────────────────────────────────────────────────

    def get_part(self, part: str) -> dict[str, Any] | None:
        row = self._one("SELECT summary_json FROM part_cache WHERE part=?", (part.upper(),))
        return json.loads(row["summary_json"]) if row else None

    def put_part(self, part: str, summary: dict[str, Any]) -> None:
        self._exec("INSERT OR REPLACE INTO part_cache VALUES (?,?,?)", (part.upper(), json.dumps(summary), now_iso()))

    # ── hub outbox ───────────────────────────────────────────────────────────────────────────

    def outbox_add(self, kind: str, payload: dict[str, Any]) -> str:
        oid = new_id()
        self._exec("INSERT INTO hub_outbox VALUES (?,?,?,?,0,NULL)", (oid, kind, json.dumps(payload), now_iso()))
        return oid

    def outbox_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM hub_outbox ORDER BY created_at, rowid LIMIT ?", (limit,))

    def outbox_done(self, outbox_id: str) -> None:
        self._exec("DELETE FROM hub_outbox WHERE id=?", (outbox_id,))

    def outbox_failed(self, outbox_id: str, error: str) -> None:
        self._exec("UPDATE hub_outbox SET attempts=attempts+1, last_error=? WHERE id=?", (error[:300], outbox_id))

    # ── demo data ────────────────────────────────────────────────────────────────────────────

    def has_simulated(self) -> bool:
        return bool(self._one("SELECT 1 AS x FROM sessions WHERE is_simulated=1 LIMIT 1"))

    def clear_simulated(self) -> int:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) FROM sessions WHERE is_simulated=1").fetchone()[0]
            self._conn.execute("DELETE FROM attempts WHERE is_simulated=1")
            self._conn.execute("DELETE FROM help_requests WHERE is_simulated=1")
            self._conn.execute("DELETE FROM sessions WHERE is_simulated=1")
            return int(n)


class _Txn:
    """``with db.transaction():`` groups many writes (used by seed-demo)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def __enter__(self) -> Database:
        self.db._lock.acquire()
        self.db._conn.execute("BEGIN")
        return self.db

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            self.db._conn.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self.db._lock.release()

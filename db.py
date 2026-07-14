"""SQLite/Postgres data layer for the job application tracker.

Single source of truth for the schema and all CRUD helpers used by both the
migration script and the Streamlit app.

Local single-user mode (the default) uses a SQLite file, exactly as before.
Setting ``DATABASE_URL`` switches to Postgres — used only for the optional
shared Render deployment, where each user's data lives in its own Postgres
*schema* (see ``connect(schema=...)``) so every query below stays identical
between the two backends and between users.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from config import DB_PATH  # noqa: F401  (re-exported for callers as db.DB_PATH)

try:  # optional — only needed for the hosted Postgres deployment
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

DATABASE_URL = os.environ.get("DATABASE_URL")
IS_POSTGRES = bool(DATABASE_URL)

# Columns the app reads/writes, in display order. `id`, `source_job_id` and the
# timestamps are managed automatically and are not part of this list.
FIELDS = [
    "date_found",
    "title",
    "company",
    "type",
    "rate",
    "location",
    "posted",
    "link",
    "fit_notes",
    "status",
    "cv_version",
    "cover_letter",
    "date_applied",
    "outcome",
]

# App-managed columns — set by the app/agent (follow-ups, archive), never by the
# CSV/xlsx importers, so they are kept out of the importable FIELDS above.
APP_COLUMNS = (
    "contact_email", "contact_source", "follow_up", "follow_up_status",
    "follow_up_draft", "archived",
)

# Canonical pipeline statuses. "etc." in the brief — kept open via free text in
# the UI, but these drive ordering, metrics and the default dropdown.
# "Draft CV" / "Draft CV & Cover Letter" are one-shot action triggers: setting one
# in the To-action queue drafts the document(s) on save, then settles to "CV Drafted".
STATUSES = [
    "Found", "Draft CV", "Draft CV & Cover Letter", "CV Drafted",
    "Applied", "Shortlisted", "Interview", "Offer", "Pass", "Rejected", "Expired",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date_found    TEXT,
    title         TEXT NOT NULL,
    company       TEXT,
    type          TEXT,
    rate          TEXT,
    location      TEXT,
    posted        TEXT,
    link          TEXT,
    fit_notes     TEXT,
    status        TEXT NOT NULL DEFAULT 'Found',
    cv_version    TEXT,
    cover_letter  TEXT,
    date_applied  TEXT,
    outcome       TEXT,
    contact_email TEXT,                        -- recruiter contact (Reed applications page)
    contact_source TEXT,                       -- provenance of contact_email (verified only)
    follow_up     INTEGER NOT NULL DEFAULT 0,  -- 0 default (ticked in UI) / 1 ticked / 2 opted out
    follow_up_status TEXT,                     -- '', 'Draft ready', 'Sent <date>', or a note
    follow_up_draft TEXT,                      -- link to the Gmail draft (user reviews & sends)
    archived      INTEGER NOT NULL DEFAULT 0,  -- 1 = 'Ended'/closed -> Archive
    source_job_id TEXT,                       -- numeric job-id parsed from the link, for dedupe
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Helps importers avoid re-inserting roles already logged.
CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id ON jobs(source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

# Same shape as SCHEMA, in Postgres dialect (SERIAL instead of AUTOINCREMENT,
# NOW() instead of SQLite's datetime('now')). Kept column-for-column identical
# to SCHEMA so app/agent code never needs to know which backend it's talking to.
SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS jobs (
    id            SERIAL PRIMARY KEY,
    date_found    TEXT,
    title         TEXT NOT NULL,
    company       TEXT,
    type          TEXT,
    rate          TEXT,
    location      TEXT,
    posted        TEXT,
    link          TEXT,
    fit_notes     TEXT,
    status        TEXT NOT NULL DEFAULT 'Found',
    cv_version    TEXT,
    cover_letter  TEXT,
    date_applied  TEXT,
    outcome       TEXT,
    contact_email TEXT,
    contact_source TEXT,
    follow_up     INTEGER NOT NULL DEFAULT 0,
    follow_up_status TEXT,
    follow_up_draft TEXT,
    archived      INTEGER NOT NULL DEFAULT 0,
    source_job_id TEXT,
    created_at    TEXT NOT NULL DEFAULT (NOW()::TEXT),
    updated_at    TEXT NOT NULL DEFAULT (NOW()::TEXT)
);

CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id ON jobs(source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

_SCHEMA_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _safe_schema(schema: str | None) -> str:
    """Whitelist a Postgres schema name before it's interpolated into SQL.

    Callers only ever pass a fixed, app-controlled slug (from APP_USERS), never
    raw user text — this is defense in depth, not the primary control.
    """
    name = (schema or "public").strip().lower()
    if not _SCHEMA_NAME_RE.match(name):
        raise ValueError(f"invalid schema name: {name!r}")
    return name


def _pg_sql(sql: str) -> str:
    """Translate SQLite's `?` placeholders to Postgres's `%s`."""
    return sql.replace("?", "%s")


def _now_sql() -> str:
    return "NOW()::TEXT" if IS_POSTGRES else "datetime('now')"


class _PgConnAdapter:
    """Wraps a psycopg2 connection to match the sqlite3.Connection surface the
    rest of this codebase relies on: a `.execute()` shortcut and dict-like rows.

    Unlike SQLite's context manager (which only commits/rolls back — the
    connection stays open, harmless for a local file), `__exit__` here also
    *closes* the connection: Postgres connections are a limited, relatively
    expensive resource, and every `db.connect()` call site in this app opens
    one per interaction without an explicit close, which would exhaust
    Render's connection cap under real use.
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = ()):
        cur = self._conn.cursor()
        cur.execute(_pg_sql(sql), params)
        return cur

    def executescript(self, sql: str) -> None:
        cur = self._conn.cursor()
        cur.execute(sql)
        cur.close()

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> _PgConnAdapter:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()


def connect(db_path: Path | str = DB_PATH, schema: str | None = None):
    """Open a connection. SQLite by default; Postgres when DATABASE_URL is set.

    ``schema`` only applies to Postgres — it selects which user's data this
    connection sees (see the module docstring). Ignored for SQLite, where
    per-user separation isn't in play (each SQLite file is already one user).
    """
    if IS_POSTGRES:
        if psycopg2 is None:
            raise RuntimeError(
                "DATABASE_URL is set but psycopg2 isn't installed — "
                "add psycopg2-binary to requirements.txt (pip install psycopg2-binary)."
            )
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        safe_schema = _safe_schema(schema)
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {safe_schema}")
            cur.execute(f"SET search_path TO {safe_schema}")
        conn.commit()
        return _PgConnAdapter(conn)

    # timeout: how long sqlite3 waits on a locked DB before raising.
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets the Streamlit app keep reading while a script (e.g. an importer)
    # writes — no whole-file lock like an open spreadsheet. busy_timeout makes a
    # writer wait its turn instead of failing immediately.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path: Path | str = DB_PATH, schema: str | None = None) -> None:
    with connect(db_path, schema) as conn:
        conn.executescript(SCHEMA_POSTGRES if IS_POSTGRES else SCHEMA)
        _ensure_columns(conn)


def _ensure_columns(conn) -> None:
    """Add columns introduced after a database was first created (idempotent)."""
    if IS_POSTGRES:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'jobs' AND table_schema = current_schema()"
        )
        existing = {row["column_name"] for row in rows}
    else:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for column, ddl in (
        ("cover_letter", "TEXT"),
        ("contact_email", "TEXT"),
        ("contact_source", "TEXT"),
        ("follow_up", "INTEGER NOT NULL DEFAULT 0"),
        ("follow_up_status", "TEXT"),
        ("follow_up_draft", "TEXT"),
        ("archived", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")


def insert_job(conn, data: dict[str, Any]) -> int:
    cols = [c for c in (*FIELDS, "source_job_id", *APP_COLUMNS) if c in data]
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({placeholders})"
    if IS_POSTGRES:
        sql += " RETURNING id"
        cur = conn.execute(sql, [data.get(c) for c in cols])
        return int(cur.fetchone()["id"])
    cur = conn.execute(sql, [data.get(c) for c in cols])
    return int(cur.lastrowid)


def update_job(conn, job_id: int, data: dict[str, Any]) -> None:
    cols = [c for c in (*FIELDS, "source_job_id", *APP_COLUMNS) if c in data]
    if not cols:
        return
    assignments = ", ".join(f"{c} = ?" for c in cols)
    sql = f"UPDATE jobs SET {assignments}, updated_at = {_now_sql()} WHERE id = ?"
    conn.execute(sql, [*(data.get(c) for c in cols), job_id])


def delete_job(conn, job_id: int) -> None:
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def fetch_all(conn) -> list:
    return conn.execute("SELECT * FROM jobs ORDER BY date_found DESC, id DESC").fetchall()


def find_by_source_job_id(conn, source_job_id: str):
    return conn.execute(
        "SELECT * FROM jobs WHERE source_job_id = ?", (source_job_id,)
    ).fetchone()


def upsert_job(conn, data: dict[str, Any]) -> tuple[int, str]:
    """Insert or update a job keyed on its ``source_job_id``.

    Lets an external script write a role without any fragile row-matching — same
    job-id updates in place, a new job-id inserts. Falls back to a plain insert
    when no ``source_job_id`` is present.
    Returns ``(id, "inserted" | "updated")``.
    """
    sid = data.get("source_job_id")
    if sid:
        existing = find_by_source_job_id(conn, sid)
        if existing is not None:
            update_job(conn, existing["id"], data)
            return int(existing["id"]), "updated"
    return insert_job(conn, data), "inserted"

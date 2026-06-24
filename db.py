"""SQLite data layer for the job application tracker.

Single source of truth for the schema and all CRUD helpers used by both the
migration script and the Streamlit app.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from config import DB_PATH  # noqa: F401  (re-exported for callers as db.DB_PATH)

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

# Canonical pipeline statuses. "etc." in the brief — kept open via free text in
# the UI, but these drive ordering, metrics and the default dropdown.
STATUSES = ["Found", "Applied", "Shortlisted", "Interview", "Offer", "Pass", "Rejected", "Expired"]

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
    source_job_id TEXT,                       -- numeric job-id parsed from the link, for dedupe
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Helps importers avoid re-inserting roles already logged.
CREATE INDEX IF NOT EXISTS idx_jobs_source_job_id ON jobs(source_job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
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


def init_db(db_path: Path | str = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was first created (idempotent)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for column, ddl in (("cover_letter", "TEXT"),):
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")


def insert_job(conn: sqlite3.Connection, data: dict[str, Any]) -> int:
    cols = [c for c in (*FIELDS, "source_job_id") if c in data]
    placeholders = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({placeholders})"
    cur = conn.execute(sql, [data.get(c) for c in cols])
    return int(cur.lastrowid)


def update_job(conn: sqlite3.Connection, job_id: int, data: dict[str, Any]) -> None:
    cols = [c for c in (*FIELDS, "source_job_id") if c in data]
    if not cols:
        return
    assignments = ", ".join(f"{c} = ?" for c in cols)
    sql = f"UPDATE jobs SET {assignments}, updated_at = datetime('now') WHERE id = ?"
    conn.execute(sql, [*(data.get(c) for c in cols), job_id])


def delete_job(conn: sqlite3.Connection, job_id: int) -> None:
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def fetch_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM jobs ORDER BY date_found DESC, id DESC").fetchall()


def find_by_source_job_id(conn: sqlite3.Connection, source_job_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM jobs WHERE source_job_id = ?", (source_job_id,)
    ).fetchone()


def upsert_job(conn: sqlite3.Connection, data: dict[str, Any]) -> tuple[int, str]:
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

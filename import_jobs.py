"""Import roles from an external SQLite database into the tracker.

Some setups have another tool — a scraper, an automation, a second tracker — drop
newly found roles into a separate SQLite database. This merges those into the
canonical tracker DB, keyed on the source job-id (with a title|company fallback),
inserting only genuinely new roles. Roles already in the tracker are left
untouched, so any edits you've made here always win.

Configure the source with ``--source PATH`` or the ``JOBTRACKER_IMPORT_DB``
environment variable. The source database needs a ``jobs`` table with at least a
``title`` column; recognised columns (see ``db.FIELDS``) are imported, the rest
are ignored.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import config
import db
from normalize import norm_status, parse_job_id, tc_key


def import_jobs(source_db: Path | str | None = None,
                target_db: Path | str | None = None) -> dict:
    """Insert new roles from ``source_db`` into ``target_db``. Returns a summary."""
    source_db = Path(source_db) if source_db else config.IMPORT_DB_PATH
    target_db = target_db if target_db is not None else db.DB_PATH

    summary = {"source_exists": bool(source_db and Path(source_db).exists()),
               "source_rows": 0, "inserted": 0, "skipped": 0}
    if not summary["source_exists"]:
        return summary

    src = sqlite3.connect(str(source_db))
    src.row_factory = sqlite3.Row
    try:
        source_rows = src.execute("SELECT * FROM jobs").fetchall()
    except sqlite3.OperationalError:
        src.close()
        return summary  # no jobs table yet
    src.close()
    summary["source_rows"] = len(source_rows)

    db.init_db(target_db)
    with db.connect(target_db) as conn:
        existing = db.fetch_all(conn)
        seen_ids = {r["source_job_id"] for r in existing if r["source_job_id"]}
        seen_tc = {tc_key(r["title"], r["company"]) for r in existing}

        for row in source_rows:
            keys = row.keys()
            data = {f: (row[f] if f in keys else None) for f in db.FIELDS}
            if not data.get("title"):
                continue
            data["status"] = norm_status(data.get("status"))  # status is NOT NULL
            sid = row["source_job_id"] if "source_job_id" in keys else None
            sid = sid or parse_job_id(data.get("link"))
            data["source_job_id"] = sid
            tc = tc_key(data.get("title"), data.get("company"))

            if (sid and sid in seen_ids) or tc in seen_tc:
                summary["skipped"] += 1
                continue
            db.insert_job(conn, data)
            summary["inserted"] += 1
            if sid:
                seen_ids.add(sid)
            seen_tc.add(tc)
        conn.commit()
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Import roles from an external SQLite DB.")
    ap.add_argument("--source", type=Path, default=config.IMPORT_DB_PATH,
                    help="Source SQLite database (or set JOBTRACKER_IMPORT_DB)")
    ap.add_argument("--db", dest="target_db", type=Path, default=db.DB_PATH)
    args = ap.parse_args()

    if args.source is None:
        raise SystemExit(
            "No source database configured. Pass --source PATH or set "
            "JOBTRACKER_IMPORT_DB in .env."
        )

    result = import_jobs(args.source, args.target_db)
    if not result["source_exists"]:
        print(f"No database found at {args.source} — nothing to import.")
        return
    print(f"Source had {result['source_rows']} roles -> "
          f"{result['inserted']} new inserted, {result['skipped']} already present.")


if __name__ == "__main__":
    main()

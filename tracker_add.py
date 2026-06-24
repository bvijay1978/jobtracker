"""Add or update roles in the tracker database from a script or the shell.

Each role is upserted on its ``source_job_id`` (a numeric job-id parsed from the
link if not supplied): a job seen again updates in place, a new one inserts.
Because the DB runs in WAL mode this is safe to call while the app is open.

Use as a library
----------------
    import tracker_add
    tracker_add.add_role({
        "date_found": "2026-06-24",
        "title": "Senior Backend Engineer",
        "company": "Example Recruiting",
        "type": "Contract",
        "rate": "£700/day",
        "location": "London (Remote)",
        "posted": "2026-06-20",
        "link": "https://www.example.com/jobs/senior-backend-engineer/57012345",
        "fit_notes": "Strong match on the platform stack",
        "status": "Found",
        "cv_version": "cv-backend.pdf",
    })

    # a whole batch at once:
    summary = tracker_add.add_roles([role1, role2, ...])

Use from the shell
------------------
    python tracker_add.py --json '{"title": "...", "link": "..."}'
    python tracker_add.py --json '[ {...}, {...} ]'
    cat roles.json | python tracker_add.py            # reads JSON from stdin
    python tracker_add.py --title "Senior Backend Engineer" \
        --company "Example Recruiting" --status Found \
        --link "https://www.example.com/jobs/.../57012345"

Prints a JSON summary: {"inserted": n, "updated": m, "results": [...]}.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

import db
from normalize import clean, norm_date, norm_status, parse_job_id

DATE_FIELDS = {"date_found", "posted", "date_applied"}


def normalize_role(data: dict) -> dict:
    """Map an arbitrary input dict to a clean jobs-table record."""
    rec: dict = {}
    for field in db.FIELDS:
        value = data.get(field)
        if field == "status":
            rec[field] = norm_status(value)
        elif field in DATE_FIELDS:
            rec[field] = norm_date(value)
        else:
            rec[field] = clean(value)
    if not rec.get("title"):
        raise ValueError("role is missing a 'title'")
    rec["source_job_id"] = clean(data.get("source_job_id")) or parse_job_id(rec.get("link"))
    return rec


def add_role(data: dict, conn: sqlite3.Connection | None = None) -> tuple[int, str]:
    """Upsert one role. Returns (id, 'inserted'|'updated').

    Pass an open ``conn`` to batch within a caller-managed transaction; otherwise
    a connection is opened and committed here.
    """
    rec = normalize_role(data)
    if conn is not None:
        return db.upsert_job(conn, rec)
    with db.connect() as own:
        result = db.upsert_job(own, rec)
        own.commit()
        return result


def add_roles(roles: list[dict]) -> dict:
    """Upsert many roles in a single transaction; returns a summary dict."""
    db.init_db()
    results = []
    with db.connect() as conn:
        for role in roles:
            try:
                job_id, action = add_role(role, conn=conn)
                results.append({"id": job_id, "action": action,
                                "title": role.get("title"), "company": role.get("company")})
            except ValueError as exc:
                results.append({"action": "skipped", "error": str(exc), "role": role})
        conn.commit()
    return {
        "inserted": sum(r["action"] == "inserted" for r in results),
        "updated": sum(r["action"] == "updated" for r in results),
        "skipped": sum(r["action"] == "skipped" for r in results),
        "results": results,
    }


def _roles_from_args(args: argparse.Namespace) -> list[dict]:
    if args.json:
        payload = json.loads(args.json)
    elif args.title:
        payload = {
            k: getattr(args, k)
            for k in db.FIELDS
            if getattr(args, k, None) is not None
        }
        if args.source_job_id:
            payload["source_job_id"] = args.source_job_id
    else:  # read JSON from stdin
        raw = sys.stdin.read().strip()
        if not raw:
            raise SystemExit("No role supplied (use --json, --title, or pipe JSON via stdin).")
        payload = json.loads(raw)
    return payload if isinstance(payload, list) else [payload]


def main() -> None:
    ap = argparse.ArgumentParser(description="Add/update roles in the job tracker DB.")
    ap.add_argument("--json", help="A JSON object or array of role objects.")
    ap.add_argument("--source-job-id", dest="source_job_id")
    for field in db.FIELDS:
        ap.add_argument(f"--{field.replace('_', '-')}", dest=field)
    args = ap.parse_args()

    summary = add_roles(_roles_from_args(args))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

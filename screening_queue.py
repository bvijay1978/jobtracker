"""Agent-side helper for the screening-CV queue.

The Streamlit app marks roles ``Draft CV`` / ``Draft CV & Cover Letter`` — a
*queue only*; it writes no document (it has no LLM and can't read a job
description). Claude, which has the JD and an LLM, processes the queue: for each
role it reads the JD from the stored link, authors the keyword-mirrored
``screening`` payload, renders it with ``screening_cv.generate_screening_cv``,
then calls ``record_result`` here to file the outcome back onto the role.

The functions take an explicit connection so callers (and tests) stay in control
of which database they touch — never an implicit write to the canonical one.
"""

from __future__ import annotations

import sqlite3

import db

CV_QUEUE_STATUSES = ("Draft CV", "Draft CV & Cover Letter")


def list_queue(conn: sqlite3.Connection) -> list[dict]:
    """Return roles awaiting a screening CV, newest first."""
    rows = [dict(r) for r in db.fetch_all(conn) if (r["status"] or "") in CV_QUEUE_STATUSES]
    rows.sort(key=lambda r: r.get("date_found") or "", reverse=True)
    return rows


def record_result(
    conn: sqlite3.Connection,
    role_id: int,
    cv_filename: str,
    coverage: dict | None = None,
    base_fit_notes: str = "",
) -> None:
    """File a drafted screening CV onto the role and settle it to 'CV Drafted'.

    If a ``coverage`` dict (from ``screening_cv.keyword_coverage``) is supplied, a
    short ``<pct>% kw coverage; gaps: …`` note is appended to the role's fit notes
    so the screening signal is visible in the tracker.
    """
    data: dict = {"status": "CV Drafted", "cv_version": cv_filename}
    if coverage:
        note = f"Screening CV {coverage.get('pct', 0)}% kw coverage"
        gaps = coverage.get("missing") or []
        if gaps:
            note += f"; gaps: {', '.join(gaps[:6])}"
        data["fit_notes"] = f"{base_fit_notes} | {note}".strip(" |") if base_fit_notes else note
    db.update_job(conn, role_id, data)

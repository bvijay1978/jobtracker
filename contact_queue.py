"""Agent-side helper for the contact-resolver queue.

Follow-up emails need a recruiter address. The Streamlit app surfaces live roles
that have no ``contact_email`` yet — a *queue only*; the app can't reach Gmail,
the web or LinkedIn (ADR-002). Claude resolves each one to a **verified** address
(never a constructed guess), walking a best-first ladder:

    1. the user's Gmail        -> a real, named sender      (``named-inbox``)
    2. LinkedIn / a team page  -> a verified named address  (``named-verified``)
    3. the company website     -> a monitored generic inbox (``dept-inbox``)
    4. nothing reliable        -> leave empty, nudge via platform (``none``)

then calls ``record_contact`` (or ``record_no_contact``) here to file the result.
Confidence order: named-inbox > named-verified > dept-inbox > none. Only verified
addresses are ever written — no assumed ``first.last@domain`` patterns.

Callers pass an explicit connection so tests/scripts stay in control of which
database they touch — never an implicit write to the canonical one.
"""

from __future__ import annotations

import sqlite3

import db

# Live pipeline statuses that warrant a follow-up (and therefore a contact).
NEEDS_CONTACT_STATUSES = ("Applied", "Shortlisted", "Interview", "Offer")

# Provenance tags for contact_email, best-first. Only verified addresses are
# written; ``none`` records that no reachable address exists.
CONTACT_SOURCES = ("named-inbox", "named-verified", "dept-inbox", "none")


def list_needs_contact(conn: sqlite3.Connection) -> list[dict]:
    """Return live, non-archived roles that still need a recruiter contact.

    A role qualifies when it is active, in a live stage, has no ``contact_email``
    and has not already been resolved to ``none`` (no reachable address). Sorted
    by apply-date, newest first.
    """
    out: list[dict] = []
    for r in db.fetch_all(conn):
        row = dict(r)
        if row.get("archived"):
            continue
        if (row.get("status") or "") not in NEEDS_CONTACT_STATUSES:
            continue
        if (row.get("contact_email") or "").strip():
            continue
        if (row.get("contact_source") or "").strip() == "none":
            continue
        out.append(row)
    out.sort(key=lambda r: r.get("date_applied") or "", reverse=True)
    return out


def record_contact(
    conn: sqlite3.Connection,
    role_id: int,
    email: str,
    source: str,
    date_applied: str | None = None,
) -> None:
    """File a resolved (verified) recruiter address onto a role.

    ``source`` must be a real-address tag in ``CONTACT_SOURCES`` (``none`` goes
    through ``record_no_contact``). ``date_applied`` is written only when supplied
    and the role has none, so a harvested apply-date backfills for free without
    clobbering an existing value.
    """
    email = (email or "").strip()
    if not email:
        raise ValueError("record_contact needs a non-empty email; use record_no_contact instead")
    if source not in CONTACT_SOURCES or source == "none":
        raise ValueError(f"source must be one of {CONTACT_SOURCES[:-1]}, got {source!r}")
    data: dict = {"contact_email": email, "contact_source": source}
    if date_applied:
        existing = conn.execute(
            "SELECT date_applied FROM jobs WHERE id = ?", (role_id,)
        ).fetchone()
        if existing is not None and not (existing["date_applied"] or "").strip():
            data["date_applied"] = date_applied
    db.update_job(conn, role_id, data)


def record_no_contact(
    conn: sqlite3.Connection,
    role_id: int,
    note: str = "no email — nudge via platform",
) -> None:
    """Mark a role as having no reachable email so it stops re-queuing.

    Sets ``contact_source='none'`` and records the reason in ``follow_up_status``
    (e.g. follow up on LinkedIn or the job board instead of by email).
    """
    db.update_job(conn, role_id, {"contact_source": "none", "follow_up_status": note})

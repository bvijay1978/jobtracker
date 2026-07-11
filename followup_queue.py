"""Agent-side helper for the follow-up email queue.

An applied role becomes *due* a follow-up once 2 working days have passed since
``date_applied`` — long enough not to pester, soon enough to nudge the
application forward. The Streamlit app lists due roles with an opt-out tick
(everything starts ticked); Claude processes the ticked ones: it sweeps Gmail
for replies first (a reply beats a nudge — rejections change status instead),
then writes a short contextual Gmail *draft* per role and files the draft link
back here via ``record_draft``. The user reviews and **sends every email
themselves** in Gmail, then the role is settled with ``mark_sent``.

This module is the single source of the due rule — the app imports ``is_due``
for its metric/section so the two can never disagree.

Callers pass an explicit connection so tests/scripts stay in control of which
database they touch — never an implicit write to the canonical one.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import db

# Working days to wait after applying before a follow-up is due.
WORKING_DAY_LAG = 2

# follow_up column semantics (everything starts ticked — opt-out).
FOLLOW_UP_DEFAULT = 0   # never touched -> shown ticked
FOLLOW_UP_TICKED = 1
FOLLOW_UP_OPTED_OUT = 2


def add_working_days(day: date, n: int) -> date:
    """Return ``day`` advanced by ``n`` working days (Mon–Fri)."""
    while n > 0:
        day += timedelta(days=1)
        if day.weekday() < 5:
            n -= 1
    return day


def is_due(date_applied, today: date | None = None) -> bool:
    """True once ``WORKING_DAY_LAG`` working days have passed since applying.

    Tolerant of blanks/garbage (returns False) so it can be mapped straight
    over a DataFrame column.
    """
    if today is None:
        today = date.today()
    try:
        applied = date.fromisoformat(str(date_applied).strip())
    except (TypeError, ValueError):
        return False
    return today >= add_working_days(applied, WORKING_DAY_LAG)


def _sent(row: dict) -> bool:
    return (row.get("follow_up_status") or "").strip().lower().startswith("sent")


def _drafted(row: dict) -> bool:
    return (row.get("follow_up_status") or "").strip().lower().startswith("draft")


def list_due(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    """Due follow-ups: active + Applied + contact + due + ticked + not sent.

    Roles already at 'Draft ready' stay listed (they're in flight until sent).
    Sorted oldest application first — most overdue at the top.
    """
    out: list[dict] = []
    for r in db.fetch_all(conn):
        row = dict(r)
        if row.get("archived"):
            continue
        if (row.get("status") or "") != "Applied":
            continue
        if not (row.get("contact_email") or "").strip():
            continue
        if int(row.get("follow_up") or 0) == FOLLOW_UP_OPTED_OUT:
            continue
        if _sent(row):
            continue
        if not is_due(row.get("date_applied"), today):
            continue
        out.append(row)
    out.sort(key=lambda r: r.get("date_applied") or "9999-99-99")
    return out


def list_to_draft(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    """The subset of ``list_due`` still needing a draft written."""
    return [r for r in list_due(conn, today) if not _drafted(r)]


def record_draft(conn: sqlite3.Connection, role_id: int, draft_url: str) -> None:
    """File a written Gmail draft onto the role (drafted, NOT sent)."""
    draft_url = (draft_url or "").strip()
    if not draft_url:
        raise ValueError("record_draft needs the Gmail draft URL")
    db.update_job(conn, role_id, {
        "follow_up": FOLLOW_UP_TICKED,
        "follow_up_status": "Draft ready",
        "follow_up_draft": draft_url,
    })


def mark_sent(conn: sqlite3.Connection, role_id: int, when: date | None = None) -> None:
    """Settle a follow-up after the user has sent it from Gmail."""
    stamp = (when or date.today()).isoformat()
    db.update_job(conn, role_id, {"follow_up_status": f"Sent {stamp}"})

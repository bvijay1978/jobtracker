from datetime import date

import pytest

import db
import followup_queue

TODAY = date(2026, 7, 14)  # a Tuesday


def _seed(tmp_path):
    p = tmp_path / "t.db"
    db.init_db(p)
    conn = db.connect(p)
    rows = [
        # In the due queue:
        dict(title="A", company="X", status="Applied", date_applied="2026-07-01",
             contact_email="a@example.com"),
        dict(title="F", company="U", status="Applied", date_applied="2026-07-02",
             contact_email="f@example.com", follow_up_status="Draft ready",
             follow_up_draft="https://mail.google.com/mail/u/0/#drafts/f"),
        # Excluded:
        dict(title="B", company="Y", status="Applied", date_applied="2026-07-01",
             contact_email="b@example.com", follow_up=2),               # opted out
        dict(title="C", company="Z", status="Applied", date_applied="2026-07-13",
             contact_email="c@example.com"),                            # not due yet
        dict(title="D", company="W", status="Applied", date_applied="2026-07-01"),  # no contact
        dict(title="E", company="V", status="Applied", date_applied="2026-07-01",
             contact_email="e@example.com", follow_up_status="Sent 2026-07-08"),
        dict(title="G", company="T", status="Applied", date_applied="2026-07-01",
             contact_email="g@example.com", archived=1),                # archived
        dict(title="H", company="S", status="Shortlisted", date_applied="2026-07-01",
             contact_email="h@example.com"),                            # not 'Applied'
    ]
    for r in rows:
        db.insert_job(conn, r)
    conn.commit()
    return conn


def _by_title(conn, title):
    return next(dict(r) for r in db.fetch_all(conn) if r["title"] == title)


def test_is_due_counts_working_days_only():
    # Applied Friday: +2 working days = Tuesday.
    assert not followup_queue.is_due("2026-07-10", today=date(2026, 7, 13))  # Monday
    assert followup_queue.is_due("2026-07-10", today=date(2026, 7, 14))      # Tuesday
    # Applied Wednesday: due Friday; still due over the weekend.
    assert followup_queue.is_due("2026-07-08", today=date(2026, 7, 11))      # Saturday
    # Blanks and garbage are never due.
    assert not followup_queue.is_due(None, today=TODAY)
    assert not followup_queue.is_due("", today=TODAY)
    assert not followup_queue.is_due("2026-06.24x", today=TODAY)


def test_list_due_filters_and_orders(tmp_path):
    conn = _seed(tmp_path)
    titles = [r["title"] for r in followup_queue.list_due(conn, today=TODAY)]
    assert titles == ["A", "F"]  # oldest application first; drafted stays listed


def test_list_to_draft_excludes_already_drafted(tmp_path):
    conn = _seed(tmp_path)
    titles = [r["title"] for r in followup_queue.list_to_draft(conn, today=TODAY)]
    assert titles == ["A"]


def test_record_draft_files_link_and_status(tmp_path):
    conn = _seed(tmp_path)
    rid = _by_title(conn, "A")["id"]
    followup_queue.record_draft(conn, rid, "https://mail.google.com/mail/u/0/#drafts/a")
    conn.commit()
    row = _by_title(conn, "A")
    assert row["follow_up_status"] == "Draft ready"
    assert row["follow_up"] == 1
    assert row["follow_up_draft"].endswith("#drafts/a")
    # Now drafted -> out of the to-draft list, still in the due list.
    assert "A" not in [r["title"] for r in followup_queue.list_to_draft(conn, today=TODAY)]
    assert "A" in [r["title"] for r in followup_queue.list_due(conn, today=TODAY)]
    with pytest.raises(ValueError):
        followup_queue.record_draft(conn, rid, "")


def test_mark_sent_settles_and_dequeues(tmp_path):
    conn = _seed(tmp_path)
    rid = _by_title(conn, "F")["id"]
    followup_queue.mark_sent(conn, rid, when=date(2026, 7, 14))
    conn.commit()
    assert _by_title(conn, "F")["follow_up_status"] == "Sent 2026-07-14"
    assert "F" not in [r["title"] for r in followup_queue.list_due(conn, today=TODAY)]

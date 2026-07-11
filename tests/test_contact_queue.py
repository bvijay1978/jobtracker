import pytest

import contact_queue
import db


def _seed(tmp_path):
    p = tmp_path / "t.db"
    db.init_db(p)
    conn = db.connect(p)
    # In queue: live stage, no email, not resolved to 'none'.
    db.insert_job(conn, {"title": "A", "company": "X", "status": "Applied",
                         "date_applied": "2026-07-01"})
    db.insert_job(conn, {"title": "D", "company": "W", "status": "Shortlisted",
                         "date_applied": "2026-07-03"})
    db.insert_job(conn, {"title": "G", "company": "V", "status": "Applied"})  # no date
    # Excluded cases:
    db.insert_job(conn, {"title": "B", "company": "Y", "status": "Applied",
                         "contact_email": "has@already.com"})           # already has a contact
    db.insert_job(conn, {"title": "C", "company": "Z", "status": "Found"})   # not a live stage
    db.insert_job(conn, {"title": "E", "company": "U", "status": "Applied",
                         "archived": 1})                                # archived
    db.insert_job(conn, {"title": "F", "company": "T", "status": "Applied",
                         "contact_source": "none"})                     # resolved: no email
    conn.commit()
    return conn


def _by_title(conn, title):
    return next(dict(r) for r in db.fetch_all(conn) if r["title"] == title)


def test_list_needs_contact_filters_and_orders(tmp_path):
    conn = _seed(tmp_path)
    titles = [r["title"] for r in contact_queue.list_needs_contact(conn)]
    # live + no email + not 'none', newest apply-date first; undated sorts last.
    assert titles == ["D", "A", "G"]


def test_record_contact_writes_email_and_source(tmp_path):
    conn = _seed(tmp_path)
    rid = _by_title(conn, "A")["id"]
    contact_queue.record_contact(conn, rid, "consultant@example.com", "named-inbox")
    conn.commit()
    row = _by_title(conn, "A")
    assert row["contact_email"] == "consultant@example.com"
    assert row["contact_source"] == "named-inbox"
    # resolved role leaves the queue
    assert "A" not in [r["title"] for r in contact_queue.list_needs_contact(conn)]


def test_record_contact_backfills_date_only_when_empty(tmp_path):
    conn = _seed(tmp_path)
    # G has no date_applied -> gets filled
    contact_queue.record_contact(conn, _by_title(conn, "G")["id"],
                                 "info@vendor.com", "dept-inbox", date_applied="2026-07-05")
    # A already has a date -> must NOT be overwritten
    contact_queue.record_contact(conn, _by_title(conn, "A")["id"],
                                 "a@x.com", "dept-inbox", date_applied="2026-06-01")
    conn.commit()
    assert _by_title(conn, "G")["date_applied"] == "2026-07-05"
    assert _by_title(conn, "A")["date_applied"] == "2026-07-01"


@pytest.mark.parametrize("bad", ["none", "bogus", ""])
def test_record_contact_rejects_bad_source_or_email(tmp_path, bad):
    conn = _seed(tmp_path)
    rid = _by_title(conn, "A")["id"]
    with pytest.raises(ValueError):
        contact_queue.record_contact(conn, rid, "x@y.com", bad)
    with pytest.raises(ValueError):
        contact_queue.record_contact(conn, rid, "", "named-inbox")


def test_record_no_contact_marks_none_and_dequeues(tmp_path):
    conn = _seed(tmp_path)
    rid = _by_title(conn, "A")["id"]
    contact_queue.record_no_contact(conn, rid)
    conn.commit()
    row = _by_title(conn, "A")
    assert row["contact_source"] == "none"
    assert "platform" in (row["follow_up_status"] or "")
    assert "A" not in [r["title"] for r in contact_queue.list_needs_contact(conn)]

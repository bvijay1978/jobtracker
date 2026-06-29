import db
import screening_queue


def _seed(tmp_path):
    p = tmp_path / "t.db"
    db.init_db(p)
    conn = db.connect(p)
    db.insert_job(conn, {"title": "A", "company": "X", "status": "Draft CV",
                         "date_found": "2026-06-20"})
    db.insert_job(conn, {"title": "B", "company": "Y", "status": "Found",
                         "date_found": "2026-06-21"})
    db.insert_job(conn, {"title": "C", "company": "Z", "status": "Draft CV & Cover Letter",
                         "date_found": "2026-06-22"})
    conn.commit()
    return conn


def test_list_queue_returns_only_queued_newest_first(tmp_path):
    conn = _seed(tmp_path)
    titles = [r["title"] for r in screening_queue.list_queue(conn)]
    assert titles == ["C", "A"]  # queued only, newest first; "B" (Found) excluded


def test_record_result_settles_and_records_coverage(tmp_path):
    conn = _seed(tmp_path)
    rid = next(r["id"] for r in screening_queue.list_queue(conn) if r["title"] == "A")
    screening_queue.record_result(
        conn, rid, "Iain - Screening - A.docx",
        coverage={"pct": 72, "missing": ["insurance", "actuarial"]},
        base_fit_notes="FS fit",
    )
    conn.commit()
    row = next(dict(r) for r in db.fetch_all(conn) if r["id"] == rid)
    assert row["status"] == "CV Drafted"
    assert row["cv_version"] == "Iain - Screening - A.docx"
    assert "72% kw coverage" in row["fit_notes"]
    assert "insurance" in row["fit_notes"]
    assert "FS fit" in row["fit_notes"]  # original note preserved

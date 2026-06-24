import sqlite3

import db
import import_jobs


def _make_source(path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT, company TEXT, "
        "link TEXT, source_job_id TEXT)"
    )
    conn.executemany(
        "INSERT INTO jobs (title, company, link, source_job_id) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_import_inserts_new_skips_existing_and_dedupes(tmp_path):
    target = tmp_path / "target.db"
    db.init_db(target)
    with db.connect(target) as conn:
        db.insert_job(conn, {
            "title": "Existing", "company": "A",
            "link": "https://x/57000001", "source_job_id": "57000001",
        })
        conn.commit()

    source = tmp_path / "source.db"
    _make_source(source, [
        ("Existing", "A", "https://x/57000001", "57000001"),  # skip: id already present
        ("New Role", "B", "https://x/57000002", "57000002"),  # insert
        ("No Id Role", "C", None, None),                      # insert
        ("No Id Role", "C", None, None),                      # skip: title|company dup
    ])

    result = import_jobs.import_jobs(source, target)
    assert result["source_exists"] is True
    assert result["inserted"] == 2
    assert result["skipped"] == 2
    with db.connect(target) as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 3


def test_import_missing_source_is_noop(tmp_path):
    target = tmp_path / "target.db"
    result = import_jobs.import_jobs(tmp_path / "does-not-exist.db", target)
    assert result["source_exists"] is False
    assert result["inserted"] == 0
